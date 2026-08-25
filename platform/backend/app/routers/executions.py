from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import crud, models, schemas
from ..auth import get_current_user
from ..crud import executions as exec_domain
from ..database import get_db
from ..engine.runner import (
    submit_batch_aggregate_notify,
    submit_batch_execution,
    submit_execution,
)
from ..services import dataset_service

router = APIRouter(prefix="/api", tags=["执行"])


@router.post("/testcases/{case_id}/execute", response_model=schemas.ExecutionRecordOut)
def execute(case_id: int, data: schemas.ExecutionCreate, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """触发用例执行（异步）：立即创建 running 状态的执行记录并返回，后台线程池执行。
    前端通过 GET /executions/{id} 轮询执行状态。
    数据驱动：绑定数据集的用例按数据行展开为 N 条记录（响应返回第一条，列表可看全部）；
    多行展开失败聚合成一条通知，row_ids 只选 1 行时保持逐条。"""
    if data.case_id != case_id:
        raise HTTPException(400, "case_id 不一致")
    case = crud.get_testcase(db, case_id)
    if not case:
        raise HTTPException(404, f"用例不存在: {case_id}")
    env = crud.get_environment(db, data.env_id)
    if not env:
        raise HTTPException(404, f"环境不存在: {data.env_id}")

    try:
        plan = dataset_service.plan_case_expansion(db, case, dataset_id=data.dataset_id,
                                                   row_ids=data.row_ids)
    except ValueError as e:
        raise HTTPException(400, str(e))

    # 多行数据驱动批量 → 抑制逐条通知，聚合器等全部完成发一条汇总
    aggregate = len(plan) > 1 and plan[0]["dataset_id"] is not None
    first = None
    group_ids = []
    for item in plan:
        record = exec_domain.create_execution(db, case_id=case_id, env_id=data.env_id, user_id=user.id,
                                              dataset_id=item["dataset_id"], dataset_row=item["row"])
        crud.fill_audit_names(db, record)
        crud.fill_exec_names(db, record)
        # 提交到后台线程池执行（非阻塞）；行数据作为变量注入（列名即变量名），
        # overrides 为数据集节点配置快照（场景包：命中节点整块替换用例编排）
        submit_execution(case_id, data.env_id, record.id,
                         row_vars=(item["row"] or {}).get("data"),
                         node_config_overrides=item["overrides"], suppress_notify=aggregate)
        group_ids.append(record.id)
        first = first or record
    if aggregate:
        submit_batch_aggregate_notify(group_ids, case_id, data.env_id,
                                      plan[0]["dataset_id"], case.name)
    return first


@router.post("/testcases/batch-execute", response_model=list[schemas.ExecutionRecordOut])
def batch_execute(data: schemas.BatchExecutionCreate, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """批量执行多个用例（并行）：为每个用例创建 running 状态的执行记录并立即返回，
    后台线程池并行执行（并发上限 4，同环境共享登录 token 防互踢）。前端可轮询各 record 状态。
    数据驱动：绑定数据集的用例按数据行展开，展开条目与普通条目一并平铺提交；
    展开多条的用例失败聚合成一条通知。
    执行次数：counts 与 case_ids 一一对应（缺省全 1），如 A×3、B×1、C×2 共 6 轮。"""
    if not data.case_ids:
        raise HTTPException(400, "请至少选择一个用例")
    # 次数参数校验：长度对齐 + 区间约束（上限 20 防误操作刷爆线程池与记录表）
    if data.counts is None:
        counts = [1] * len(data.case_ids)
    else:
        if len(data.counts) != len(data.case_ids):
            raise HTTPException(400, "counts 长度必须与 case_ids 一致")
        if any(c < 1 or c > 20 for c in data.counts):
            raise HTTPException(400, "执行次数须在 1~20 之间")
        counts = data.counts
    env = crud.get_environment(db, data.env_id)
    if not env:
        raise HTTPException(404, f"环境不存在: {data.env_id}")

    records, flat_case_ids, rows_vars, overrides_list, suppress_flags = [], [], [], [], []
    aggregate_groups = []  # (execution_ids, case_id, dataset_id, case_name)
    for case_id, run_count in zip(data.case_ids, counts):
        case = crud.get_testcase(db, case_id)
        if not case:
            raise HTTPException(404, f"用例不存在: {case_id}")
        try:
            plan = dataset_service.plan_case_expansion(db, case)
        except ValueError as e:
            raise HTTPException(400, f"用例 {case.name}: {e}")
        group_ids = []
        aggregate = len(plan) > 1 and plan[0]["dataset_id"] is not None
        # 同一用例按执行次数重复提交（同轮次的数据行展开 plan 一致，复用一次规划结果）
        for _ in range(run_count):
            for item in plan:
                record = exec_domain.create_execution(db, case_id=case_id, env_id=data.env_id, user_id=user.id,
                                                      dataset_id=item["dataset_id"], dataset_row=item["row"])
                records.append(record)
                flat_case_ids.append(case_id)
                rows_vars.append((item["row"] or {}).get("data"))
                overrides_list.append(item["overrides"])
                suppress_flags.append(aggregate)
                group_ids.append(record.id)
        if aggregate:
            aggregate_groups.append((group_ids, case_id, plan[0]["dataset_id"], case.name))

    for record in records:
        crud.fill_audit_names(db, record)
        crud.fill_exec_names(db, record)

    # 提交批量并行执行（非阻塞，线程池并发上限 4）
    submit_batch_execution([r.id for r in records], flat_case_ids, data.env_id,
                           rows_vars, overrides_list, suppress_flags)
    for group_ids, case_id, dataset_id, case_name in aggregate_groups:
        submit_batch_aggregate_notify(group_ids, case_id, data.env_id, dataset_id, case_name)
    return records


@router.get("/executions", response_model=list[schemas.ExecutionRecordOut])
def list_executions(case_id: int | None = None, project_id: int | None = None, created_by: int | None = None, limit: int = 50, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    objs = crud.list_executions(db, case_id, project_id, created_by, limit)
    crud.fill_audit_names_batch(db, objs)
    crud.fill_exec_names(db, objs)
    return objs


@router.delete("/executions/cleanup")
def cleanup_executions(days: int = 30, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """手动清理指定天数前的执行记录（含步骤和断言），仅管理员可操作。需在 /{exec_id} 之前注册。"""
    if user.role != "admin":
        raise HTTPException(403, "需要管理员权限")
    if days < 1:
        raise HTTPException(400, "天数必须大于 0")
    cutoff = datetime.now() - timedelta(days=days)
    count = exec_domain.cleanup_old_records(db, cutoff)
    return {"message": f"已清理 {count} 条 {days} 天前的执行记录", "deleted": count, "days": days}


@router.get("/executions/{exec_id}", response_model=schemas.ExecutionRecordOut)
def get_execution(exec_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    obj = crud.get_execution(db, exec_id)
    if not obj:
        raise HTTPException(404, "执行记录不存在")
    crud.fill_audit_names(db, obj)
    crud.fill_exec_names(db, obj)
    return obj

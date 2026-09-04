from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import crud, models, schemas
from ..auth import get_current_user
from ..crud import executions as exec_domain
from ..database import get_db
from ..services.execution_launcher import build_launch_plan, commit_launch

router = APIRouter(prefix="/api", tags=["执行"])

# 并发数上限：防止误配置过大打爆线程与目标系统
MAX_CONCURRENCY = 16
# 单用例执行次数上限：放开到 9999（防手滑输天文数字刷爆记录表，正常用例远达不到）
MAX_RUN_COUNT = 9999


def _validate_concurrency(concurrency: int) -> None:
    if concurrency < 1 or concurrency > MAX_CONCURRENCY:
        raise HTTPException(400, f"并发数须在 1~{MAX_CONCURRENCY} 之间")


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
        plan = build_launch_plan(db, case, data.env_id, user.id,
                                 dataset_id=data.dataset_id, row_ids=data.row_ids)
    except ValueError as e:
        raise HTTPException(400, str(e))
    _validate_concurrency(data.concurrency)
    commit_launch([plan], data.env_id, concurrency=data.concurrency)
    return plan.records[0]


@router.post("/testcases/batch-execute", response_model=list[schemas.ExecutionRecordOut])
def batch_execute(data: schemas.BatchExecutionCreate, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """批量执行多个用例：为每个用例创建 running 状态的执行记录并立即返回，
    后台线程池执行，并发数可配（concurrency=1 逐个串行，一个结束再下一个；
    缺省 4 并行，同环境共享登录 token 防互踢）。前端可轮询各 record 状态。
    数据驱动：绑定数据集的用例按数据行展开，展开条目与普通条目一并平铺提交；
    展开多条的用例失败聚合成一条通知。
    执行次数：counts 与 case_ids 一一对应（缺省全 1），如 A×3、B×1、C×2 共 6 轮。"""
    if not data.case_ids:
        raise HTTPException(400, "请至少选择一个用例")
    _validate_concurrency(data.concurrency)
    # 次数参数校验：长度对齐 + 下界 1（上限仅防手滑，正常压测循环也够用）
    if data.counts is None:
        counts = [1] * len(data.case_ids)
    else:
        if len(data.counts) != len(data.case_ids):
            raise HTTPException(400, "counts 长度必须与 case_ids 一致")
        if any(c < 1 or c > MAX_RUN_COUNT for c in data.counts):
            raise HTTPException(400, f"执行次数须在 1~{MAX_RUN_COUNT} 之间")
        counts = data.counts
    env = crud.get_environment(db, data.env_id)
    if not env:
        raise HTTPException(404, f"环境不存在: {data.env_id}")

    plans = []
    for case_id, run_count in zip(data.case_ids, counts):
        case = crud.get_testcase(db, case_id)
        if not case:
            raise HTTPException(404, f"用例不存在: {case_id}")
        try:
            plans.append(build_launch_plan(db, case, data.env_id, user.id,
                                           run_count=run_count))
        except ValueError as e:
            raise HTTPException(400, f"用例 {case.name}: {e}")

    # 全部用例平铺进一个批次专用线程池（并发数 = concurrency，1 即串行）
    commit_launch(plans, data.env_id, concurrency=data.concurrency)
    return [record for plan in plans for record in plan.records]


@router.get("/executions", response_model=schemas.ExecutionListOut)
def list_executions(case_id: int | None = None, project_id: int | None = None, created_by: int | None = None,
                    limit: int = 50, offset: int = 0, case_name: str | None = None, status: str | None = None,
                    start_time: datetime | None = None, end_time: datetime | None = None,
                    sort_by: str = "id", order: str = "desc",
                    db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """筛选（状态/时间范围）与排序全部服务端处理，返回 {items, total} 信封：
    分页组件翻页/整页排序口径才正确；total 与列表同口径过滤"""
    if sort_by not in crud.EXECUTION_SORT_FIELDS:
        raise HTTPException(400, f"不支持的排序字段: {sort_by}")
    if order not in ("asc", "desc"):
        raise HTTPException(400, "order 仅支持 asc / desc")
    objs = crud.list_executions(db, case_id=case_id, project_id=project_id, created_by=created_by,
                                limit=limit, offset=offset, case_name=case_name, status=status,
                                start_time=start_time, end_time=end_time, sort_by=sort_by, order=order)
    total = crud.count_executions(db, case_id=case_id, project_id=project_id, created_by=created_by,
                                  case_name=case_name, status=status, start_time=start_time, end_time=end_time)
    crud.fill_audit_names_batch(db, objs)
    crud.fill_exec_names(db, objs)
    return {"items": objs, "total": total}


@router.get("/executions/stats")
def execution_stats(days: int = 7, project_id: int | None = None,
                    db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """近 N 天执行统计（工作台用）：全量聚合口径，不受列表 200 条截断影响。
    需注册在 /executions/{exec_id} 之前。"""
    if days < 1 or days > 365:
        raise HTTPException(400, "天数须在 1~365 之间")
    since = datetime.now() - timedelta(days=days)
    # ExecutionRecord 无 created_at，时间口径用 started_at（default=now）
    q = db.query(models.ExecutionRecord).filter(models.ExecutionRecord.started_at >= since)
    if project_id is not None:
        q = q.join(models.TestCase, models.ExecutionRecord.case_id == models.TestCase.id) \
             .filter(models.TestCase.project_id == project_id)
    rows = q.with_entities(models.ExecutionRecord.status).all()
    total = len(rows)
    passed = sum(1 for (s,) in rows if s == "success")
    rate = round(passed * 100 / total) if total else None
    return {"count": total, "passed": passed, "rate": rate, "days": days}


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

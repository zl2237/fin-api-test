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
    数据驱动：绑定数据集的用例用其单套数据执行（dataset_id 可临时换数据集）。"""
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
                                 dataset_id=data.dataset_id)
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
    绑定数据集的用例按该数据集的单套值展开为一条执行记录，与其他条目一并平铺提交。
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


@router.post("/executions/steps/{step_id}/replay")
def replay_step(step_id: int, data: schemas.StepReplayRequest,
                db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """报告页节点重放：按步骤快照定位接口（path+method+项目），用原执行环境重发一次。

    body_override（编辑后的请求体）优先，否则用原快照请求体；表达式求值与
    调试/DAG 链路同口径（${timestamp()} 等生效）。纯调试口径：不写回报告。"""
    import time
    from copy import deepcopy

    from ..engine.expression import ExpressionEngine
    from ..engine.type_coercer import apply_field_types, coerce_json_strings
    from ..services.body_builder import pop_file_fields_from_body
    from ..services.request_sender import send_request
    from ..services.runtime_service import build_db_client, build_http_client, login

    step = db.get(models.StepRecord, step_id)
    if not step:
        raise HTTPException(404, f"步骤不存在: {step_id}")
    execution = db.get(models.ExecutionRecord, step.execution_id)
    if not execution or not execution.env_id:
        raise HTTPException(400, "原执行记录缺失或无环境信息，无法重放")
    case = crud.get_testcase(db, execution.case_id)
    api = (db.query(models.ApiDefinition)
           .filter(models.ApiDefinition.path == step.api_path,
                   models.ApiDefinition.method == (step.api_method or "GET").upper(),
                   models.ApiDefinition.project_id == case.project_id if case else True)
           .first())
    if not api:
        raise HTTPException(404, f"接口已不存在或已改路径: {step.api_path}")
    env = crud.get_environment(db, execution.env_id)
    if not env:
        raise HTTPException(404, f"环境不存在: {execution.env_id}")

    start_ts = time.time()
    client = build_http_client(env)
    try:
        try:
            login(client, env)
        except Exception as e:
            return {"status_code": 0, "response_body": {"error": str(e)},
                    "error": "登录失败", "elapsed_ms": int((time.time() - start_ts) * 1000),
                    "request_body": data.body_override}
        client.headers = {**(client.headers or {}),
                          **(deepcopy(api.headers_template) or {})}
        client.headers = {k: v for k, v in client.headers.items() if v is not None}
        body = deepcopy(data.body_override) if data.body_override is not None \
            else deepcopy(step.request_body or {})
        expr = ExpressionEngine({"extracted": {}}, db_client=build_db_client(env))
        body = expr.evaluate(body)
        body = coerce_json_strings(body)
        body = apply_field_types(body, api)
        for k, v in list((client.headers or {}).items()):
            if isinstance(v, str) and "${" in v:
                client.headers[k] = expr.evaluate(v)
        body, file_fields = pop_file_fields_from_body(body, api)
        req_timeout = getattr(env, "timeout", None) or 15
        status_code, response_data, error_msg = send_request(
            db, client, api, body, file_fields=file_fields, timeout=req_timeout)
        crud.log_operation(db, user, "execute", "api", api.id,
                           f"replay step#{step_id} ({api.name})")
        return {"status_code": status_code, "response_body": response_data,
                "error": error_msg,
                "elapsed_ms": int((time.time() - start_ts) * 1000),
                "request_body": body}
    finally:
        try:
            if client.session:
                client.session.close()
        except Exception:
            pass


@router.get("/executions/{exec_id}", response_model=schemas.ExecutionRecordOut)
def get_execution(exec_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    obj = crud.get_execution(db, exec_id)
    if not obj:
        raise HTTPException(404, "执行记录不存在")
    crud.fill_audit_names(db, obj)
    crud.fill_exec_names(db, obj)
    return obj


@router.post("/executions/{exec_id}/terminate", response_model=schemas.ExecutionRecordOut)
def terminate_execution(exec_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """手动终止执行。

    两类场景统一入口：
    - 僵尸记录：进程重启致后台线程丢失，记录永远停在 running——直接落 terminated
    - 活动执行：runner 在节点间/套件成员间检查点感知本状态后提前退出，
      剩余节点/成员并入未执行统计；套件主记录终止时级联标记其名下
      running 的成员行记录（成员 DagExecutor 检查点只看自己的记录状态）
    """
    obj = crud.get_execution(db, exec_id)
    if not obj:
        raise HTTPException(404, "执行记录不存在")
    if obj.status != "running":
        raise HTTPException(400, "仅运行中的执行可终止")
    obj.status = "terminated"
    obj.ended_at = datetime.now()
    obj.summary = {**(obj.summary or {}),
                   "error": f"用户 {user.username} 手动终止"}
    cascaded = 0
    if (obj.summary or {}).get("suite"):
        for child in (db.query(models.ExecutionRecord)
                      .filter(models.ExecutionRecord.suite_execution_id == exec_id,
                              models.ExecutionRecord.status == "running").all()):
            child.status = "terminated"
            child.ended_at = datetime.now()
            child.summary = {**(child.summary or {}), "error": "套件主执行被手动终止"}
            cascaded += 1
    db.commit()
    db.refresh(obj)
    crud.fill_audit_names(db, obj)
    crud.fill_exec_names(db, obj)
    if cascaded:
        obj.summary = {**(obj.summary or {}), "cascaded": cascaded}
    return obj

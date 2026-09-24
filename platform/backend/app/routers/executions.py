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
    调试/DAG 链路同口径（${timestamp()} 等生效）。
    断点续跑配套（同口径验证）：
    - ${} 求值上下文 = 报告虚拟上下文（该节点之前各成功步骤的提取值 + 当前数据集行值）
    - 发送后同口径跑后置提取与断言（规则优先取当前节点配置，无配置回退步骤快照）
    - 断言全过且请求成功 → 步骤打 replay_passed_at（「已重放通过」徽标），
      供用户同步数据集后从此节点续跑；步骤内容不改动（报告只认真实执行）
    """
    import time
    from copy import deepcopy

    from ..engine.assertion_engine import AssertionEngine
    from ..engine.expression import ExpressionEngine
    from ..engine.extractor import Extractor
    from ..engine.report_context import build_report_context
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

    # 当前节点配置（断言/提取规则优先取当前值——参数配置可变原则）
    config = (db.query(models.CaseNodeConfig)
              .filter(models.CaseNodeConfig.case_id == execution.case_id,
                      models.CaseNodeConfig.node_id == step.node_id)
              .first()) if step.node_id else None
    extract_rules = (config.post_extract if config and config.post_extract else step.post_extract)
    assertion_rules = (config.assertions if config and config.assertions else None)

    # 报告虚拟上下文：该节点之前各成功步骤提取值 + 当前数据集行值（同续跑 seed 口径）
    steps = sorted(execution.steps, key=lambda s: s.id)
    row_vars = _current_dataset_row_vars(db, execution)
    ctx_extracted = build_report_context(steps, row_vars=row_vars, before_node=step.node_id)

    start_ts = time.time()
    client = build_http_client(env)
    try:
        try:
            login(client, env)
        except Exception as e:
            return {"status_code": 0, "response_body": {"error": str(e)},
                    "error": "登录失败", "elapsed_ms": int((time.time() - start_ts) * 1000),
                    "request_body": data.body_override, "passed": False}
        client.headers = {**(client.headers or {}),
                          **(deepcopy(api.headers_template) or {})}
        client.headers = {k: v for k, v in client.headers.items() if v is not None}
        body = deepcopy(data.body_override) if data.body_override is not None \
            else deepcopy(step.request_body or {})
        expr = ExpressionEngine({"extracted": deepcopy(ctx_extracted)},
                                db_client=build_db_client(env))
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
        elapsed = int((time.time() - start_ts) * 1000)
        crud.log_operation(db, user, "execute", "api", api.id,
                           f"replay step#{step_id} ({api.name})")

        # 同口径后置提取（提取值并入上下文供断言 ${} 引用与结果展示）
        extracted: dict = {}
        if extract_rules and response_data is not None:
            extractor = Extractor()
            extractor.db_client = build_db_client(env)
            extractor.set_extracted_vars(ctx_extracted)
            extracted = extractor.extract(response_data, extract_rules)

        # 同口径断言（规则取当前节点配置）
        assertion_results: list[dict] = []
        if assertion_rules:
            engine = AssertionEngine({"extracted": {**ctx_extracted, **extracted}},
                                     build_db_client(env))
            assertion_results = engine.evaluate_all(response_data, status_code, elapsed, assertion_rules)
        passed = (error_msg is None) and all(r["pass"] for r in assertion_results)

        # 验证通过打点（徽标数据源）；步骤内容不动——报告只认真实执行
        if passed and step.status != "success":
            from datetime import datetime as _dt
            step.replay_passed_at = _dt.now()
            db.commit()

        return {"status_code": status_code, "response_body": response_data,
                "error": error_msg,
                "elapsed_ms": elapsed,
                "request_body": body,
                "passed": passed,
                "assertions": assertion_results,
                "extracted": extracted}
    finally:
        try:
            if client.session:
                client.session.close()
        except Exception:
            pass


def _current_dataset_row_vars(db: Session, execution: models.ExecutionRecord) -> dict | None:
    """执行记录绑定数据集的当前行值（首行）：重放/续跑共用「数据集取当前」口径。

    数据集被用户修改后此处取到新值（与 dataset_row 快照解耦）；无绑定返回 None。
    """
    if not execution.dataset_id:
        return None
    row = (db.query(models.DataSetRow)
           .filter(models.DataSetRow.dataset_id == execution.dataset_id)
           .order_by(models.DataSetRow.row_index)
           .first())
    return dict(row.data) if row and isinstance(row.data, dict) else None


@router.post("/executions/{exec_id}/resume", response_model=schemas.ExecutionRecordOut)
def resume_execution(exec_id: int, db: Session = Depends(get_db),
                     user: models.User = Depends(get_current_user)):
    """断点续跑：从首个未成功节点起，用当前配置 + 当前数据集重新真实执行。

    调试闭环（重放验证 → 手动同步数据集 → 续跑）：
    - 前置校验：仅 failed 报告可续；套件（主/成员）不支持；编排结构指纹一致
      （指纹只锁节点/边/接口绑定，参数配置与数据集允许变——续跑用当前值，
      正是「改完参数不用整个重跑」的核心场景）
    - 上下文：前缀成功步骤提取值 + 当前数据集行值拼成虚拟上下文注入 ${} 池
    - 时间线：首个非成功步骤起的旧记录删除，续跑段重新生成（报告只认真实执行）
    - 完成不发企微通知（调试动作，避免打扰）
    """
    import threading

    from ..database import SessionLocal
    from ..engine.dag_executor import DagExecutor
    from ..engine.orchestration import collect_node_bindings, compute_structure_fingerprint
    from ..engine.report_context import build_report_context

    record = crud.get_execution(db, exec_id)
    if not record:
        raise HTTPException(404, f"执行记录不存在: {exec_id}")
    if record.status != "failed":
        raise HTTPException(400, f"仅失败报告可续跑（当前状态: {record.status}），成功/执行中请直接执行")
    if record.suite_execution_id:
        raise HTTPException(400, "套件成员报告不支持续跑：请单独执行该用例后在新报告上调试")
    case = crud.get_testcase(db, record.case_id)
    if not case:
        raise HTTPException(404, f"用例不存在: {record.case_id}")
    if getattr(case, "case_type", "normal") == "suite":
        raise HTTPException(400, "套件用例不支持续跑：请单独执行成员用例")
    env = crud.get_environment(db, record.env_id)
    if not env:
        raise HTTPException(404, f"环境不存在: {record.env_id}")

    if not record.orchestration_fingerprint:
        raise HTTPException(400, "该报告产生于续跑功能上线前（无编排指纹），请重新执行一次后再续跑")
    current_fp = compute_structure_fingerprint(case.dag_config,
                                               collect_node_bindings(db, case.id))
    if current_fp != record.orchestration_fingerprint:
        raise HTTPException(400, "编排结构已变更（节点/连线/接口绑定与报告时不一致），请重新执行")

    # 起点节点：首个非成功步骤；无失败步骤（异常中断）回退 leftover 首节点
    steps = sorted(record.steps, key=lambda s: s.id)
    first_unsuccess = next((s for s in steps if s.status != "success"), None)
    if first_unsuccess and first_unsuccess.node_id:
        start_node = first_unsuccess.node_id
    else:
        leftover = (record.summary or {}).get("leftover") or []
        if not leftover:
            raise HTTPException(400, "报告中无可续跑的失败节点（异常中断且无未执行节点），请重新执行")
        start_node = leftover[0]

    row_vars = _current_dataset_row_vars(db, record)
    context_seed = build_report_context(steps, row_vars=row_vars)

    # 置 running（前端轮询立即感知），后台线程续跑（独立会话，请求会话随响应关闭）
    record.status = "running"
    db.commit()
    crud.log_operation(db, user, "execute", "case", case.id,
                       f"resume execution#{exec_id} from node {start_node}")

    exec_id_val, case_id_val, env_id_val = record.id, case.id, env.id

    def _run() -> None:
        rdb = SessionLocal()
        try:
            rcase = crud.get_testcase(rdb, case_id_val)
            renv = crud.get_environment(rdb, env_id_val)
            rrecord = crud.get_execution(rdb, exec_id_val)
            if not (rcase and renv and rrecord):
                return
            DagExecutor(rdb, rcase, renv, execution_record=rrecord,
                        row_vars=row_vars, context_seed=context_seed,
                        start_node=start_node, suppress_notify=True).execute()
        except Exception as e:
            try:
                rrecord = crud.get_execution(rdb, exec_id_val)
                if rrecord and rrecord.status == "running":
                    rrecord.status = "failed"
                    rrecord.summary = {**(rrecord.summary or {}), "error": f"续跑异常: {e}"}
                    rdb.commit()
            except Exception:
                pass
        finally:
            rdb.close()

    threading.Thread(target=_run, daemon=True,
                     name=f"resume-{exec_id_val}").start()
    db.refresh(record)
    return record


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

"""报告页重放与断点续跑（从 routers/executions 迁出的执行编排层）。

两类动作共用的口径（详见各函数注释）：
- 定位与前置校验（404/400 语义与迁移前一致）
- 报告虚拟上下文（前缀成功步骤的提取值按节点命名空间还原）
- 规则取当前节点配置（参数配置可变原则），发送/提取/断言与执行链路同口径

路由层只做参数解析与鉴权；无 HTTP 之外的调用方时本模块不感知路由存在，
但沿用 HTTPException 表达校验失败（FastAPI 任意层抛出均生效）。
"""
import threading
import time
from copy import deepcopy
from datetime import datetime
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from .. import crud, models
from ..database import SessionLocal
from ..engine.assertion_engine import AssertionEngine
from ..engine.dag_executor import DagExecutor
from ..engine.extractor import Extractor
from ..engine.orchestration import collect_node_bindings, compute_structure_fingerprint
from ..engine.report_context import build_report_context
from ..engine.type_coercer import apply_field_types, coerce_json_strings
from ..engine.variables import VariableRegistry
from ..services.body_builder import pop_file_fields_from_body
from ..services.request_sender import send_request
from ..services.runtime_service import build_db_client, build_http_client, login


def replay_step_once(db: Session, user: models.User, step_id: int,
                     body_override: Any) -> dict:
    """报告页节点重放：按步骤快照定位接口（path+method+项目），用原执行环境重发一次。

    body_override（编辑后的请求体）优先，否则用原快照请求体。
    断点续跑配套（同口径验证）：
    - 上下文 = 报告虚拟上下文（该节点之前各成功步骤的提取值）
    - 发送后同口径跑后置提取与断言（规则优先取当前节点配置，无配置回退步骤快照）
    - 断言全过且请求成功 → 步骤打 replay_passed_at（「已重放通过」徽标），
      供用户同步数据集后从此节点续跑；步骤内容不改动（报告只认真实执行）
    """
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

    # 报告虚拟注册表：前缀成功步骤提取值按节点命名空间还原
    # （重放口径 = 续跑 seed 口径；{{节点.变量}} 引用链保持完整。
    # 数据集行现为 per-node 入参配置（非键值），不再注入注册表）
    steps = sorted(execution.steps, key=lambda s: s.id)
    replay_registry = VariableRegistry()
    for nid, vars_ in build_report_context(steps, before_node=step.node_id).items():
        replay_registry.inject(nid, vars_)

    start_ts = time.time()
    client = build_http_client(env)
    try:
        try:
            login(client, env)
        except Exception as e:
            return {"status_code": 0, "response_body": {"error": str(e)},
                    "error": "登录失败", "elapsed_ms": int((time.time() - start_ts) * 1000),
                    "request_body": body_override, "passed": False}
        client.headers = {**(client.headers or {}),
                          **(deepcopy(api.headers_template) or {})}
        client.headers = {k: v for k, v in client.headers.items() if v is not None}
        body = deepcopy(body_override) if body_override is not None \
            else deepcopy(step.request_body or {})
        # 重放 body 不做表达式求值：快照/手改值原样发送（${} 语法已废止），
        # 类型还原与字段强转保持与执行链路同口径
        body = coerce_json_strings(body)
        body = apply_field_types(body, api)
        body, file_fields = pop_file_fields_from_body(body, api)
        req_timeout = getattr(env, "timeout", None) or 15
        status_code, response_data, error_msg = send_request(
            db, client, api, body, file_fields=file_fields, timeout=req_timeout)
        elapsed = int((time.time() - start_ts) * 1000)
        crud.log_operation(db, user, "execute", "api", api.id,
                           f"replay step#{step_id} ({api.name})")

        # 同口径后置提取（产出注册进本节点命名空间，供断言 {{}} 引用与结果展示）
        extracted: dict = {}
        if extract_rules and response_data is not None:
            extractor = Extractor()
            extractor.db_client = build_db_client(env)
            extracted = extractor.extract(response_data, extract_rules,
                                          replay_registry, step.node_id or "")

        # 同口径断言（规则取当前节点配置）
        assertion_results: list[dict] = []
        if assertion_rules:
            engine = AssertionEngine(replay_registry, build_db_client(env),
                                     self_node=step.node_id or "")
            assertion_results = engine.evaluate_all(response_data, status_code, elapsed, assertion_rules)
        passed = (error_msg is None) and all(r["pass"] for r in assertion_results)

        # 验证通过打点（徽标数据源）；步骤内容不动——报告只认真实执行
        if passed and step.status != "success":
            step.replay_passed_at = datetime.now()
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


def _current_dataset_row(db: Session, execution: models.ExecutionRecord) -> dict | None:
    """执行记录绑定数据集的当前行数据（首行，per-node 入参配置）：续跑共用
    「数据集取当前」口径。数据集被用户修改后此处取到新配置（与 dataset_row
    快照解耦）；无绑定/无行返回 None（执行强绑定下续跑被拒）。"""
    if not execution.dataset_id:
        return None
    row = (db.query(models.DataSetRow)
           .filter(models.DataSetRow.dataset_id == execution.dataset_id)
           .order_by(models.DataSetRow.row_index)
           .first())
    return dict(row.data) if row and isinstance(row.data, dict) else None


def resume_execution_async(db: Session, user: models.User, exec_id: int) -> models.ExecutionRecord:
    """断点续跑：从首个未成功节点起，用当前配置 + 当前数据集重新真实执行。

    调试闭环（重放验证 → 手动同步数据集 → 续跑）：
    - 前置校验：仅 failed 报告可续；套件（主/成员）不支持；编排结构指纹一致
      （指纹只锁节点/边/接口绑定，参数配置与数据集允许变——续跑用当前值，
      正是「改完参数不用整个重跑」的核心场景）
    - 上下文：前缀成功步骤提取值 + 当前数据集行值拼成虚拟上下文注入 ${} 池
    - 时间线：首个非成功步骤起的旧记录删除，续跑段重新生成（报告只认真实执行）
    - 完成不发企微通知（调试动作，避免打扰）
    """
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

    dataset_row = _current_dataset_row(db, record)
    if dataset_row is None:
        raise HTTPException(400, "原执行未绑定数据集（或数据集已无数据行），续跑需绑定数据集，请重新执行")
    context_seed = build_report_context(steps)

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
                        dataset_row=dataset_row, context_seed=context_seed,
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

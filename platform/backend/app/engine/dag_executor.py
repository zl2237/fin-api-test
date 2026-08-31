"""
DAG 拓扑执行引擎。

复用现有能力：
- utils.http_client.HttpClient   （请求 + 401 自动重登 + 业务码校验 + 日志脱敏）
- db.db_client.DBClient          （MySQL 查询，用于 db_query_* 断言）
- utils.generator_util           （通过表达式引擎调用）

执行流程：
1. 按 env 构建 HttpClient，按 variables 登录并注册 token 刷新回调
2. 按 env.db_config 构建 DBClient（可选）
3. 对 DAG 做拓扑排序，逐节点执行：
   前置处理 → 发请求 → 后置提取 → 断言 → 落库 StepRecord/AssertionRecord
4. 默认失败即停止（断言失败或请求异常）
"""
import time
from copy import deepcopy
from datetime import datetime
from types import SimpleNamespace
from typing import Any

from sqlalchemy.orm import Session

# 复用现有项目代码（异常分类已收敛至 services.request_sender）
from utils.http_client import HttpClient

from .. import (
    models,
    path_setup,  # noqa: F401
)
from ..services.body_builder import (
    apply_row_overrides,
    build_request_body,
    pop_file_fields_from_body,
)
from ..services.dataset_service import filter_row_vars_for_node
from ..services.notifier import send_notify
from ..services.request_sender import send_request
from ..services.runtime_service import build_db_client, build_http_client, login
from .assertion_engine import AssertionEngine
from .context import ExecutionContext
from .events import AssertionResult, DbSink, ExecutionSink, StepResult
from .extractor import Extractor
from .preprocessor import PreProcessor
from .type_coercer import apply_field_types, coerce_json_strings


class DagExecutor:
    def __init__(self, db: Session, case: models.TestCase, env: models.Environment,
                 execution_record: models.ExecutionRecord | None = None,
                 sink: ExecutionSink | None = None,
                 row_vars: dict[str, Any] | None = None,
                 row_origins: dict[str, Any] | None = None,
                 node_config_overrides: dict[str, dict] | None = None,
                 suppress_notify: bool = False):
        self.db = db
        self.case = case
        self.env = env
        # 业务变量从 variables 读取（与登录/通知配置解耦）；
        # 数据驱动：row_vars 为数据集行 {列key: 值}，覆盖同名环境变量进池
        self.context = ExecutionContext(env_vars=env.variables or {}, row_vars=row_vars)
        # 数据驱动批量执行时抑制逐条通知（由聚合器等全部完成后发一条汇总）
        self.suppress_notify = suppress_notify
        # 数据集行值原始引用（优先级 1）：PreProcessor 据此让非动态 set_field 让位行值
        self.row_vars = row_vars or None
        # 列快照原值 {key: 生成时源头值}（数据集 columns 的 origin）：同名异值列
        # 只作用于"节点配置值 == origin"的节点（快照保真，见 filter_row_vars_for_node）
        self.row_origins = row_origins or None
        # 数据集节点配置快照 {node_id: {api_id, pre_process, post_extract, assertions, wait_after_ms}}：
        # 命中的节点整块替换用例当前编排（前置/后置/断言全换），未命中回落 CaseNodeConfig
        self.node_config_overrides = node_config_overrides or None
        self.extractor = Extractor()
        self.http_client: HttpClient | None = None
        self.db_client = None
        # 并发执行场景下由外部预先创建 record 并传入，避免后台线程重复创建
        self._precreated_record = execution_record
        # 事件出口：默认落库；测试/dry-run 注入内存 sink（持久化接缝）
        self.sink: ExecutionSink = sink or DbSink(db)

    # ---------- 拓扑排序 ----------
    @staticmethod
    def _topo_sort(dag: dict[str, Any]) -> tuple[list[str], list[str]]:
        """返回 (执行顺序节点id列表, 因环/断链未执行的节点id列表)"""
        nodes = dag.get("nodes", [])
        edges = dag.get("edges", [])
        ids = [n["id"] for n in nodes]
        in_degree = {nid: 0 for nid in ids}
        adj: dict[str, list[str]] = {nid: [] for nid in ids}
        for e in edges:
            src, tgt = e.get("source"), e.get("target")
            if src in adj and tgt in in_degree:
                adj[src].append(tgt)
                in_degree[tgt] += 1
        # 保持稳定顺序：按节点 id 字典序入队
        queue = sorted([nid for nid, d in in_degree.items() if d == 0])
        order: list[str] = []
        while queue:
            nid = queue.pop(0)
            order.append(nid)
            for nxt in adj[nid]:
                in_degree[nxt] -= 1
                if in_degree[nxt] == 0:
                    queue.append(nxt)
            queue.sort()
        leftover = [nid for nid in ids if nid not in order]
        return order, leftover

    # ---------- 请求发送 ----------
    def _send_request(self, api: models.ApiDefinition, body: Any, headers: dict,
                      file_fields: list[tuple[str, str]] | None = None) -> tuple[int, Any, str | None]:
        """委托共享发送器（与单接口调试同一实现），返回 (status_code, response_body, error_msg)"""
        # 超时时间取环境配置（向后兼容：未配置时默认 15 秒）
        timeout = getattr(self.env, "timeout", None) or 15
        return send_request(self.db, self.http_client, api, body,
                            file_fields=file_fields, timeout=timeout)

    # ---------- 执行入口 ----------
    def execute(self) -> models.ExecutionRecord:
        if self._precreated_record is not None:
            # 并发执行：复用外部已创建的 record（已在请求线程中落库）
            record = self._precreated_record
            if record not in self.db:
                record = self.db.merge(record)
        else:
            record = models.ExecutionRecord(case_id=self.case.id, env_id=self.env.id, status="running")
            self.db.add(record)
            self.db.commit()
            self.db.refresh(record)

        # 耗时口径：started_at 取真正开始执行的时刻，而非批量提交时创建 record 的
        # 时刻——排队等待不计入用例耗时（报告/通知的 duration = ended_at - started_at）
        record.started_at = datetime.now()

        self.http_client = build_http_client(self.env)
        self.db_client = build_db_client(self.env)
        # extractor / assertion_engine 共享 db_client，供 source=db 提取与 db_* 断言使用
        self.extractor.db_client = self.db_client

        total_passed = 0
        total_failed = 0
        error_msg = None
        try:
            # 登录在 try 内，失败时记为执行失败而非 500
            login(self.http_client, self.env)
            dag = self.case.dag_config or {"nodes": [], "edges": []}
            order, leftover = self._topo_sort(dag)
            nodes_map = {n["id"]: n for n in dag.get("nodes", [])}

            for idx, node_id in enumerate(order):
                step_passed, wait_ms = self._execute_node(record.id, node_id, nodes_map.get(node_id, {"id": node_id}))
                if step_passed:
                    total_passed += 1
                else:
                    total_failed += 1
                    # 默认失败即停止：后续节点未执行，并入 leftover（与环节点同口径：
                    # 计入失败总数、不落步骤记录，通知里展示"未执行：N 个节点"）
                    leftover = leftover + order[idx + 1:]
                    break
                # 节点间等待：当前节点成功且仍有后续节点时，按配置等待若干毫秒，
                # 给后端处理事务/数据落库留出时间，避免下游接口读到未提交数据
                if step_passed and idx < len(order) - 1 and wait_ms and wait_ms > 0:
                    time.sleep(wait_ms / 1000.0)

            if leftover:
                # 未执行的节点计入失败统计但不落步骤记录
                total_failed += len(leftover)

            record.status = "failed" if total_failed > 0 else "success"
            record.summary = {
                "total": total_passed + total_failed,
                "passed": total_passed,
                "failed": total_failed,
                "leftover": leftover,
            }
        except Exception as e:
            error_msg = str(e)
            record.status = "failed"
            record.summary = {"total": total_passed + total_failed, "passed": total_passed, "failed": total_failed, "error": error_msg}
        finally:
            record.ended_at = datetime.now()
            self.db.commit()
            if self.db_client:
                try:
                    self.db_client.close()
                except Exception as e:
                    print(f"[资源清理] DBClient 关闭失败（忽略）: {e}")
            # 关闭 HTTP session，避免连续执行多个用例时连接池累积导致后续请求超时
            if self.http_client and self.http_client.session:
                try:
                    self.http_client.session.close()
                except Exception as e:
                    print(f"[资源清理] HTTP session 关闭失败（忽略）: {e}")
            # 发送企微通知（notify_config 配置了 webhook 时）
            executor_name = ""
            if record.created_by:
                user = self.db.query(models.User).filter(models.User.id == record.created_by).first()
                if user:
                    executor_name = user.username
            project_name = ""
            if self.case.project_id:
                project = self.db.query(models.Project).filter(models.Project.id == self.case.project_id).first()
                if project:
                    project_name = project.name
            if self.suppress_notify:
                print("[通知发送] 跳过逐条通知：数据驱动批量执行由聚合器汇总发送")
            else:
                send_notify(self.env, self.case, record, executor_name=executor_name, project_name=project_name)
        return record

    # ---------- 单节点执行 ----------
    def _resolve_node_config(self, node_id: str):
        """节点配置来源：数据集快照优先（node_id 命中整块替换）→ 回落用例 CaseNodeConfig。"""
        snap = (self.node_config_overrides or {}).get(node_id)
        if snap:
            return SimpleNamespace(
                node_id=node_id,
                api_id=snap.get("api_id"),
                pre_process=snap.get("pre_process") or [],
                post_extract=snap.get("post_extract") or [],
                assertions=snap.get("assertions") or [],
                wait_after_ms=snap.get("wait_after_ms") or 0,
            )
        return self.db.query(models.CaseNodeConfig).filter(
            models.CaseNodeConfig.case_id == self.case.id,
            models.CaseNodeConfig.node_id == node_id,
        ).first()

    def _execute_node(self, execution_id: int, node_id: str, node: dict) -> tuple[bool, int]:
        """执行单个节点。返回 (是否通过, 节点配置的 wait_after_ms)。
        wait_after_ms 表示当前节点执行完后到下一节点请求前的等待毫秒数，由调用方在节点间应用。
        """
        config = self._resolve_node_config(node_id)

        api = None
        if config and config.api_id:
            api = self.db.query(models.ApiDefinition).filter(models.ApiDefinition.id == config.api_id).first()

        started_at = datetime.now()
        start_ts = time.time()

        # 无配置或无接口定义 → 产出失败事件
        if not api:
            self.sink.record_step(StepResult(
                execution_id=execution_id, node_id=node_id,
                api_name=node.get("data", {}).get("label") if isinstance(node.get("data"), dict) else node_id,
                api_path="", api_method="",
                request_headers={}, request_body={},
                response_status=0, response_body={"error": "节点未绑定接口或配置缺失"},
                response_time_ms=0, started_at=started_at, ended_at=datetime.now(),
                status="failed",
            ))
            return False, 0

        # 1. 准备请求体 / 请求头
        # 优先用 ApiField 组装（新版本字段级配置）；无 fields 时回退到 request_template
        # 三级取值优先级：数据集(1) > 用例编排 set_field(2) > 接口字段默认值(3，此处组装的兜底值)
        body = build_request_body(api)
        # 优先级 1（数据集）：行值覆盖同名字段（动态绑定 ${} 字段除外，见 apply_row_overrides）。
        # 快照保真：用户编辑过的单元格（行值 != origin）无条件覆盖全部节点；
        # 未编辑的快照值仅作用于"配置值 == origin"的节点，异值节点保留自身配置
        node_row_vars = filter_row_vars_for_node(
            self.row_vars, self.row_origins, api,
            config.pre_process if config else None)
        if node_row_vars:
            body = apply_row_overrides(body, node_row_vars)
        headers = deepcopy(self.http_client.headers or {})

        # PreProcessor 持有 db_client，使 set_field 的值能通过 ${db.query_value(...)} 从 DB 取值
        # set_field 内部同规则：非动态字面量让位行值（优先级 1），${} 动态绑定照常求值
        preprocessor = PreProcessor(self.context.to_dict(), self.db_client, row_vars=node_row_vars)
        # 对组装后的 body 递归求值 ${...}（覆盖 array/object 字段中嵌入的表达式）；
        # 未定义变量保留占位符，不替换为空，留给后续前置处理或下游注入
        body = preprocessor.expr.evaluate(body)
        if config and config.pre_process:
            # 传入 self.context.extracted（引用），set_field 求值后的值同步到上下文，
            # 使后续 post_extract 的 SQL 和后续节点的 ${xxx} 能引用到
            body = preprocessor.process(body, config.pre_process, self.context.extracted)
            # 前置处理可能往上下文写入新变量，对 body 再求值一次，注入此时已具备的变量
            # （保留仍未定义的占位符原样，便于排查未注入字段）
            body = preprocessor.expr.evaluate(body)
        # array/object 字段经表达式求值后仍是字符串（如 "[${id}]" → "[123]"），
        # 转回原生 JSON 类型，使接口收到的是列表/对象而非字符串
        body = coerce_json_strings(body)
        # 按接口字段定义强转标量类型，避免表达式求值后类型丢失
        # （如 ${order_id} 提取为 int，但字段定义为 string 时应转字符串发送）
        body = apply_field_types(body, api)
        # 提取 file 类型字段：从 body 中剥离 file 字段，单独组装到 multipart files
        # file 字段不参与 JSON body，避免被 JSON 序列化为字符串
        body, file_fields = pop_file_fields_from_body(body, api)
        # headers 中支持表达式
        for k, v in list(headers.items()):
            if isinstance(v, str) and "${" in v:
                headers[k] = preprocessor.expr.evaluate(v)

        # 2. 发送请求（file_fields 非空时走 multipart 通道）
        status_code, response_data, err = self._send_request(api, body, headers, file_fields)
        elapsed = int((time.time() - start_ts) * 1000)

        # 3. 后置提取（支持从响应或 DB 提取变量到上下文）
        if config and config.post_extract and response_data is not None:
            # 注入当前已提取变量，供 source=db 的 SQL 引用
            self.extractor.set_extracted_vars(self.context.extracted)
            extracted = self.extractor.extract(response_data, config.post_extract)
            self.context.update_extracted(extracted)

        # 4. 断言
        assertion_results: list[dict] = []
        if config and config.assertions:
            engine = AssertionEngine(self.context.to_dict(), self.db_client)
            assertion_results = engine.evaluate_all(response_data, status_code, elapsed, config.assertions)

        step_passed = (err is None) and all(r["pass"] for r in assertion_results)

        # 5. 产出步骤事件（落库/收集交给 sink）
        self.sink.record_step(StepResult(
            execution_id=execution_id, node_id=node_id,
            api_name=api.name, api_path=api.path, api_method=api.method,
            request_headers=headers, request_body=body,
            response_status=status_code,
            # 请求异常（超时/连接失败等）时 err 有值但响应体可能为 None，
            # 落 {"error": err} 让步骤记录（及失败通知）可读到具体原因
            response_body=(
                {"error": err} if err is not None
                else response_data if isinstance(response_data, (dict, list))
                else {"text": str(response_data)}
            ),
            response_time_ms=elapsed, started_at=started_at, ended_at=datetime.now(),
            status="success" if step_passed else "failed",
            assertions=[
                AssertionResult(
                    type=ar["type"], rule_config=ar, passed=ar["pass"],
                    actual=ar.get("actual"), expected=ar.get("expected"),
                    message=ar.get("message", ""),
                ) for ar in assertion_results
            ],
        ))

        # 节点配置的等待时间（ms），由调用方在节点间应用
        wait_ms = getattr(config, "wait_after_ms", 0) or 0 if config else 0
        return step_passed, wait_ms

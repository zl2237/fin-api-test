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
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

# 复用现有项目代码（异常分类已收敛至 services.request_sender）
from utils.http_client import HttpClient

from .. import (
    models,
    path_setup,  # noqa: F401
)
from ..services.notifier import send_notify
from ..services.request_sender import send_request
from ..services.runtime_service import build_db_client, build_http_client, login
from .assertion_engine import AssertionEngine
from .context import ExecutionContext
from .events import AssertionResult, DbSink, ExecutionSink, StepResult
from .extractor import Extractor
from .prepare_request import prepare_request
from .topo import topo_order


class DagExecutor:
    def __init__(self, db: Session, case: models.TestCase, env: models.Environment,
                 execution_record: models.ExecutionRecord | None = None,
                 sink: ExecutionSink | None = None,
                 row_vars: dict[str, Any] | None = None,
                 suite_vars: dict[str, Any] | None = None,
                 suppress_notify: bool = False):
        self.db = db
        self.case = case
        self.env = env
        # 业务变量已退役：测试数据来源唯一为数据集（row_vars 为数据集单套数据，
        # 数据集域第 3 层自动解析）；套件注入：suite_vars 为上游成员白名单快照
        # （单独执行不传，行为不变）
        self.context = ExecutionContext(row_vars=row_vars,
                                         suite_vars=suite_vars)
        # 数据驱动批量执行时抑制逐条通知（由聚合器等全部完成后发一条汇总）
        self.suppress_notify = suppress_notify
        # 数据集行值原始引用：数据集域取值处（prepare_request 第 3 层解析）
        self.row_vars = row_vars or None
        self.extractor = Extractor()
        self.http_client: HttpClient | None = None
        self.db_client: Any = None
        # 并发执行场景下由外部预先创建 record 并传入，避免后台线程重复创建
        self._precreated_record = execution_record
        # 事件出口：默认落库；测试/dry-run 注入内存 sink（持久化接缝）
        self.sink: ExecutionSink = sink or DbSink(db)

    # ---------- 请求发送 ----------
    def _send_request(self, api: models.ApiDefinition, body: Any, headers: dict,
                      file_fields: list[tuple[str, str]] | None = None) -> tuple[int, Any, str | None]:
        """委托共享发送器（与单接口调试同一实现），返回 (status_code, response_body, error_msg)。

        headers 为 prepare_request 组装产物（环境公共头 + 接口 headers_template 覆盖 +
        ${} 求值），发送期间临时替换 client.headers 使接口级 Content-Type 真正生效
        （表单接口据此走表单编码），发完恢复。
        """
        # 超时时间取环境配置（向后兼容：未配置时默认 15 秒）
        timeout = getattr(self.env, "timeout", None) or 15
        return send_request(self.db, self.http_client, api, body,
                            file_fields=file_fields, timeout=timeout, headers=headers)

    # ---------- 执行入口 ----------
    def _terminated(self, execution_id: int) -> bool:
        """查询手动终止标记（每步后 sink 已 commit，本查询开新事务能看到
        terminate API 的跨会话提交；REPEATABLE READ 下同事务快照不可见）。"""
        status = (self.db.query(models.ExecutionRecord.status)
                  .filter(models.ExecutionRecord.id == execution_id).scalar())
        return status == "terminated"

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
            order, leftover = topo_order(dag)
            nodes_map = {n["id"]: n for n in dag.get("nodes", [])}

            terminated = False
            for idx, node_id in enumerate(order):
                # 手动终止检查点：terminate API 已提交 terminated（每步后 sink
                # commit 开新事务，此查询能读到外部提交）→ 剩余节点并入 leftover
                # 同口径统计，最终保留 terminated 状态不被汇总覆盖
                if self._terminated(record.id):
                    terminated = True
                    leftover = leftover + order[idx:]
                    break
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

            if terminated:
                record.status = "terminated"
                record.summary = {
                    "total": total_passed + total_failed, "passed": total_passed,
                    "failed": total_failed, "leftover": leftover, "error": "手动终止",
                }
            else:
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
            # 发送企微通知（执行人/项目名取数与门控都在 notifier，见其模块注释）
            if self.suppress_notify:
                print("[通知发送] 跳过逐条通知：数据驱动批量执行由聚合器汇总发送")
            else:
                send_notify(self.db, self.env, self.case, record)
        return record

    # ---------- 单节点执行 ----------
    def _resolve_node_config(self, node_id: str):
        """节点配置来源：用例当前 CaseNodeConfig（编排唯一来源，无快照覆盖）。"""
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
                pre_process=(config.pre_process if config else None) or None,
                post_extract=(config.post_extract if config else None) or None,
                extracted_vars={},
            ))
            return False, 0

        # 1. 组装请求（三级优先级与编排顺序统一在 prepare_request，见其模块注释）；
        # 前置处理 exec_sql 执行失败等组装期异常在这里兜底为失败步骤（原因可见），
        # 避免异常冒泡到 execute() 导致本节点无步骤记录
        assert self.http_client is not None  # execute() 前已 build_http_client，收窄 None 分支
        try:
            parts = prepare_request(api, config, context=self.context,
                                    row_vars=self.row_vars,
                                    base_headers=self.http_client.headers,
                                    db_client=self.db_client)
        except Exception as e:
            self.sink.record_step(StepResult(
                execution_id=execution_id, node_id=node_id,
                api_name=api.name, api_path=api.path, api_method=api.method,
                request_headers={}, request_body={},
                response_status=0, response_body={"error": f"请求组装/前置处理失败: {e}"},
                response_time_ms=0, started_at=started_at, ended_at=datetime.now(),
                status="failed",
                pre_process=(config.pre_process if config else None) or None,
                post_extract=(config.post_extract if config else None) or None,
                extracted_vars={},
            ))
            return False, 0
        body, headers, file_fields = parts.body, parts.headers, parts.file_fields

        # 2~4. 发送请求 → 后置提取 → 断言；请求层失败（err 非空：HTTP 状态码/
        # 业务码失败、超时、连接异常）按环境配置自动重试同一请求——被测系统
        # 异步同步（如 ES 分钟级延迟）导致的瞬时失败，稍后原样重发即可恢复，
        # 与报告页手工重放语义一致。断言失败不重试：避免掩盖真实断言问题，
        # 也降低写接口重复提交风险。
        retry_limit = max(0, getattr(self.env, "node_retry_count", 0) or 0)
        retry_interval = max(1, getattr(self.env, "node_retry_interval", 1) or 1)
        status_code, response_data, err = 0, None, None
        extracted: dict = {}
        assertion_results: list[dict] = []
        step_passed = False
        retry_count = 0
        for attempt in range(retry_limit + 1):
            if attempt:
                time.sleep(retry_interval)
                retry_count = attempt
            # 2. 发送请求（file_fields 非空时走 multipart 通道）
            status_code, response_data, err = self._send_request(api, body, headers, file_fields)
            elapsed = int((time.time() - start_ts) * 1000)
            if err is not None and attempt < retry_limit:
                continue  # 请求层失败且仍有重试额度：间隔后原样重发
            # 成功 / 断言路径 / 重试额度耗尽：提取与断言后收尾

            # 3. 后置提取（支持从响应或 DB 提取变量到上下文）
            if config and config.post_extract and response_data is not None:
                # 注入当前已提取变量，供 source=db 的 SQL 引用
                self.extractor.set_extracted_vars(self.context.extracted)
                extracted = self.extractor.extract(response_data, config.post_extract)
                self.context.update_extracted(extracted)

            # 4. 断言
            if config and config.assertions:
                engine = AssertionEngine(self.context.to_dict(), self.db_client)
                assertion_results = engine.evaluate_all(response_data, status_code, elapsed, config.assertions)

            step_passed = (err is None) and all(r["pass"] for r in assertion_results)
            break

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
            pre_process=(config.pre_process if config else None) or None,
            post_extract=(config.post_extract if config else None) or None,
            extracted_vars=extracted,
            retry_count=retry_count,
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

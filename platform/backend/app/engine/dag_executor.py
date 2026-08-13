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
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from .. import path_setup  # noqa: F401
from .. import models
from ..services.runtime_service import build_http_client, login, build_db_client
from ..services.body_builder import build_request_body, pop_file_fields_from_body
from ..services.notifier import send_notify
from .context import ExecutionContext
from .preprocessor import PreProcessor
from .extractor import Extractor
from .assertion_engine import AssertionEngine
from .type_coercer import coerce_json_strings, apply_field_types

# 复用现有项目代码
from utils.http_client import HttpClient
from utils.exceptions import HttpStatusError, BusinessError, AuthError, HttpTimeoutError, JsonParseError


class DagExecutor:
    def __init__(self, db: Session, case: models.TestCase, env: models.Environment,
                 execution_record: Optional[models.ExecutionRecord] = None):
        self.db = db
        self.case = case
        self.env = env
        # 业务变量从 variables 读取（与登录/通知配置解耦）
        self.context = ExecutionContext(env_vars=env.variables or {})
        self.extractor = Extractor()
        self.http_client: Optional[HttpClient] = None
        self.db_client = None
        # 并发执行场景下由外部预先创建 record 并传入，避免后台线程重复创建
        self._precreated_record = execution_record

    # ---------- 拓扑排序 ----------
    @staticmethod
    def _topo_sort(dag: Dict[str, Any]) -> Tuple[List[str], List[str]]:
        """返回 (执行顺序节点id列表, 因环/断链未执行的节点id列表)"""
        nodes = dag.get("nodes", [])
        edges = dag.get("edges", [])
        ids = [n["id"] for n in nodes]
        in_degree = {nid: 0 for nid in ids}
        adj: Dict[str, List[str]] = {nid: [] for nid in ids}
        for e in edges:
            src, tgt = e.get("source"), e.get("target")
            if src in adj and tgt in in_degree:
                adj[src].append(tgt)
                in_degree[tgt] += 1
        # 保持稳定顺序：按节点 id 字典序入队
        queue = sorted([nid for nid, d in in_degree.items() if d == 0])
        order: List[str] = []
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
    def _send_request(self, api: models.ApiDefinition, body: Any, headers: Dict,
                      file_fields: Optional[List[Tuple[str, str]]] = None) -> Tuple[int, Any, Optional[str]]:
        """返回 (status_code, response_body, error_msg)

        :param file_fields: file 类型字段列表 [(field_name, file_id), ...]
                            非空时构建 multipart 请求，文件从文件中心按 file_id 取
        """
        # 超时时间取环境配置（向后兼容：未配置时默认 15 秒）
        timeout = getattr(self.env, "timeout", None) or 15
        files_payload: list = []
        try:
            if api.method.upper() == "GET":
                resp = self.http_client.get(api.path, params=body, timeout=timeout)
            elif file_fields:
                # 含文件字段：构建 multipart/form-data
                files_payload = self._build_multipart_files(file_fields)
                if files_payload:
                    # multipart 请求去掉 Content-Type，让 requests 自动生成 boundary
                    saved_headers = self.http_client.headers
                    multipart_headers = {k: v for k, v in saved_headers.items()
                                         if k.lower() != "content-type"}
                    self.http_client.headers = multipart_headers
                    # multipart form_data：dict 直接用，list（数组请求体）取首元素
                    if isinstance(body, dict):
                        form_data = body
                    elif isinstance(body, list) and body and isinstance(body[0], dict):
                        form_data = body[0]
                    else:
                        form_data = None
                    try:
                        resp = self.http_client.post_multipart(
                            api.path, data=form_data, files=files_payload, timeout=timeout
                        )
                    finally:
                        self.http_client.headers = saved_headers
                else:
                    resp = self.http_client.post(api.path, json=body, timeout=timeout)
            else:
                resp = self.http_client.post(api.path, json=body, timeout=timeout)
            # HttpClient 成功返回即 HTTP 200 且业务码 200
            return 200, resp, None
        except HttpStatusError as e:
            return e.status_code, {"error": str(e)}, str(e)
        except BusinessError as e:
            return 200, {"code": e.code, "msg": e.msg, "error": str(e)}, str(e)
        except (AuthError, HttpTimeoutError, JsonParseError) as e:
            return 0, {"error": str(e)}, str(e)
        except Exception as e:
            # 未预期的请求异常（如连接错误、SSL 错误等），记录日志便于排查
            print(f"[请求异常] {api.method} {api.path} 未预期异常: {e}")
            return 0, {"error": str(e)}, str(e)
        finally:
            # 关闭 multipart 请求中打开的文件句柄
            if files_payload:
                self._close_multipart_files(files_payload)

    def _build_multipart_files(self, file_fields: List[Tuple[str, str]]) -> list:
        """将 file_id 列表转为 requests 的 files 参数格式。

        返回 [(field_name, (filename, fileobj, content_type)), ...]
        文件不存在或读取失败的字段跳过并打印日志。
        """
        from ..routers.files import _resolve_physical_path

        files_payload: list = []
        for field_name, file_id_str in file_fields:
            try:
                file_id = int(file_id_str)
            except (ValueError, TypeError):
                print(f"[文件上传] file_id 非法: {file_id_str}，跳过")
                continue
            f = self.db.query(models.TestFile).filter(models.TestFile.id == file_id).first()
            if not f:
                print(f"[文件上传] file_id={file_id} 不存在，跳过")
                continue
            physical = _resolve_physical_path(f.storage_path)
            if not physical.exists():
                print(f"[文件上传] 物理文件丢失: {f.storage_path}，跳过")
                continue
            fileobj = open(physical, "rb")
            files_payload.append((field_name, (f.name, fileobj, f.content_type)))
        return files_payload

    def _close_multipart_files(self, files_payload: list) -> None:
        """关闭 multipart 请求中打开的文件句柄"""
        for item in files_payload:
            try:
                # 元组格式 (field_name, (filename, fileobj, content_type))
                fileobj = item[1][1] if isinstance(item[1], tuple) else None
                if fileobj:
                    fileobj.close()
            except Exception:
                pass

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
                    # 默认失败即停止
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
            send_notify(self.env, self.case, record, executor_name=executor_name)
        return record

    # ---------- 单节点执行 ----------
    def _execute_node(self, execution_id: int, node_id: str, node: Dict) -> Tuple[bool, int]:
        """执行单个节点。返回 (是否通过, 节点配置的 wait_after_ms)。
        wait_after_ms 表示当前节点执行完后到下一节点请求前的等待毫秒数，由调用方在节点间应用。
        """
        config = self.db.query(models.CaseNodeConfig).filter(
            models.CaseNodeConfig.case_id == self.case.id,
            models.CaseNodeConfig.node_id == node_id,
        ).first()

        api = None
        if config and config.api_id:
            api = self.db.query(models.ApiDefinition).filter(models.ApiDefinition.id == config.api_id).first()

        started_at = datetime.now()
        start_ts = time.time()

        # 无配置或无接口定义 → 记录失败步骤
        if not api:
            step = models.StepRecord(
                execution_id=execution_id, node_id=node_id,
                api_name=node.get("data", {}).get("label") if isinstance(node.get("data"), dict) else node_id,
                api_path="", api_method="",
                request_headers={}, request_body={},
                response_status=0, response_body={"error": "节点未绑定接口或配置缺失"},
                response_time_ms=0, started_at=started_at, ended_at=datetime.now(),
                status="failed",
            )
            self.db.add(step)
            self.db.commit()
            self.db.refresh(step)
            return False, 0

        # 1. 准备请求体 / 请求头
        # 优先用 ApiField 组装（新版本字段级配置）；无 fields 时回退到 request_template
        body = build_request_body(api)
        headers = deepcopy(self.http_client.headers or {})

        # PreProcessor 持有 db_client，使 set_field 的值能通过 ${db.query_value(...)} 从 DB 取值
        preprocessor = PreProcessor(self.context.to_dict(), self.db_client)
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
        assertion_results: List[Dict] = []
        if config and config.assertions:
            engine = AssertionEngine(self.context.to_dict(), self.db_client)
            assertion_results = engine.evaluate_all(response_data, status_code, elapsed, config.assertions)

        step_passed = (err is None) and all(r["pass"] for r in assertion_results)

        # 5. 落库步骤
        step = models.StepRecord(
            execution_id=execution_id, node_id=node_id,
            api_name=api.name, api_path=api.path, api_method=api.method,
            request_headers=headers, request_body=body,
            response_status=status_code,
            response_body=response_data if isinstance(response_data, (dict, list)) else {"text": str(response_data)},
            response_time_ms=elapsed, started_at=started_at, ended_at=datetime.now(),
            status="success" if step_passed else "failed",
        )
        self.db.add(step)
        self.db.commit()
        self.db.refresh(step)

        # 6. 落库断言
        for ar in assertion_results:
            arec = models.AssertionRecord(
                step_id=step.id, rule_type=ar["type"], rule_config=ar,
                result=ar["pass"], actual_value=str(ar.get("actual")),
                expected_value=str(ar.get("expected")), message=ar.get("message", ""),
            )
            self.db.add(arec)
        self.db.commit()

        # 节点配置的等待时间（ms），由调用方在节点间应用
        wait_ms = getattr(config, "wait_after_ms", 0) or 0 if config else 0
        return step_passed, wait_ms

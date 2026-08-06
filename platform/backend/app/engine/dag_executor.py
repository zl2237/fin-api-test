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
from jsonpath_ng import parse as jsonpath_parse

from .. import path_setup  # noqa: F401
from .. import models
from .context import ExecutionContext
from .preprocessor import PreProcessor
from .extractor import Extractor
from .assertion_engine import AssertionEngine

# 复用现有项目代码
from utils.http_client import HttpClient
from utils.exceptions import HttpStatusError, BusinessError, AuthError, HttpTimeoutError, JsonParseError


def _extract_by_jsonpath(data: Any, path: str) -> Any:
    try:
        matches = jsonpath_parse(path).find(data)
        return matches[0].value if matches else None
    except Exception:
        return None


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

    # ---------- 客户端准备 ----------
    def _build_http_client(self) -> HttpClient:
        client = HttpClient(base_url=self.env.base_url)
        client.headers = deepcopy(self.env.common_headers or {}) or {"Content-Type": "application/json"}
        return client

    def _login(self, client: HttpClient):
        """按 env.login_config 配置登录并注册 token 刷新回调；未配置则跳过"""
        login_cfg: Dict[str, Any] = self.env.login_config or {}
        login_path = login_cfg.get("login_path", "/api/home/login/userLogin")
        login_body = login_cfg.get("login_body")
        token_jsonpath = login_cfg.get("token_jsonpath", "$.data.token")
        auth_header_name = login_cfg.get("auth_header_name", "Authorization")
        # 鉴权头值模板：支持 ${token} 和 ${timestamp} 占位符
        # 默认 ${token}（直接注入）；可配为 Bearer ${token}、${token}_${timestamp} 等
        auth_header_value_template = login_cfg.get("auth_header_value_template") or "${token}"
        if not login_body:
            return

        def _build_header_value(token: str) -> str:
            """按模板渲染鉴权头值"""
            return (auth_header_value_template
                    .replace("${token}", str(token))
                    .replace("${timestamp}", str(int(time.time()))))

        def _do_login():
            # 登录时带任意 Authorization 头跳过验证码校验，登录成功后会被真实 token 覆盖
            client.set_header(auth_header_name, "skip-captcha-placeholder")
            resp = client.post(login_path, json=login_body)
            token = _extract_by_jsonpath(resp, token_jsonpath)
            if token:
                client.set_header(auth_header_name, _build_header_value(token))
            return token

        # 首次登录失败时给出清晰错误，避免 500；后续 401 重登失败由回调吞掉
        try:
            _do_login()
        except Exception as e:
            raise RuntimeError(f"登录失败：{e}") from e

        def refresh():
            try:
                return _do_login()
            except Exception:
                return None

        client.set_token_refresh_callback(refresh)

    def _build_db_client(self):
        cfg = self.env.db_config or {}
        if not cfg.get("host"):
            return None
        # 延迟导入，避免无 DB 环境启动报错
        try:
            from db.db_client import DBClient
            return DBClient(
                host=cfg.get("host"),
                port=int(cfg.get("port", 3306)),
                user=cfg.get("user", ""),
                password=cfg.get("password", ""),
                database=cfg.get("database", ""),
            )
        except Exception:
            return None

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

    # ---------- 请求体构建 ----------
    def _build_request_body(self, api: models.ApiDefinition) -> Dict[str, Any]:
        """
        优先用 ApiField 组装请求体（支持点号嵌套路径）；
        无 fields 时回退到 request_template（兼容旧数据）。
        """
        fields = getattr(api, "fields", None) or []
        if not fields:
            return deepcopy(api.request_template or {})

        body: Dict[str, Any] = {}
        for f in fields:
            if not f.key:
                continue
            # 解析默认值：支持 JSON（array/object 类型）、表达式、纯字符串
            val = self._parse_field_value(f.default_value, f.field_type)
            # 按点号路径设置到嵌套 dict
            self._set_nested(body, f.key, val)
        return body

    @staticmethod
    def _parse_field_value(raw: Optional[str], field_type: str) -> Any:
        """解析字段默认值"""
        if raw is None or raw == "":
            return "" if field_type == "string" else None
        # 含 ${} 表达式的值：先保留原始字符串，待 expr.evaluate 求值后
        # 再由 _coerce_json_strings 转回 array/object 原生类型
        if "${" in raw:
            return raw
        if field_type in ("array", "object"):
            try:
                import json
                return json.loads(raw)
            except Exception:
                return raw
        if field_type == "int":
            try:
                return int(raw)
            except Exception:
                return raw
        if field_type == "bool":
            return raw.lower() in ("true", "1", "yes")
        return raw  # string 类型，保留表达式 ${...} 由后续 preprocessor 求值

    @staticmethod
    def _coerce_json_strings(obj: Any) -> Any:
        """递归把求值后形如 JSON 的字符串转回原生类型。
        例如 array 字段 "[${id}]" 求值后为 "[123]" 字符串，转回 ["123"] 列表。
        仅对形如 [...] / {...} 的字符串尝试，失败则原样返回。"""
        import json
        if isinstance(obj, dict):
            return {k: DagExecutor._coerce_json_strings(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [DagExecutor._coerce_json_strings(v) for v in obj]
        if isinstance(obj, str):
            s = obj.strip()
            if (s.startswith("[") and s.endswith("]")) or (s.startswith("{") and s.endswith("}")):
                try:
                    return json.loads(s)
                except Exception:
                    return obj
        return obj

    @staticmethod
    def _set_nested(target: Dict[str, Any], path: str, value: Any):
        """按点号路径设置嵌套 dict 值"""
        keys = path.split(".")
        cur = target
        for k in keys[:-1]:
            if k not in cur or not isinstance(cur[k], dict):
                cur[k] = {}
            cur = cur[k]
        cur[keys[-1]] = value

    # ---------- 请求发送 ----------
    def _send_request(self, api: models.ApiDefinition, body: Any, headers: Dict) -> Tuple[int, Any, Optional[str]]:
        """返回 (status_code, response_body, error_msg)"""
        # 超时时间取环境配置（向后兼容：未配置时默认 15 秒）
        timeout = getattr(self.env, "timeout", None) or 15
        try:
            if api.method.upper() == "GET":
                resp = self.http_client.get(api.path, params=body, timeout=timeout)
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
            return 0, {"error": str(e)}, str(e)

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

        self.http_client = self._build_http_client()
        self.db_client = self._build_db_client()
        # extractor / assertion_engine 共享 db_client，供 source=db 提取与 db_* 断言使用
        self.extractor.db_client = self.db_client

        total_passed = 0
        total_failed = 0
        error_msg = None
        try:
            # 登录在 try 内，失败时记为执行失败而非 500
            self._login(self.http_client)
            dag = self.case.dag_config or {"nodes": [], "edges": []}
            order, leftover = self._topo_sort(dag)
            nodes_map = {n["id"]: n for n in dag.get("nodes", [])}

            for node_id in order:
                step_passed = self._execute_node(record.id, node_id, nodes_map.get(node_id, {"id": node_id}))
                if step_passed:
                    total_passed += 1
                else:
                    total_failed += 1
                    # 默认失败即停止
                    break

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
                except Exception:
                    pass
            # 关闭 HTTP session，避免连续执行多个用例时连接池累积导致后续请求超时
            if self.http_client and self.http_client.session:
                try:
                    self.http_client.session.close()
                except Exception:
                    pass
            # 发送企微通知（notify_config 配置了 webhook 时）
            self._send_notify(record)
        return record

    def _send_notify(self, record: models.ExecutionRecord) -> None:
        """执行完成后发送企微通知，失败不影响主流程"""
        try:
            notify_config = self.env.notify_config or {}
            webhook = notify_config.get("webhook")
            if not webhook:
                return
            from utils.wecom_util import WeComRobot
            status_text = "✅ 通过" if record.status == "success" else "❌ 失败"
            summary = record.summary or {}
            duration = ""
            if record.started_at and record.ended_at:
                secs = (record.ended_at - record.started_at).total_seconds()
                duration = f"（耗时 {secs:.1f}s）"
            content = (
                f"**用例执行通知**\n"
                f"> 用例：{self.case.name}\n"
                f"> 状态：{status_text}{duration}\n"
                f"> 通过/总数：{summary.get('passed', 0)}/{summary.get('total', 0)}\n"
                f"> 环境：{self.env.name}\n"
                f"> 时间：{record.ended_at.strftime('%Y-%m-%d %H:%M:%S') if record.ended_at else ''}"
            )
            WeComRobot(webhook).send_markdown("用例执行通知", content)
        except Exception as e:
            # 通知失败不影响执行结果
            print(f"[通知发送] 企微通知发送失败（忽略）: {e}")

    # ---------- 单节点执行 ----------
    def _execute_node(self, execution_id: int, node_id: str, node: Dict) -> bool:
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
            return False

        # 1. 准备请求体 / 请求头
        # 优先用 ApiField 组装（新版本字段级配置）；无 fields 时回退到 request_template
        body = self._build_request_body(api)
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
        body = self._coerce_json_strings(body)
        # headers 中支持表达式
        for k, v in list(headers.items()):
            if isinstance(v, str) and "${" in v:
                headers[k] = preprocessor.expr.evaluate(v)

        # 2. 发送请求
        status_code, response_data, err = self._send_request(api, body, headers)
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

        return step_passed

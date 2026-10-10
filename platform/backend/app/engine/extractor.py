"""后置提取器 v2：从响应或数据库提取变量到节点命名空间注册表。

规则格式：
1. 响应体提取（默认）：{"name": "order_id", "json_path": "$.data.order_id"}
2. 数据库提取：{"name": "order_id", "source": "db",
   "sql": "SELECT order_id FROM sys_order WHERE bl_no={{n_create.bl_no}}", "field": "order_id"}
   - SQL 变量引用为 {{节点.变量}} 占位（旧 ${xxx} 废止）
   - field 可选，未指定取首行首列
   - 查询无结果时按 retry/interval 重查（被测系统接口返回后异步落库，
     提取立即执行常查不到；SQL 错误/引用失败不重试——重试无意义）

提取结果实时写入注册表本节点命名空间：同节点后续规则可经 {{本节点.变量}} 引用。

未取到（jsonpath 未命中 / SQL 执行失败 / 查询无结果 / 值为 NULL 等）时结果值为
{"__error__": 原因}：DagExecutor 据此判节点失败，报告提取页与失败通知据此展示原因
（此前静默 None，SQL 写错也无从排查）。注册表仍写 None，下游 {{引用}} 口径不变。
"""
import time
from typing import Any

from jsonpath_ng import parse

from .param_resolver import render_placeholders
from .variables import ReferenceError, VariableRegistry

EXTRACT_ERROR_KEY = "__error__"


def _err(reason: str) -> dict[str, Any]:
    return {EXTRACT_ERROR_KEY: reason}


def is_extract_error(v: Any) -> bool:
    return isinstance(v, dict) and EXTRACT_ERROR_KEY in v


def _clip(s: Any, n: int = 300) -> str:
    t = str(s).strip()
    return t if len(t) <= n else t[:n] + "…"


class Extractor:
    def __init__(self, db_client=None, retry: int = 0, interval: float = 1):
        self.db_client = db_client
        # DB 提取「查询无结果」的重查次数与间隔：复用环境级失败重试配置
        # （node_retry_count / node_retry_interval），与请求层重试同动机——
        # 被测系统异步落库导致的瞬时查不到，稍后重查即可恢复
        self.retry = max(0, retry)
        self.interval = max(0.1, interval)

    def extract(self, response: Any, rules: list[dict], registry: VariableRegistry,
                self_node: str) -> dict[str, Any]:
        """执行提取规则，产出 {变量名: 值} 并实时注册进本节点命名空间。

        未取到的变量值为 {"__error__": 原因}（is_extract_error 可判）；注册表写 None。
        """
        extracted: dict[str, Any] = {}
        for rule in rules or []:
            name = rule.get("name")
            if not name:
                continue
            if rule.get("source", "response") == "db":
                val = self._extract_from_db(rule, registry, self_node)
            else:
                val = self._extract_from_response(response, rule)
            extracted[name] = val
            # 实时注册：同节点后续规则的 {{本节点.name}} 可引用刚提取的值；
            # 失败时写 None 而非错误对象，下游引用语义保持「无值」
            registry.write(self_node, name, None if is_extract_error(val) else val)
        return extracted

    def _extract_from_response(self, response: Any, rule: dict) -> Any:
        json_path = (rule.get("json_path") or "").strip()
        if not json_path:
            return _err("未配置 jsonpath")
        try:
            matches = parse(json_path).find(response)
        except Exception as e:
            return _err(f"jsonpath 语法错误：{_clip(e, 120)}")
        if not matches:
            return _err(f"jsonpath 未命中：{json_path}")
        return matches[0].value

    def _extract_from_db(self, rule: dict, registry: VariableRegistry, self_node: str) -> Any:
        if not self.db_client:
            return _err("环境未配置数据库连接")
        sql = (rule.get("sql") or "").strip()
        if not sql:
            return _err("SQL 为空")
        try:
            rows = self.db_client.query(render_placeholders(sql, registry))
        except ReferenceError as e:
            return _err(f"引用取值失败：{_clip(e, 200)}")
        except Exception as e:
            return _err(f"SQL 执行失败：{_clip(e)}")
        # 查询无结果：被测系统接口返回后异步落库（如发起付款需求写 sys_pay_demand），
        # 按配置间隔重查；SQL 本身已执行成功，语法错误不会走到这里
        attempts = 0
        while not rows and attempts < self.retry:
            attempts += 1
            time.sleep(self.interval)
            try:
                rows = self.db_client.query(render_placeholders(sql, registry))
            except Exception:
                rows = []
        if not rows:
            suffix = f"（含重查 {attempts} 次）" if attempts else ""
            return _err(f"查询无结果{suffix}")
        # field 去除首尾空格，避免配置 "audit_id " 带空格导致取不到值
        field = (rule.get("field") or "").strip() or None
        first = rows[0]
        if isinstance(first, dict):
            if field:
                if field not in first:
                    cols = ", ".join(list(first)[:8])
                    return _err(f"结果列无 {field}（可用列：{cols}）")
                val = first[field]
            else:
                val = next(iter(first.values())) if first else None
        else:
            val = first
        if val is None:
            return _err("结果值为 NULL")
        return val

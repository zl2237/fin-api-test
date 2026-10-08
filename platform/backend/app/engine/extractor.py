"""后置提取器 v2：从响应或数据库提取变量到节点命名空间注册表。

规则格式：
1. 响应体提取（默认）：{"name": "order_id", "json_path": "$.data.order_id"}
2. 数据库提取：{"name": "order_id", "source": "db",
   "sql": "SELECT order_id FROM sys_order WHERE bl_no={{n_create.bl_no}}", "field": "order_id"}
   - SQL 变量引用为 {{节点.变量}} 占位（旧 ${xxx} 废止）
   - field 可选，未指定取首行首列

提取结果实时写入注册表本节点命名空间：同节点后续规则可经 {{本节点.变量}} 引用。
"""
from typing import Any

from jsonpath_ng import parse

from .param_resolver import render_placeholders
from .variables import ReferenceError, VariableRegistry


class Extractor:
    def __init__(self, db_client=None):
        self.db_client = db_client

    def extract(self, response: Any, rules: list[dict], registry: VariableRegistry,
                self_node: str) -> dict[str, Any]:
        """执行提取规则，产出 {变量名: 值} 并实时注册进本节点命名空间。"""
        extracted: dict[str, Any] = {}
        for rule in rules or []:
            name = rule.get("name")
            if not name:
                continue
            if rule.get("source", "response") == "db":
                extracted[name] = self._extract_from_db(rule, registry, self_node)
            else:
                extracted[name] = self._extract_from_response(response, rule)
            # 实时注册：同节点后续规则的 {{本节点.name}} 可引用刚提取的值
            registry.write(self_node, name, extracted[name])
        return extracted

    def _extract_from_response(self, response: Any, rule: dict) -> Any:
        json_path = rule.get("json_path")
        if not json_path:
            return None
        try:
            matches = parse(json_path).find(response)
            return matches[0].value if matches else None
        except Exception:
            return None

    def _extract_from_db(self, rule: dict, registry: VariableRegistry, self_node: str) -> Any:
        if not self.db_client:
            return None
        sql = (rule.get("sql") or "").strip()
        if not sql:
            return None
        try:
            rows = self.db_client.query(render_placeholders(sql, registry))
        except (ReferenceError, Exception):
            return None
        if not rows:
            return None
        # field 去除首尾空格，避免配置 "audit_id " 带空格导致取不到值
        field = (rule.get("field") or "").strip() or None
        first = rows[0]
        if isinstance(first, dict):
            if field:
                return first.get(field)
            return next(iter(first.values())) if first else None
        return first

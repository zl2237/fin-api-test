"""后置提取器：从响应或数据库中提取变量到上下文。

支持的规则格式：
1. 从响应体提取（默认）：
   {"name": "order_id", "json_path": "$.data.order_id"}
2. 从数据库提取：
   {"name": "order_id", "source": "db", "sql": "SELECT order_id FROM sys_order WHERE bl_no='${bl_no}'", "field": "order_id"}
   - source=db 时执行 SQL，取第一行 field 字段的值存入上下文
   - field 可选，未指定时取第一行第一列
   - SQL 中支持 ${context.xxx} / ${xxx} 变量引用
"""
import re
from typing import Any, Dict, List, Optional

from jsonpath_ng import parse


class Extractor:
    def __init__(self, db_client=None):
        self.db_client = db_client

    def extract(self, response: Any, rules: List[Dict]) -> Dict[str, Any]:
        extracted: Dict[str, Any] = {}
        for rule in rules or []:
            name = rule.get("name")
            if not name:
                continue
            source = rule.get("source", "response")
            if source == "db":
                extracted[name] = self._extract_from_db(rule)
            else:
                extracted[name] = self._extract_from_response(response, rule)
        return extracted

    def _extract_from_response(self, response: Any, rule: Dict) -> Any:
        json_path = rule.get("json_path")
        if not json_path:
            return None
        try:
            matches = parse(json_path).find(response)
            if matches:
                # 多匹配时取第一个，多值可扩展 rule.multiple
                return matches[0].value
            return None
        except Exception:
            return None

    def _extract_from_db(self, rule: Dict) -> Any:
        if not self.db_client:
            return None
        sql = rule.get("sql", "")
        sql = self._inject_vars(sql)
        if not sql.strip():
            return None
        try:
            rows = self.db_client.query(sql)
        except Exception:
            return None
        if not rows:
            return None
        field = rule.get("field")
        first = rows[0]
        if isinstance(first, dict):
            if field:
                return first.get(field)
            # 未指定 field → 取第一列
            return next(iter(first.values())) if first else None
        return first

    def _inject_vars(self, sql: str) -> str:
        """把 ${context.xxx} / ${xxx} 替换为已提取变量值，字符串做防注入转义。

        注意：extractor 运行时，上下文变量由 dag_executor 维护（context.update_extracted），
        当前批次提取的变量还未写入 context，因此仅能引用此前步骤已提取的变量。
        dag_executor 会把已提取变量通过 context 传入。
        """
        # 此处 self._vars 由 extract 调用前通过 set_context 注入
        extracted = getattr(self, "_vars", {})

        def repl(m):
            key = m.group(1).strip()
            if key.startswith("context."):
                key = key[len("context."):]
            elif key.startswith("extracted."):
                key = key[len("extracted."):]
            val = extracted.get(key, m.group(0))
            if isinstance(val, str):
                return "'" + val.replace("'", "''") + "'"
            if val is None:
                return "NULL"
            return str(val)

        return re.sub(r"\$\{([^}]+)\}", repl, sql)

    def set_extracted_vars(self, vars: Dict[str, Any]):
        """供 dag_executor 在每步提取前注入当前已提取的变量，供 SQL 引用"""
        self._vars = vars

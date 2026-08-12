"""后置提取器：从响应或数据库中提取变量到上下文。

支持的规则格式：
1. 从响应体提取（默认）：
   {"name": "order_id", "json_path": "$.data.order_id"}
2. 从数据库提取：
   {"name": "order_id", "source": "db", "sql": "SELECT order_id FROM sys_order WHERE bl_no='${bl_no}'", "field": "order_id"}
   - source=db 时执行 SQL，取第一行 field 字段的值存入上下文
   - field 可选，未指定时取第一行第一列
   - SQL 中支持 ${xxx} 变量引用（${context.xxx} 兼容旧写法）
"""
from typing import Any, Dict, List

from jsonpath_ng import parse

from .expression import inject_sql_vars


class Extractor:
    def __init__(self, db_client=None):
        self.db_client = db_client

    def extract(self, response: Any, rules: List[Dict]) -> Dict[str, Any]:
        extracted: Dict[str, Any] = {}
        # 初始化 _vars（若未通过 set_extracted_vars 设置）
        if not hasattr(self, "_vars"):
            self._vars = {}
        for rule in rules or []:
            name = rule.get("name")
            if not name:
                continue
            source = rule.get("source", "response")
            if source == "db":
                extracted[name] = self._extract_from_db(rule)
            else:
                extracted[name] = self._extract_from_response(response, rule)
            # 实时更新 _vars，使同一节点后续 post_extract 规则能引用刚提取的变量
            self._vars[name] = extracted[name]
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
        # field 去除首尾空格，避免配置 "audit_id " 带空格导致 first.get 取不到值
        field = (rule.get("field") or "").strip() or None
        first = rows[0]
        if isinstance(first, dict):
            if field:
                return first.get(field)
            # 未指定 field → 取第一列
            return next(iter(first.values())) if first else None
        return first

    def _inject_vars(self, sql: str) -> str:
        """把 ${xxx} 替换为已提取变量值，字符串做防注入转义。

        注意：extractor 运行时，上下文变量由 dag_executor 维护（context.update_extracted），
        当前批次提取的变量还未写入 context，因此仅能引用此前步骤已提取的变量。
        dag_executor 会把已提取变量通过 context 传入。
        """
        # 委托公共函数，消除三处重复的转义逻辑
        return inject_sql_vars(sql, getattr(self, "_vars", {}))

    def set_extracted_vars(self, vars: Dict[str, Any]):
        """供 dag_executor 在每步提取前注入当前已提取的变量，供 SQL 引用"""
        self._vars = vars

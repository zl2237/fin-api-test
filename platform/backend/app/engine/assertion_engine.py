"""
断言引擎。

支持类型：
- json_path_equals              JSON Path 取值等于期望
- json_path_not_equals          JSON Path 取值不等于期望
- json_path_contains            JSON Path 取值包含期望（字符串/列表）
- json_path_exists              JSON Path 路径存在
- json_path_not_empty           JSON Path 取值非空
- json_path_match_regex         JSON Path 取值匹配正则
- json_path_type_equals         JSON Path 取值类型校验（string/int/bool/array/object/null）
- response_status_equals        HTTP 状态码等于期望
- response_time_less_than       响应时间小于期望(ms)
- db_query_equals               数据库查询指定字段等于期望（支持 field 参数取单值）
- db_query_not_equals           数据库查询指定字段不等于期望
- db_query_not_empty            数据库查询结果非空
- db_query_count_equals         数据库查询行数等于期望
- db_query_count_greater_than   数据库查询行数大于期望
- db_query_count_less_than      数据库查询行数小于期望
- db_vs_jsonpath_equals         DB查询值 等于 响应JSON Path取值（DB值与响应值交叉校验）
- db_vs_jsonpath_not_equals     DB查询值 不等于 响应JSON Path取值

DB 断言支持 retry_count / retry_interval 参数，用于应对异步落库场景。
"""
import re
import time
from typing import Any, Dict, List, Optional
from jsonpath_ng import parse

from .expression import ExpressionEngine


class AssertionEngine:
    def __init__(self, context: Dict[str, Any], db_client=None):
        self.context = context
        self.db_client = db_client
        self.expr = ExpressionEngine(context, db_client=db_client)

    def evaluate_all(
        self,
        response_body: Any,
        status_code: int,
        response_time_ms: int,
        rules: List[Dict],
    ) -> List[Dict]:
        results = []
        for rule in rules or []:
            results.append(self._evaluate(response_body, status_code, response_time_ms, rule))
        return results

    def _evaluate(self, response_body, status_code, response_time_ms, rule: Dict) -> Dict:
        rule_type = rule.get("type")
        message = rule.get("message", "")

        if rule_type == "json_path_equals":
            actual = self._jsonpath_get(response_body, rule.get("path"))
            expected = self.expr.evaluate(rule.get("expected"))
            return self._pack(actual == expected, rule_type, actual, expected, message or f"{rule.get('path')} 期望 {expected}, 实际 {actual}")

        if rule_type == "json_path_not_equals":
            actual = self._jsonpath_get(response_body, rule.get("path"))
            expected = self.expr.evaluate(rule.get("expected"))
            return self._pack(actual != expected, rule_type, actual, expected, message)

        if rule_type == "json_path_contains":
            actual = self._jsonpath_get(response_body, rule.get("path"))
            expected = self.expr.evaluate(rule.get("expected"))
            passed = expected in actual if actual is not None else False
            return self._pack(passed, rule_type, actual, expected, message)

        if rule_type == "json_path_exists":
            actual = self._jsonpath_get(response_body, rule.get("path"))
            return self._pack(actual is not None, rule_type, actual, "exists", message)

        if rule_type == "json_path_not_empty":
            actual = self._jsonpath_get(response_body, rule.get("path"))
            passed = bool(actual) or actual == 0 or actual is False
            return self._pack(passed, rule_type, actual, "not_empty", message)

        if rule_type == "json_path_match_regex":
            actual = self._jsonpath_get(response_body, rule.get("path"))
            pattern = rule.get("pattern", "")
            passed = bool(re.search(pattern, str(actual))) if actual is not None else False
            return self._pack(passed, rule_type, actual, pattern, message or f"{rule.get('path')} 期望匹配正则 /{pattern}/, 实际 {actual}")

        if rule_type == "json_path_type_equals":
            actual = self._jsonpath_get(response_body, rule.get("path"))
            expected_type = rule.get("expected", "string")
            actual_type = self._python_type_name(actual)
            passed = actual_type == expected_type
            return self._pack(passed, rule_type, actual_type, expected_type, message or f"{rule.get('path')} 期望类型 {expected_type}, 实际类型 {actual_type}")

        if rule_type == "response_status_equals":
            expected = rule.get("expected")
            return self._pack(status_code == expected, rule_type, status_code, expected, message)

        if rule_type == "response_time_less_than":
            expected = rule.get("expected")
            return self._pack(response_time_ms < expected, rule_type, response_time_ms, expected, message or f"响应时间 {response_time_ms}ms 超过 {expected}ms")

        if rule_type in ("db_query_equals", "db_query_not_equals", "db_query_not_empty",
                         "db_query_count_equals", "db_query_count_greater_than", "db_query_count_less_than"):
            return self._eval_db_with_retry(rule_type, rule, message)

        if rule_type in ("db_vs_jsonpath_equals", "db_vs_jsonpath_not_equals"):
            return self._eval_db_vs_jsonpath_with_retry(response_body, rule, message)

        return self._pack(False, "unknown", None, None, "未知断言类型: " + str(rule_type))

    def _eval_db_with_retry(self, rule_type: str, rule: Dict, message: str) -> Dict:
        """DB 断言带重试：应对异步落库场景（如费用穿行）。
        retry_count 默认 0（不重试），retry_interval 默认 2 秒。
        """
        retry_count = int(rule.get("retry_count", 0))
        retry_interval = float(rule.get("retry_interval", 2))
        result = self._eval_db(rule_type, rule, message)
        for i in range(retry_count):
            if result.get("pass"):
                break
            time.sleep(retry_interval)
            result = self._eval_db(rule_type, rule, message)
        return result

    def _eval_db_vs_jsonpath_with_retry(self, response_body: Any, rule: Dict, message: str) -> Dict:
        """db_vs_jsonpath_equals 断言带重试。"""
        retry_count = int(rule.get("retry_count", 0))
        retry_interval = float(rule.get("retry_interval", 2))
        result = self._eval_db_vs_jsonpath(response_body, rule, message)
        for _ in range(retry_count):
            if result.get("pass"):
                break
            time.sleep(retry_interval)
            result = self._eval_db_vs_jsonpath(response_body, rule, message)
        return result

    def _eval_db(self, rule_type: str, rule: Dict, message: str) -> Dict:
        sql = rule.get("sql", "")
        sql = self._inject_extracted(sql)
        rows: Optional[List] = None
        actual = None
        if self.db_client:
            try:
                rows = self.db_client.query(sql)
            except Exception as e:
                actual = f"DB Error: {e}"
                return self._pack(False, rule_type, actual, rule.get("expected"), message or f"SQL执行异常: {e}")
        if rule_type == "db_query_equals":
            # 支持 field 参数：从第一行取指定字段的标量值与 expected 比较
            field = rule.get("field")
            if rows:
                first = rows[0]
                if isinstance(first, dict) and field:
                    actual = first.get(field)
                elif isinstance(first, dict):
                    # 未指定 field → 取第一行第一列
                    actual = next(iter(first.values())) if first else None
                else:
                    actual = first
            expected = self.expr.evaluate(rule.get("expected"))
            return self._pack(actual == expected, rule_type, actual, expected, message or f"DB字段 {field or ''} 期望 {expected}, 实际 {actual}")
        if rule_type == "db_query_not_equals":
            # DB 字段不等于期望值（对应代码里的 not_equal）
            field = rule.get("field")
            if rows:
                first = rows[0]
                if isinstance(first, dict) and field:
                    actual = first.get(field)
                elif isinstance(first, dict):
                    actual = next(iter(first.values())) if first else None
                else:
                    actual = first
            expected = self.expr.evaluate(rule.get("expected"))
            return self._pack(actual != expected, rule_type, actual, expected, message or f"DB字段 {field or ''} 不应等于 {expected}, 实际 {actual}")
        if rule_type == "db_query_not_empty":
            passed = bool(rows)
            return self._pack(passed, rule_type, rows, "not_empty", message)
        if rule_type == "db_query_count_equals":
            actual = len(rows) if rows else 0
            expected = rule.get("expected")
            return self._pack(actual == expected, rule_type, actual, expected, message or f"查询行数期望 {expected}, 实际 {actual}")
        if rule_type == "db_query_count_greater_than":
            actual = len(rows) if rows else 0
            expected = rule.get("expected")
            return self._pack(actual > expected, rule_type, actual, expected, message or f"查询行数期望 > {expected}, 实际 {actual}")
        if rule_type == "db_query_count_less_than":
            actual = len(rows) if rows else 0
            expected = rule.get("expected")
            return self._pack(actual < expected, rule_type, actual, expected, message or f"查询行数期望 < {expected}, 实际 {actual}")
        return self._pack(False, rule_type, None, None, "未知DB断言")

    def _eval_db_vs_jsonpath(self, response_body: Any, rule: Dict, message: str) -> Dict:
        """DB查询值 vs 响应JSON Path取值 相等断言。

        规则格式：
        {
            "type": "db_vs_jsonpath_equals",
            "sql": "SELECT status FROM sys_order WHERE bl_no='${bl_no}'",
            "field": "status",
            "path": "$.data.status"
        }
        """
        sql = rule.get("sql", "")
        sql = self._inject_extracted(sql)
        field = rule.get("field")
        json_path = rule.get("path")

        db_value = None
        if self.db_client:
            try:
                rows = self.db_client.query(sql)
                if rows:
                    first = rows[0]
                    if isinstance(first, dict) and field:
                        db_value = first.get(field)
                    elif isinstance(first, dict):
                        db_value = next(iter(first.values())) if first else None
                    else:
                        db_value = first
            except Exception as e:
                return self._pack(False, "db_vs_jsonpath_equals", f"DB Error: {e}", None, message or f"SQL执行异常: {e}")

        json_value = self._jsonpath_get(response_body, json_path)
        rule_type = rule.get("type", "db_vs_jsonpath_equals")
        if rule_type == "db_vs_jsonpath_not_equals":
            passed = db_value != json_value
            return self._pack(
                passed, "db_vs_jsonpath_not_equals",
                {"db": db_value, "response": json_value},
                "not_equal",
                message or f"DB值({db_value}) 与 响应值({json_value}) 应不相等但一致",
            )
        passed = db_value == json_value
        return self._pack(
            passed, "db_vs_jsonpath_equals",
            {"db": db_value, "response": json_value},
            "equal",
            message or f"DB值({db_value}) 与 响应值({json_value}) 不一致",
        )

    def _inject_extracted(self, sql: str) -> str:
        """把 ${extracted.xxx} / ${context.xxx} / ${xxx} 替换为已提取变量值"""
        extracted = self.context.get("extracted", {})

        def repl(m):
            key = m.group(1).strip()
            if key.startswith("extracted."):
                key = key[len("extracted."):]
            elif key.startswith("context."):
                key = key[len("context."):]
            val = extracted.get(key, m.group(0))
            if isinstance(val, str):
                # 简单防注入：字符串用单引号包裹并转义单引号
                return "'" + val.replace("'", "''") + "'"
            if val is None:
                return "NULL"
            return str(val)

        return re.sub(r"\$\{([^}]+)\}", repl, sql)

    @staticmethod
    def _jsonpath_get(data: Any, path: str) -> Any:
        if not path:
            return None
        try:
            matches = parse(path).find(data)
            return matches[0].value if matches else None
        except Exception:
            return None

    @staticmethod
    def _python_type_name(val: Any) -> str:
        """Python 值映射为统一类型名（与前端字段类型对齐）"""
        if val is None:
            return "null"
        if isinstance(val, bool):
            return "bool"
        if isinstance(val, int):
            return "int"
        if isinstance(val, float):
            return "number"
        if isinstance(val, str):
            return "string"
        if isinstance(val, list):
            return "array"
        if isinstance(val, dict):
            return "object"
        return "unknown"

    @staticmethod
    def _pack(passed: bool, rule_type: str, actual: Any, expected: Any, message: str) -> Dict:
        return {
            "pass": passed,
            "type": rule_type,
            "actual": actual,
            "expected": expected,
            "message": message,
        }

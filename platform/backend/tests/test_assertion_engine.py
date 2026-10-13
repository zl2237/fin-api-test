"""assertion_engine 模块单测：17 种断言类型。"""
from app.engine.assertion_engine import AssertionEngine


class FakeDBClient:
    """模拟 DB 客户端，按预设行数返回查询结果"""
    def __init__(self, rows=None):
        self.rows = rows or []

    def query(self, sql):
        return self.rows


def make_engine(context=None, db_rows=None):
    ctx = context or {"extracted": {}}
    db = FakeDBClient(db_rows) if db_rows is not None else None
    return AssertionEngine(ctx, db_client=db)


class TestJsonPathAssertions:
    def test_json_path_equals_pass(self):
        engine = make_engine()
        results = engine.evaluate_all({"data": {"status": 1}}, 200, 50,
                                     [{"type": "json_path_equals", "path": "$.data.status", "expected": 1}])
        assert results[0]["pass"] is True

    def test_json_path_equals_fail(self):
        engine = make_engine()
        results = engine.evaluate_all({"data": {"status": 2}}, 200, 50,
                                     [{"type": "json_path_equals", "path": "$.data.status", "expected": 1}])
        assert results[0]["pass"] is False

    def test_json_path_not_equals(self):
        engine = make_engine()
        results = engine.evaluate_all({"data": {"status": 2}}, 200, 50,
                                     [{"type": "json_path_not_equals", "path": "$.data.status", "expected": 1}])
        assert results[0]["pass"] is True

    def test_json_path_contains_string(self):
        engine = make_engine()
        results = engine.evaluate_all({"data": {"name": "hello world"}}, 200, 50,
                                     [{"type": "json_path_contains", "path": "$.data.name", "expected": "world"}])
        assert results[0]["pass"] is True

    def test_json_path_contains_list(self):
        engine = make_engine()
        results = engine.evaluate_all({"data": {"tags": ["a", "b", "c"]}}, 200, 50,
                                     [{"type": "json_path_contains", "path": "$.data.tags", "expected": "b"}])
        assert results[0]["pass"] is True

    def test_json_path_exists(self):
        engine = make_engine()
        results = engine.evaluate_all({"data": {"status": 1}}, 200, 50,
                                     [{"type": "json_path_exists", "path": "$.data.status"}])
        assert results[0]["pass"] is True

    def test_json_path_not_exists(self):
        engine = make_engine()
        results = engine.evaluate_all({"data": {}}, 200, 50,
                                     [{"type": "json_path_exists", "path": "$.data.missing"}])
        assert results[0]["pass"] is False

    def test_json_path_not_empty_value(self):
        engine = make_engine()
        results = engine.evaluate_all({"data": {"name": "abc"}}, 200, 50,
                                     [{"type": "json_path_not_empty", "path": "$.data.name"}])
        assert results[0]["pass"] is True

    def test_json_path_not_empty_zero(self):
        # 0 被视为非空（代码：bool(0) or 0 == 0 → True）
        engine = make_engine()
        results = engine.evaluate_all({"data": {"count": 0}}, 200, 50,
                                     [{"type": "json_path_not_empty", "path": "$.data.count"}])
        assert results[0]["pass"] is True

    def test_json_path_not_empty_empty_string(self):
        engine = make_engine()
        results = engine.evaluate_all({"data": {"name": ""}}, 200, 50,
                                     [{"type": "json_path_not_empty", "path": "$.data.name"}])
        assert results[0]["pass"] is False

    def test_json_path_match_regex(self):
        engine = make_engine()
        results = engine.evaluate_all({"data": {"code": "abc123"}}, 200, 50,
                                     [{"type": "json_path_match_regex", "path": "$.data.code", "pattern": "\\d+"}])
        assert results[0]["pass"] is True

    def test_json_path_match_regex_fail(self):
        engine = make_engine()
        results = engine.evaluate_all({"data": {"code": "abcdef"}}, 200, 50,
                                     [{"type": "json_path_match_regex", "path": "$.data.code", "pattern": "\\d+"}])
        assert results[0]["pass"] is False

    def test_json_path_type_equals_int(self):
        engine = make_engine()
        results = engine.evaluate_all({"data": {"count": 5}}, 200, 50,
                                     [{"type": "json_path_type_equals", "path": "$.data.count", "expected": "int"}])
        assert results[0]["pass"] is True

    def test_json_path_type_equals_string(self):
        engine = make_engine()
        results = engine.evaluate_all({"data": {"name": "abc"}}, 200, 50,
                                     [{"type": "json_path_type_equals", "path": "$.data.name", "expected": "string"}])
        assert results[0]["pass"] is True

    def test_json_path_type_equals_bool(self):
        engine = make_engine()
        results = engine.evaluate_all({"data": {"flag": True}}, 200, 50,
                                     [{"type": "json_path_type_equals", "path": "$.data.flag", "expected": "bool"}])
        assert results[0]["pass"] is True

    def test_json_path_type_equals_mismatch(self):
        engine = make_engine()
        results = engine.evaluate_all({"data": {"count": "5"}}, 200, 50,
                                     [{"type": "json_path_type_equals", "path": "$.data.count", "expected": "int"}])
        assert results[0]["pass"] is False


class TestResponseAssertions:
    def test_response_status_equals_int(self):
        engine = make_engine()
        results = engine.evaluate_all({}, 200, 50,
                                     [{"type": "response_status_equals", "expected": 200}])
        assert results[0]["pass"] is True

    def test_response_status_equals_string(self):
        # 字符串 "200" 也能匹配
        engine = make_engine()
        results = engine.evaluate_all({}, 200, 50,
                                     [{"type": "response_status_equals", "expected": "200"}])
        assert results[0]["pass"] is True

    def test_response_status_equals_fail(self):
        engine = make_engine()
        results = engine.evaluate_all({}, 404, 50,
                                     [{"type": "response_status_equals", "expected": 200}])
        assert results[0]["pass"] is False

    def test_response_time_less_than_pass(self):
        engine = make_engine()
        results = engine.evaluate_all({}, 200, 100,
                                     [{"type": "response_time_less_than", "expected": 200}])
        assert results[0]["pass"] is True

    def test_response_time_less_than_fail(self):
        engine = make_engine()
        results = engine.evaluate_all({}, 200, 300,
                                     [{"type": "response_time_less_than", "expected": 200}])
        assert results[0]["pass"] is False


class TestDbAssertions:
    def test_db_query_equals_pass(self):
        engine = make_engine(db_rows=[{"status": 1}])
        results = engine.evaluate_all({}, 200, 50,
                                     [{"type": "db_query_equals", "sql": "SELECT status", "field": "status", "expected": 1}])
        assert results[0]["pass"] is True

    def test_db_query_equals_loose(self):
        # DB 返回 int 1，expected 为字符串 "1"，松散相等应通过
        engine = make_engine(db_rows=[{"status": 1}])
        results = engine.evaluate_all({}, 200, 50,
                                     [{"type": "db_query_equals", "sql": "SELECT status", "field": "status", "expected": "1"}])
        assert results[0]["pass"] is True

    def test_db_query_not_equals_pass(self):
        engine = make_engine(db_rows=[{"status": 2}])
        results = engine.evaluate_all({}, 200, 50,
                                     [{"type": "db_query_not_equals", "sql": "SELECT status", "field": "status", "expected": 1}])
        assert results[0]["pass"] is True

    def test_db_query_not_empty_pass(self):
        engine = make_engine(db_rows=[{"id": 1}])
        results = engine.evaluate_all({}, 200, 50,
                                     [{"type": "db_query_not_empty", "sql": "SELECT * FROM t"}])
        assert results[0]["pass"] is True

    def test_db_query_not_empty_fail(self):
        engine = make_engine(db_rows=[])
        results = engine.evaluate_all({}, 200, 50,
                                     [{"type": "db_query_not_empty", "sql": "SELECT * FROM t"}])
        assert results[0]["pass"] is False

    def test_db_query_count_equals(self):
        engine = make_engine(db_rows=[{"id": 1}, {"id": 2}, {"id": 3}])
        results = engine.evaluate_all({}, 200, 50,
                                     [{"type": "db_query_count_equals", "sql": "SELECT *", "expected": 3}])
        assert results[0]["pass"] is True

    def test_db_query_count_greater_than(self):
        engine = make_engine(db_rows=[{"id": 1}, {"id": 2}, {"id": 3}])
        results = engine.evaluate_all({}, 200, 50,
                                     [{"type": "db_query_count_greater_than", "sql": "SELECT *", "expected": 2}])
        assert results[0]["pass"] is True

    def test_db_query_count_less_than(self):
        engine = make_engine(db_rows=[{"id": 1}, {"id": 2}, {"id": 3}])
        results = engine.evaluate_all({}, 200, 50,
                                     [{"type": "db_query_count_less_than", "sql": "SELECT *", "expected": 5}])
        assert results[0]["pass"] is True


class TestDbVsJsonPathAssertions:
    def test_db_vs_jsonpath_equals_pass(self):
        engine = make_engine(db_rows=[{"status": 1}])
        results = engine.evaluate_all({"data": {"status": 1}}, 200, 50,
                                     [{"type": "db_vs_jsonpath_equals", "sql": "SELECT status", "field": "status", "path": "$.data.status"}])
        assert results[0]["pass"] is True

    def test_db_vs_jsonpath_equals_fail(self):
        engine = make_engine(db_rows=[{"status": 2}])
        results = engine.evaluate_all({"data": {"status": 1}}, 200, 50,
                                     [{"type": "db_vs_jsonpath_equals", "sql": "SELECT status", "field": "status", "path": "$.data.status"}])
        assert results[0]["pass"] is False

    def test_db_vs_jsonpath_not_equals_pass(self):
        engine = make_engine(db_rows=[{"status": 2}])
        results = engine.evaluate_all({"data": {"status": 1}}, 200, 50,
                                     [{"type": "db_vs_jsonpath_not_equals", "sql": "SELECT status", "field": "status", "path": "$.data.status"}])
        assert results[0]["pass"] is True


class TestSpecExpectedRegression:
    """回归：期望值经四来源弹层保存为 spec（{"source":"constant","value":...}）后，
    各断言类型必须先经 _eval_expected 求值再比较（生产 record 1011：count 常量4 被判成 0）。"""

    def test_count_equals_constant_spec(self):
        # 生产事故场景：4 行 vs 常量 spec 4，旧实现 _to_count(dict) 兜底 0 → 误报失败
        engine = make_engine(db_rows=[{"id": 1}, {"id": 2}, {"id": 3}, {"id": 4}])
        results = engine.evaluate_all({}, 200, 50,
                                     [{"type": "db_query_count_equals", "sql": "SELECT *",
                                       "expected": {"source": "constant", "value": 4}}])
        assert results[0]["pass"] is True
        assert results[0]["expected"] == 4

    def test_count_greater_than_constant_spec(self):
        engine = make_engine(db_rows=[{"id": 1}, {"id": 2}])
        results = engine.evaluate_all({}, 200, 50,
                                     [{"type": "db_query_count_greater_than", "sql": "SELECT *",
                                       "expected": {"source": "constant", "value": "1"}}])
        assert results[0]["pass"] is True

    def test_count_less_than_constant_spec(self):
        engine = make_engine(db_rows=[{"id": 1}])
        results = engine.evaluate_all({}, 200, 50,
                                     [{"type": "db_query_count_less_than", "sql": "SELECT *",
                                       "expected": {"source": "constant", "value": 3}}])
        assert results[0]["pass"] is True

    def test_response_status_constant_spec(self):
        engine = make_engine()
        results = engine.evaluate_all({}, 200, 50,
                                     [{"type": "response_status_equals",
                                       "expected": {"source": "constant", "value": 200}}])
        assert results[0]["pass"] is True

    def test_response_time_constant_spec(self):
        engine = make_engine()
        results = engine.evaluate_all({}, 200, 50,
                                     [{"type": "response_time_less_than",
                                       "expected": {"source": "constant", "value": 100}}])
        assert results[0]["pass"] is True

    def test_type_equals_constant_spec(self):
        engine = make_engine()
        results = engine.evaluate_all({"data": {"n": 1}}, 200, 50,
                                     [{"type": "json_path_type_equals", "path": "$.data.n",
                                       "expected": {"source": "constant", "value": "int"}}])
        assert results[0]["pass"] is True

    def test_regex_from_expected_field(self):
        # 新前端把正则存进期望值列（spec），后端旧实现只读 pattern（空正则恒匹配）
        engine = make_engine()
        results = engine.evaluate_all({"data": {"phone": "13800138000"}}, 200, 50,
                                     [{"type": "json_path_match_regex", "path": "$.data.phone",
                                       "expected": {"source": "constant", "value": r"^1\d{10}$"}}])
        assert results[0]["pass"] is True
        bad = engine.evaluate_all({"data": {"phone": "abc"}}, 200, 50,
                                  [{"type": "json_path_match_regex", "path": "$.data.phone",
                                    "expected": {"source": "constant", "value": r"^1\d{10}$"}}])
        assert bad[0]["pass"] is False

    def test_regex_legacy_pattern_field_still_works(self):
        engine = make_engine()
        results = engine.evaluate_all({"data": {"n": "42"}}, 200, 50,
                                     [{"type": "json_path_match_regex", "path": "$.data.n",
                                       "pattern": r"^\d+$"}])
        assert results[0]["pass"] is True

    def test_expected_ref_failure_marks_fail_not_crash(self):
        # 引用来源解析失败 = 断言失败（message 带原因），不抛异常
        engine = make_engine()
        results = engine.evaluate_all({}, 200, 50,
                                     [{"type": "db_query_count_equals", "sql": "SELECT *",
                                       "expected": {"source": "ref", "node_id": "n_x", "var_path": "cnt"}}])
        assert results[0]["pass"] is False
        assert "解析失败" in results[0]["message"]


class TestUnknownAssertion:
    def test_unknown_type(self):
        engine = make_engine()
        results = engine.evaluate_all({}, 200, 50,
                                     [{"type": "unknown_type", "expected": 1}])
        assert results[0]["pass"] is False
        assert "未知" in results[0]["message"]

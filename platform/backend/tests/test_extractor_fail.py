# -*- coding: utf-8 -*-
"""后置提取失败语义：未取到的变量值为 {__error__: 原因}，注册表写 None。

历史行为是静默 None（SQL 写错也无从排查），改为错误可见 + DagExecutor 判节点失败。
"""
from app.engine.extractor import Extractor, is_extract_error
from app.engine.variables import VariableRegistry


def _rules(**kw):
    base = {"name": "v1", "source": "response", "json_path": "$.data.id"}
    base.update(kw)
    return [base]


class _DbStub:
    def __init__(self, rows=None, exc=None):
        self.rows, self.exc = rows, exc

    def query(self, sql):
        if self.exc:
            raise self.exc
        return self.rows


def test_response_jsonpath_miss_returns_error():
    reg = VariableRegistry()
    out = Extractor().extract({"data": {}}, _rules(), reg, "n1")
    assert is_extract_error(out["v1"]) and "未命中" in out["v1"]["__error__"]
    assert reg.read("n1", "v1") is None  # 注册表口径：无值


def test_response_success_value_passthrough():
    reg = VariableRegistry()
    out = Extractor().extract({"data": {"id": 42}}, _rules(), reg, "n1")
    assert out["v1"] == 42 and reg.read("n1", "v1") == 42


def test_db_sql_error_carries_reason():
    reg = VariableRegistry()
    ex = Extractor(db_client=_DbStub(exc=RuntimeError("(1064, 'syntax error near [\\'X\\']')")))
    out = ex.extract({}, [{"name": "v1", "source": "db", "sql": "SELECT 1"}], reg, "n1")
    assert is_extract_error(out["v1"]) and "SQL 执行失败" in out["v1"]["__error__"]


def test_db_no_rows_and_field_missing():
    reg = VariableRegistry()
    ex = Extractor(db_client=_DbStub(rows=[]))
    out = ex.extract({}, [{"name": "v1", "source": "db", "sql": "SELECT 1"}], reg, "n1")
    assert is_extract_error(out["v1"]) and "查询无结果" in out["v1"]["__error__"]

    ex2 = Extractor(db_client=_DbStub(rows=[{"a": 1}]))
    out2 = ex2.extract({}, [{"name": "v1", "source": "db", "sql": "SELECT 1", "field": "b"}],
                       reg, "n1")
    assert is_extract_error(out2["v1"]) and "结果列无 b" in out2["v1"]["__error__"]


def test_db_success_and_self_reference_chain():
    reg = VariableRegistry()
    ex = Extractor(db_client=_DbStub(rows=[{"id": 7}]))
    rules = [
        {"name": "pid", "source": "db", "sql": "SELECT id"},
        {"name": "audit", "source": "db", "sql": "SELECT audit_id WHERE id={{n1.pid}}"},
    ]
    # 第二条 SQL 引用第一条提取值：占位渲染取注册表 n1.pid
    ex.db_client = _DbStub(rows=[{"id": 7}])
    out = ex.extract({}, rules, reg, "n1")
    assert out["pid"] == 7 and reg.read("n1", "pid") == 7


class _DbLazyStub:
    """前 empty 次查询返回空（模拟异步落库延迟），之后返回数据"""

    def __init__(self, empty, rows):
        self.empty, self.rows = empty, rows
        self.calls = 0

    def query(self, sql):
        self.calls += 1
        return self.rows if self.calls > self.empty else []


def test_db_no_rows_retry_recovers():
    """查询无结果按 retry/interval 重查：异步落库场景重查后取到"""
    reg = VariableRegistry()
    stub = _DbLazyStub(2, [{"id": 9}])
    ex = Extractor(db_client=stub, retry=2, interval=0.01)
    out = ex.extract({}, [{"name": "v1", "source": "db", "sql": "SELECT 1"}], reg, "n1")
    assert out["v1"] == 9 and stub.calls == 3


def test_db_no_rows_retry_exhausted_reports_attempts():
    reg = VariableRegistry()
    stub = _DbLazyStub(9, [{"id": 9}])
    ex = Extractor(db_client=stub, retry=2, interval=0.01)
    out = ex.extract({}, [{"name": "v1", "source": "db", "sql": "SELECT 1"}], reg, "n1")
    assert is_extract_error(out["v1"]) and "查询无结果（含重查 2 次）" in out["v1"]["__error__"]
    assert reg.read("n1", "v1") is None

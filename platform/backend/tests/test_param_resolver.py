# -*- coding: utf-8 -*-
"""四来源参数解析器单测。"""
import pytest

from app.engine.param_resolver import (
    SqlExecutionError,
    render_placeholders,
    resolve_param,
)
from app.engine.variables import PREV_NS, ReferenceError, VariableRegistry


class _FakeDB:
    def __init__(self, rows=None, exc=None):
        self.rows, self.exc, self.queries = rows or [], exc, []

    def query(self, sql):
        if self.exc:
            raise self.exc
        self.queries.append(sql)
        return self.rows


@pytest.fixture()
def reg():
    r = VariableRegistry()
    r.inject(PREV_NS, {"main_id": "3"})
    r.write("n_create", "bl_no", "SMOKE-1")
    return r


class TestConstant:
    def test_scalar_and_composite(self, reg):
        assert resolve_param("a", {"source": "constant", "value": 1}, registry=reg, self_node="n1", db_client=None) == 1
        assert resolve_param("b", {"source": "constant", "value": {"x": [1, 2]}}, registry=reg, self_node="n1", db_client=None) == {"x": [1, 2]}


class TestRef:
    def test_cross_node(self, reg):
        v = resolve_param("p", {"source": "ref", "node_id": "n_create", "var_path": "bl_no"},
                          registry=reg, self_node="n2", db_client=None)
        assert v == "SMOKE-1"

    def test_suite_pseudo_ns(self, reg):
        """__prev__ 伪命名空间（上游白名单注入）可被 ref 直接引用（__dataset__ 平铺键已退役）。"""
        v = resolve_param("p", {"source": "ref", "node_id": PREV_NS, "var_path": "main_id"},
                          registry=reg, self_node="n2", db_client=None)
        assert v == "3"

    def test_missing_raises(self, reg):
        with pytest.raises(ReferenceError):
            resolve_param("p", {"source": "ref", "node_id": "n_x", "var_path": "nope"},
                          registry=reg, self_node="n2", db_client=None)


class TestFunc:
    def test_const_args(self, reg):
        v = resolve_param("p", {"source": "func", "func": "upper",
                                "args": [{"name": "s", "kind": "const", "value": "abc"}]},
                          registry=reg, self_node="n1", db_client=None)
        assert v == "ABC"

    def test_ref_args(self, reg):
        """函数入参引用上游变量（拷问定案：来源2 入参开引用）。"""
        v = resolve_param("p", {"source": "func", "func": "md5",
                                "args": [{"name": "s", "kind": "ref", "node_id": "n_create", "var_path": "bl_no"}]},
                          registry=reg, self_node="n2", db_client=None)
        import hashlib
        assert v == hashlib.md5(b"SMOKE-1").hexdigest()

    def test_unknown_func_raises(self, reg):
        with pytest.raises(ValueError):
            resolve_param("p", {"source": "func", "func": "nope", "args": []},
                          registry=reg, self_node="n1", db_client=None)


class TestSql:
    def test_scalar_and_registration(self, reg):
        """SQL 结果取首行首列并注册为 节点.参数路径（下游可直接引用）。"""
        db = _FakeDB(rows=[{"order_id": 88, "bl_no": "X"}])
        v = resolve_param("order_id", {"source": "sql", "sql": "SELECT order_id FROM t WHERE bl_no={{n_create.bl_no}}"},
                          registry=reg, self_node="n_distribute", db_client=db)
        assert v == 88
        assert db.queries == ["SELECT order_id FROM t WHERE bl_no='SMOKE-1'"]
        # 同节点后续参数引用 SQL 结果
        v2 = resolve_param("p", {"source": "ref", "node_id": "n_distribute", "var_path": "order_id"},
                           registry=reg, self_node="n_distribute", db_client=None)
        assert v2 == 88

    def test_column_pick(self, reg):
        db = _FakeDB(rows=[{"a": 1, "b": 2}])
        v = resolve_param("p", {"source": "sql", "sql": "SELECT a, b FROM t", "column": "b"},
                          registry=reg, self_node="n1", db_client=db)
        assert v == 2

    def test_empty_rows_returns_none(self, reg):
        db = _FakeDB(rows=[])
        v = resolve_param("p", {"source": "sql", "sql": "SELECT 1"}, registry=reg, self_node="n1", db_client=db)
        assert v is None

    def test_db_failure_raises(self, reg):
        with pytest.raises(SqlExecutionError):
            resolve_param("p", {"source": "sql", "sql": "SELECT 1"}, registry=reg,
                          self_node="n1", db_client=_FakeDB(exc=RuntimeError("conn refused")))

    def test_no_db_client_raises(self, reg):
        with pytest.raises(SqlExecutionError):
            resolve_param("p", {"source": "sql", "sql": "SELECT 1"}, registry=reg,
                          self_node="n1", db_client=None)


class TestRender:
    def test_escape_and_types(self, reg):
        r = VariableRegistry()
        r.write("n1", "s", "O'BRIEN")
        r.write("n1", "i", 5)
        out = render_placeholders("SELECT {{n1.s}}, {{n1.i}}", r)
        assert out == "SELECT 'O''BRIEN', 5"

    def test_missing_placeholder_raises(self, reg):
        with pytest.raises(ReferenceError):
            render_placeholders("SELECT {{n_none.x}}", reg)

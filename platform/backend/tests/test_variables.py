# -*- coding: utf-8 -*-
"""变量注册表 + 参数拓扑排序单测（新参数模型地基）。"""
import pytest

from app.engine.variables import (
    PREV_NS,
    CycleError,
    ReferenceError,
    VariableRegistry,
    extract_refs,
    order_params,
    split_ref,
)


class TestVariableRegistry:
    def test_namespaced_isolation(self):
        """同名冲突三场景根治：不同节点同名变量互不覆盖。"""
        r = VariableRegistry()
        r.write("n_create", "order_id", 1)
        r.write("n_distribute", "order_id", "ORD-2")  # 同名异值异型
        r.write("n_stash", "order_id", {"nested": {"a": 1}})  # 同名嵌套层级不一致
        assert r.read("n_create", "order_id") == 1
        assert r.read("n_distribute", "order_id") == "ORD-2"
        assert r.read("n_stash", "order_id") == {"nested": {"a": 1}}

    def test_resolve_missing_raises(self):
        """取不到值必须抛错——旧引擎静默保留占位符的行为已废止。"""
        r = VariableRegistry()
        with pytest.raises(ReferenceError):
            r.resolve({"node_id": "n_a", "var_path": "x"})
        with pytest.raises(ReferenceError):
            r.resolve({"node_id": "", "var_path": "x"})

    def test_resolve_ok(self):
        r = VariableRegistry()
        r.write("n_a", "bl_no", "SMOKE-1")
        assert r.resolve({"node_id": "n_a", "var_path": "bl_no"}) == "SMOKE-1"

    def test_suite_pseudo_ns(self):
        """套件伪命名空间批量注入（__dataset__ 平铺键值注入已随入参收敛退役）。"""
        r = VariableRegistry()
        r.inject(PREV_NS, {"pol": "ANTING", "pod": "AOSHANWEI"})
        assert r.vars_of(PREV_NS) == {"pol": "ANTING", "pod": "AOSHANWEI"}
        assert r.read(PREV_NS, "pol") == "ANTING"

    def test_inject_and_write_no_cross_talk(self):
        r = VariableRegistry()
        r.inject("__prev__", {"a": 1})
        r.write("n1", "a", 2)
        assert r.read("__prev__", "a") == 1
        assert r.read("n1", "a") == 2

    def test_null_value_resolved_raises(self):
        r = VariableRegistry()
        r.write("n1", "x", None)
        with pytest.raises(ReferenceError):
            r.resolve({"node_id": "n1", "var_path": "x"})


class TestPlaceholder:
    def test_split_ref(self):
        assert split_ref("n_create.order_id") == ("n_create", "order_id")
        assert split_ref("__prev__.to_customer.a") == ("__prev__", "to_customer.a")

    def test_extract_refs(self):
        sql = "SELECT 1 FROM t WHERE bl_no={{n_create.bl_no}} AND id={{__prev__.main_id}}"
        assert extract_refs(sql) == [("n_create", "bl_no"), ("__prev__", "main_id")]

    def test_old_syntax_not_matched(self):
        """旧 ${xxx} 语法不再是占位符——迁移后残留应被校验拦截。"""
        assert extract_refs("SELECT ${x}") == []


class TestOrderParams:
    def test_no_deps_keeps_order(self):
        params = {"a": {"source": "constant", "value": 1}, "b": {"source": "constant", "value": 2}}
        assert order_params(params, "n1") == ["a", "b"]

    def test_func_arg_dep_on_sql_param(self):
        """B(func upper) 引用本节点 SQL 参数 A → A 先解析。"""
        params = {
            "b": {"source": "func", "func": "upper", "args": [
                {"kind": "ref", "node_id": "n1", "var_path": "a"}]},
            "a": {"source": "sql", "sql": "SELECT id FROM t"},
        }
        assert order_params(params, "n1") == ["a", "b"]

    def test_sql_placeholder_dep(self):
        params = {
            "x": {"source": "sql", "sql": "SELECT {{n1.y}} FROM t"},
            "y": {"source": "sql", "sql": "SELECT 1"},
        }
        assert order_params(params, "n1") == ["y", "x"]

    def test_cross_node_ref_not_local_dep(self):
        """引用前置节点变量不构成本节点参数间依赖。"""
        params = {
            "b": {"source": "func", "func": "upper", "args": [
                {"kind": "ref", "node_id": "n_prev", "var_path": "a"}]},
        }
        assert order_params(params, "n1") == ["b"]

    def test_cycle_raises(self):
        params = {
            "a": {"source": "sql", "sql": "SELECT {{n1.b}}"},
            "b": {"source": "sql", "sql": "SELECT {{n1.a}}"},
        }
        with pytest.raises(CycleError):
            order_params(params, "n1")

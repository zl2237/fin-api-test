# -*- coding: utf-8 -*-
"""参数声明语义（2026-09-30「动作概念退场」定案）。

本文件测字段设置的全部语义在参数模型上的等价表达（旧 PreProcessor
set_field/iterate_set 已删除，字段设置 = 声明该参数的取值来源）：
- constant 容器值（list/dict）内嵌 spec 递归解析（常量元素原样保留）
- 通配路径参数（列表.*.字段）：容器参数就位后逐元素独立求值
  （iterate_set 的声明式等价）；同步列表用 ref 通配按下标配对取值
- 参数解析结果注册进本节点命名空间（完整路径 + 末段别名，下游经
  节点.变量 引用；SQL 占位 {{节点.末段}} 兼容旧引用名）
"""
from types import SimpleNamespace

import pytest

from app.engine.context import ExecutionContext
from app.engine.prepare_request import prepare_request

SELF = "n_case"


def _field(key, field_type="string", default=None, required=False):
    return SimpleNamespace(key=key, field_type=field_type, default_value=default,
                           required=required)


def _api(fields, template=None, **kw):
    return SimpleNamespace(fields=fields, request_template=template, **kw)


def _config(body=None, headers=None):
    return SimpleNamespace(params={"body": body or {}, "headers": headers or {}})


def _const(v):
    return {"source": "constant", "value": v}


def _ref(node_id, var_path):
    return {"source": "ref", "node_id": node_id, "var_path": var_path}


def _run(api, config=None, ctx=None, self_node=SELF, db_client=None):
    return prepare_request(api, config, context=ctx or ExecutionContext(),
                           self_node=self_node,
                           base_headers={}, db_client=db_client)


class TestConstantContainer:
    """constant 容器值：内嵌 spec 递归解析，常量元素原样保留"""

    def test_embedded_specs_in_list_value(self):
        """数组整组值：list 容器内嵌 ref 独立求值，常量元素原样"""
        api = _api([_field("tags", field_type="array")])
        parts = _run(api, _config(body={"tags": _const([_ref("n_up", "id"), "keep"])}),
                     ExecutionContext(resume_seed={"n_up": {"id": "A1"}}))
        assert parts.body == {"tags": ["A1", "keep"]}

    def test_embedded_specs_in_dict_value(self):
        """对象整组值：dict 容器内嵌 spec 逐键求值，其余子键原样"""
        api = _api([_field("to_customer", field_type="object")])
        parts = _run(
            api,
            _config(body={"to_customer": _const({
                "order_id": _ref("n_up", "oid"), "remark": "keep", "num": 2})}),
            ExecutionContext(resume_seed={"n_up": {"oid": "O9"}}),
        )
        assert parts.body == {"to_customer": {"order_id": "O9", "remark": "keep", "num": 2}}

    def test_embedded_func_evaluates(self):
        """容器内嵌 func 照常求值"""
        api = _api([_field("meta", field_type="object")])
        parts = _run(
            api,
            _config(body={"meta": _const({"bl_no": {
                "source": "func", "func": "generate_bl_no",
                "args": [{"name": "prefix", "kind": "const", "value": "smoke"}]}})}),
        )
        assert parts.body["meta"]["bl_no"].startswith("smoke")

    def test_embedded_spec_nested_deep(self):
        """深层嵌套容器（list<dict<list>>）内的 spec 逐层解析"""
        api = _api([_field("payload", field_type="object")])
        parts = _run(
            api,
            _config(body={"payload": _const(
                {"rows": [{"oid": _ref("n_up", "oid"), "tags": ["x", _ref("n_up", "oid")]}]})}),
            ExecutionContext(resume_seed={"n_up": {"oid": "OID"}}),
        )
        assert parts.body["payload"]["rows"][0] == {"oid": "OID", "tags": ["x", "OID"]}

    def test_embedded_sql_source_rejected(self):
        """容器内嵌 SQL 来源禁用：读库取值须声明为独立参数（旧「动作值禁 SQL」同口径）"""
        api = _api([_field("meta", field_type="object")])
        with pytest.raises(ValueError, match="未知来源|SQL"):
            _run(api, _config(body={"meta": _const(
                {"x": {"source": "sql", "sql": "SELECT 1"}})}))


class TestWildcardParam:
    """通配路径参数（列表.*.字段）：iterate_set 的声明式等价"""

    def test_func_per_element_fresh_values(self):
        """func 每元素独立求值（逐行 generate_unique_id 各不相同）"""
        api = _api([_field("items", field_type="array")])
        parts = _run(
            api,
            _config(body={
                "items": _const([{"sku": "a"}, {"sku": "b"}]),
                "items.*.unique_id": {"source": "func", "func": "generate_unique_id",
                                      "args": []},
            }),
        )
        ids = [it["unique_id"] for it in parts.body["items"]]
        assert len(ids) == 2 and len(set(ids)) == 2  # 每行独立新值

    def test_sync_list_via_wildcard_ref(self):
        """同步语义：第二列表声明来源为本节点另一列表的通配字段（同下标配对取值）"""
        api = _api([_field("to_customer", field_type="object"),
                    _field("to_supplier", field_type="object")])
        wp = "to_customer.put_amount.standard_list.*.unique_id"
        parts = _run(
            api,
            _config(body={
                "to_customer": _const({"put_amount": {"standard_list": [
                    {"num": "1"}, {"num": "2"}]}}),
                "to_supplier": _const({"pay_amount": {"standard_list": [
                    {"num": "1"}, {"num": "2"}]}}),
                wp: {"source": "func", "func": "generate_unique_id", "args": []},
                "to_supplier.pay_amount.standard_list.*.unique_id": _ref(SELF, wp),
            }),
        )
        a = [it["unique_id"] for it in parts.body["to_customer"]["put_amount"]["standard_list"]]
        b = [it["unique_id"] for it in parts.body["to_supplier"]["pay_amount"]["standard_list"]]
        assert a == b and len(set(a)) == 2  # 逐下标同值（行关联键），各行互异

    def test_wildcard_after_container_param(self):
        """通配参数在其容器参数之后展开（order_params 前缀依赖），
        dict 键序上通配在前也不受影响"""
        api = _api([_field("items", field_type="array")])
        parts = _run(
            api,
            _config(body={
                "items.*.uid": _ref("n_up", "uid"),  # 声明顺序在前
                "items": _const([{"sku": "a"}, {"sku": "b"}]),
            }),
            ExecutionContext(resume_seed={"n_up": {"uid": "U1"}}),
        )
        assert all(it["uid"] == "U1" for it in parts.body["items"])

    def test_non_list_prefix_skipped(self):
        """前缀不是列表 → 静默跳过（与旧 iterate_set 口径一致）"""
        api = _api([_field("items", field_type="object")])
        parts = _run(
            api,
            _config(body={
                "items": _const({"a": 1}),
                "items.*.uid": _ref("n_up", "uid"),
            }),
        )
        assert parts.body == {"items": {"a": 1}}

    def test_non_dict_element_skipped(self):
        """标量元素跳过，dict 元素正常写入"""
        api = _api([_field("items", field_type="array")])
        parts = _run(
            api,
            _config(body={
                "items": _const(["plain", {"sku": "a"}]),
                "items.*.uid": _ref("n_up", "uid"),
            }),
            ExecutionContext(resume_seed={"n_up": {"uid": "U1"}}),
        )
        assert parts.body["items"] == ["plain", {"sku": "a", "uid": "U1"}]


class TestRegistrySync:
    """参数解析结果注册进本节点命名空间（下游经 节点.变量 引用）"""

    def test_param_registers_full_path_and_tail(self):
        """顶层参数注册路径本身；嵌套参数额外注册末段（旧 set_field 引用名兼容）"""
        api = _api([_field("to_customer.put_amount", field_type="int")])
        ctx = ExecutionContext()
        _run(api, _config(body={"to_customer.put_amount": _const("100")}), ctx)
        assert ctx.registry.read(SELF, "to_customer.put_amount") == "100"
        assert ctx.registry.read(SELF, "put_amount") == "100"

    def test_later_param_refs_earlier_param(self):
        """参数拓扑序：后序参数引用先序参数的完整路径"""
        api = _api([_field("src"), _field("dst")])
        parts = _run(api, _config(body={
            "src": _const("FROM_CASE"),
            "dst": _ref(SELF, "src"),
        }))
        assert parts.body == {"src": "FROM_CASE", "dst": "FROM_CASE"}

    def test_later_param_refs_earlier_param_tail(self):
        """末段别名引用（旧 {{节点.末段}} 引用名）：依赖归一后仍按序解析"""
        api = _api([_field("select_list", field_type="array"), _field("memo")])
        parts = _run(
            api,
            _config(body={
                "select_list": _const([{"x": 1}]),
                "select_list.0.bl_no": _ref("n_up", "bl_no"),
                "memo": _ref(SELF, "bl_no"),
            }),
            ExecutionContext(resume_seed={"n_up": {"bl_no": "BL9"}}),
        )
        assert parts.body["memo"] == "BL9"

    def test_wildcard_registers_concrete_paths(self):
        """通配参数按具体路径（列表.下标.字段）注册，供下游按下标引用"""
        api = _api([_field("items", field_type="array"), _field("memo")])
        wp = "items.*.uid"
        parts = _run(
            api,
            _config(body={
                "items": _const([{"sku": "a"}, {"sku": "b"}]),
                wp: {"source": "func", "func": "generate_unique_id", "args": []},
                "memo": _ref(SELF, "items.1.uid"),
            }),
        )
        assert parts.body["memo"] == parts.body["items"][1]["uid"]

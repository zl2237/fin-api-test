# -*- coding: utf-8 -*-
"""contract_sync 单测：数据集节点参数 与 接口字段契约 的一致性口径（2026-10-10 定案）。

覆盖：
- field_param_specs：示例值 → 初始参数（结构拆解 Q9-B / 原生类型还原 / 空占位语义）
- node_contract_gaps：missing / extra 判定（前缀链、父级容器、通配、模板接口防御）
- apply_node_sync：补 missing、删 constant extra、动态来源红线（Q8）
"""
from types import SimpleNamespace

from app.services.contract_sync import (
    apply_node_sync,
    field_param_specs,
    node_contract_gaps,
)


def _field(key, field_type="string", default=None):
    return SimpleNamespace(key=key, field_type=field_type, default_value=default)


def _const(v):
    return {"source": "constant", "value": v}


def _ref(node="n1", path="x"):
    return {"source": "ref", "node_id": node, "var_path": path}


class TestFieldParamSpecs:
    def test_string_example_text(self):
        assert field_param_specs(_field("bl_no", default="BL001")) == {"bl_no": _const("BL001")}

    def test_string_numeric_example_native(self):
        """数字示例值还原原生类型（与前端 constant 输入的类型自动转换同口径）"""
        assert field_param_specs(_field("teu", default="5")) == {"teu": _const(5)}

    def test_no_example_empty_placeholder_semantics(self):
        """无示例值对齐引擎空占位：string/file→""，int/bool→None"""
        assert field_param_specs(_field("bl_no")) == {"bl_no": _const("")}
        assert field_param_specs(_field("doc", field_type="file")) == {"doc": _const("")}
        assert field_param_specs(_field("teu", field_type="int")) == {"teu": _const(None)}

    def test_object_structure_split(self):
        """object 示例值按 JSON 结构拆叶子路径（Q9-B）"""
        f = _field("to_customer", field_type="object",
                   default='{"name": "ACO", "addr": {"city": "SH"}}')
        assert field_param_specs(f) == {
            "to_customer.name": _const("ACO"),
            "to_customer.addr.city": _const("SH"),
        }

    def test_object_no_example_null(self):
        assert field_param_specs(_field("extra", field_type="object")) == {"extra": _const(None)}

    def test_array_dict_first_element_split(self):
        """array 首元素 dict：拆 x.0.叶子（元素结构契约源，Q1/Q9-B）"""
        f = _field("statement", field_type="array",
                   default='[{"receipt_account": "ACC", "fee": 1}]')
        assert field_param_specs(f) == {
            "statement.0.receipt_account": _const("ACC"),
            "statement.0.fee": _const(1),
        }

    def test_array_scalar_example_kept_as_text(self):
        """标量数组元素无字段名：整字段 constant JSON 文本（引擎转回 list）"""
        f = _field("ids", field_type="array", default='["3439281444", "1"]')
        assert field_param_specs(f) == {"ids": _const('["3439281444", "1"]')}

    def test_array_no_example_or_illegal_empty_list(self):
        assert field_param_specs(_field("ids", field_type="array")) == {"ids": _const([])}
        assert field_param_specs(_field("ids", field_type="array", default="abc")) == {"ids": _const([])}

    def test_empty_key_skipped(self):
        assert field_param_specs(_field("")) == {}


class TestNodeContractGaps:
    def test_consistent(self):
        fields = [_field("bl_no"), _field("ids", field_type="array")]
        params = {"bl_no": _const("B1"), "ids": _const([])}
        assert node_contract_gaps(fields, params) == {}

    def test_missing_field(self):
        assert node_contract_gaps([_field("bl_no")], {}) == {"missing": ["bl_no"]}

    def test_array_leaf_param_covers_field(self):
        """数组元素路径参数（statement.0.acc）覆盖 array 字段（不 missing）"""
        fields = [_field("statement", field_type="array")]
        assert node_contract_gaps(fields, {"statement.0.acc": _const("A")}) == {}

    def test_wildcard_param_covers_field(self):
        assert node_contract_gaps([_field("list", field_type="array")],
                                  {"list.*.id": _ref()}) == {}

    def test_parent_container_param_covers_nested_field_key(self):
        """嵌套字段 key（to_customer.put_amount）的父级整体参数（to_customer
        容器常量）是合法写法：既不 missing 也不 extra"""
        fields = [_field("to_customer.put_amount", field_type="int")]
        assert node_contract_gaps(fields, {"to_customer": _const({"put_amount": 1})}) == {}

    def test_extra_constant_and_dynamic_flagged(self):
        fields = [_field("bl_no")]
        gaps = node_contract_gaps(fields, {
            "bl_no": _const("B"),
            "legacy": _const("x"),
            "dyn": _ref(),
        })
        assert gaps == {"extra": [
            {"path": "legacy", "source": "constant", "dynamic": False},
            {"path": "dyn", "source": "ref", "dynamic": True},
        ]}

    def test_template_api_no_fields_no_gaps(self):
        """无字段契约（模板接口）：参数对齐 request_template，不做比对"""
        assert node_contract_gaps(None, {"anything": _const(1)}) == {}
        assert node_contract_gaps([], {"anything": _const(1)}) == {}


class TestApplyNodeSync:
    def test_adds_missing_removes_constant_extra_keeps_dynamic(self):
        """同步三动作：补 missing（示例值）、删 constant extra、动态 extra 红线保留（Q8）"""
        fields = [_field("bl_no", default="BL1"),
                  _field("statement", field_type="array",
                         default='[{"acc": "A"}]')]
        body = {"legacy": _const("x"), "dyn": _ref()}
        new_body, stats = apply_node_sync(body, fields)
        assert new_body == {
            "dyn": _ref(),
            "bl_no": _const("BL1"),
            "statement.0.acc": _const("A"),
        }
        assert stats == {"added": 2, "removed": 1, "skipped_dynamic": 1}

    def test_partial_config_not_refilled(self):
        """字段已部分配置（元素叶子在）：不重复补（元素补空由引擎兜底）"""
        fields = [_field("statement", field_type="array", default='[{"a": 1, "b": 2}]')]
        new_body, stats = apply_node_sync({"statement.0.a": _const(9)}, fields)
        assert new_body == {"statement.0.a": _const(9)}
        assert stats["added"] == 0

    def test_no_fields_untouched(self):
        body = {"anything": _const(1)}
        new_body, stats = apply_node_sync(body, [])
        assert new_body == body and stats["added"] == 0 and stats["removed"] == 0

    def test_idempotent(self):
        fields = [_field("bl_no", default="BL1")]
        once, _ = apply_node_sync({}, fields)
        twice, stats = apply_node_sync(once, fields)
        assert twice == once and stats == {"added": 0, "removed": 0, "skipped_dynamic": 0}

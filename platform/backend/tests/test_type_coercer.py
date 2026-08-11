"""type_coercer 模块单测：请求体类型强转（表达式求值后按字段定义还原/强转类型）。

覆盖 coerce_json_strings / apply_field_types / infer_array_elem_type / coerce_scalar
的关键分支，行为与原 DagExecutor 实现完全一致。
"""
from types import SimpleNamespace

from app.engine.type_coercer import (
    coerce_json_strings,
    apply_field_types,
    infer_array_elem_type,
    coerce_scalar,
)


def _field(key, default_value="", field_type="string"):
    return SimpleNamespace(key=key, default_value=default_value, field_type=field_type)


def _api(fields=None):
    return SimpleNamespace(fields=fields or [])


# ==================== coerce_json_strings ====================
class TestCoerceJsonStrings:
    def test_dict_recursive(self):
        obj = {"a": "[1, 2]", "b": '{"k": "v"}'}
        assert coerce_json_strings(obj) == {"a": [1, 2], "b": {"k": "v"}}

    def test_list_recursive(self):
        obj = ["[1]", '{"x": 1}', "plain"]
        assert coerce_json_strings(obj) == [[1], {"x": 1}, "plain"]

    def test_valid_json_array_string(self):
        assert coerce_json_strings("[1, 2, 3]") == [1, 2, 3]

    def test_valid_json_object_string(self):
        assert coerce_json_strings('{"key": "val"}') == {"key": "val"}

    def test_invalid_json_array_string_kept(self):
        # 形似数组但内容非合法 JSON → 保留原字符串
        assert coerce_json_strings("[abc]") == "[abc]"

    def test_invalid_json_object_string_kept(self):
        assert coerce_json_strings("{abc}") == "{abc}"

    def test_plain_string_unchanged(self):
        assert coerce_json_strings("hello") == "hello"

    def test_non_string_non_container_unchanged(self):
        assert coerce_json_strings(42) == 42
        assert coerce_json_strings(True) is True
        assert coerce_json_strings(None) is None

    def test_nested_dict_in_list(self):
        obj = [{"data": "[1,2]"}]
        assert coerce_json_strings(obj) == [{"data": [1, 2]}]

    def test_whitespace_trimmed_before_parse(self):
        assert coerce_json_strings('  [1, 2]  ') == [1, 2]

    def test_empty_json_array(self):
        assert coerce_json_strings("[]") == []

    def test_empty_json_object(self):
        assert coerce_json_strings("{}") == {}


# ==================== coerce_scalar ====================
class TestCoerceScalar:
    def test_string_from_int(self):
        assert coerce_scalar(123, "string") == "123"

    def test_string_from_str(self):
        assert coerce_scalar("hello", "string") == "hello"

    def test_string_from_bool(self):
        # 布尔值转小写字符串
        assert coerce_scalar(True, "string") == "true"
        assert coerce_scalar(False, "string") == "false"

    def test_int_from_int(self):
        assert coerce_scalar(42, "int") == 42

    def test_int_from_str(self):
        assert coerce_scalar("123", "int") == 123

    def test_int_from_float_str(self):
        assert coerce_scalar("123.0", "int") == 123

    def test_int_from_float(self):
        assert coerce_scalar(123.9, "int") == 123

    def test_int_from_bool(self):
        assert coerce_scalar(True, "int") == 1
        assert coerce_scalar(False, "int") == 0

    def test_int_invalid_returns_none(self):
        assert coerce_scalar("abc", "int") is None

    def test_bool_from_bool(self):
        assert coerce_scalar(True, "bool") is True
        assert coerce_scalar(False, "bool") is False

    def test_bool_from_str_truthy(self):
        assert coerce_scalar("true", "bool") is True
        assert coerce_scalar("1", "bool") is True
        assert coerce_scalar("yes", "bool") is True

    def test_bool_from_str_falsy(self):
        assert coerce_scalar("false", "bool") is False
        assert coerce_scalar("no", "bool") is False
        assert coerce_scalar("0", "bool") is False

    def test_bool_from_other(self):
        assert coerce_scalar(1, "bool") is True
        assert coerce_scalar(0, "bool") is False

    def test_unknown_type_passthrough(self):
        assert coerce_scalar("x", "unknown") == "x"


# ==================== infer_array_elem_type ====================
class TestInferArrayElemType:
    def test_string_array(self):
        assert infer_array_elem_type('["1", "2"]') == "string"

    def test_int_array(self):
        assert infer_array_elem_type("[1, 2, 3]") == "int"

    def test_bool_array(self):
        assert infer_array_elem_type('[true, false]') == "bool"

    def test_empty_string(self):
        assert infer_array_elem_type("") is None
        assert infer_array_elem_type(None) is None

    def test_empty_array(self):
        assert infer_array_elem_type("[]") is None

    def test_invalid_json(self):
        assert infer_array_elem_type("not json") is None

    def test_non_list_json(self):
        assert infer_array_elem_type('{"k": 1}') is None

    def test_nested_element_returns_none(self):
        # 元素是 dict/list → 不处理
        assert infer_array_elem_type('[{"a": 1}]') is None
        assert infer_array_elem_type('[[1, 2]]') is None


# ==================== apply_field_types ====================
class TestApplyFieldTypes:
    def test_no_fields_returns_body_unchanged(self):
        api = _api(fields=[])
        body = {"a": 1}
        assert apply_field_types(body, api) == {"a": 1}

    def test_none_fields_returns_body_unchanged(self):
        api = SimpleNamespace(fields=None)
        body = {"a": 1}
        assert apply_field_types(body, api) == {"a": 1}

    def test_string_field_coerces_int_to_str(self):
        api = _api(fields=[_field("order_id", "", "string")])
        body = {"order_id": 123}
        assert apply_field_types(body, api) == {"order_id": "123"}

    def test_int_field_coerces_str_to_int(self):
        api = _api(fields=[_field("amount", "", "int")])
        body = {"amount": "100"}
        assert apply_field_types(body, api) == {"amount": 100}

    def test_bool_field_coerces_str_to_bool(self):
        api = _api(fields=[_field("enabled", "", "bool")])
        body = {"enabled": "true"}
        assert apply_field_types(body, api) == {"enabled": True}

    def test_object_field_skipped(self):
        api = _api(fields=[_field("detail", "", "object")])
        body = {"detail": {"k": "v"}}
        assert apply_field_types(body, api) == {"detail": {"k": "v"}}

    def test_none_value_skipped(self):
        api = _api(fields=[_field("missing", "", "int")])
        body = {"other": 1}
        # missing 字段在 body 中不存在 → get_nested_value 返回 None → 跳过
        assert apply_field_types(body, api) == {"other": 1}

    def test_empty_key_field_skipped(self):
        api = _api(fields=[_field("", "", "string")])
        body = {"a": 1}
        assert apply_field_types(body, api) == {"a": 1}

    def test_array_field_string_elements(self):
        # default_value '["343928144446619648"]' → 推断元素类型 string
        api = _api(fields=[_field("ids", '["343928144446619648"]', "array")])
        body = {"ids": [123, 456]}
        result = apply_field_types(body, api)
        assert result == {"ids": ["123", "456"]}

    def test_array_field_int_elements(self):
        api = _api(fields=[_field("nums", "[1, 2]", "array")])
        body = {"nums": ["10", "20"]}
        result = apply_field_types(body, api)
        assert result == {"nums": [10, 20]}

    def test_array_field_non_list_value_skipped(self):
        # field_type=array 但值是无括号普通字符串 → 保持原样，不误转为 list
        api = _api(fields=[_field("ids", '["x"]', "array")])
        body = {"ids": "not a list"}
        assert apply_field_types(body, api) == {"ids": "not a list"}

    def test_array_field_bracket_string_value_recovered_to_list(self):
        # [${bl_no}] 求值后得到 "[somestring]"（非合法 JSON），应按数组语义恢复为 list
        api = _api(fields=[_field("bl_nos", '[""]', "array")])
        body = {"bl_nos": "[smoke20260811093513FKK8]"}
        result = apply_field_types(body, api)
        assert result == {"bl_nos": ["smoke20260811093513FKK8"]}

    def test_array_field_bracket_string_multiple_values_recovered(self):
        # [${a}, ${b}] 求值后得到 "[x, y]"，恢复为 ["x", "y"]
        api = _api(fields=[_field("tags", '[""]', "array")])
        body = {"tags": "[x, y]"}
        result = apply_field_types(body, api)
        assert result == {"tags": ["x", "y"]}

    def test_array_field_bracket_string_empty_recovered(self):
        # "[]" 应恢复为空 list
        api = _api(fields=[_field("ids", '[""]', "array")])
        body = {"ids": "[]"}
        result = apply_field_types(body, api)
        assert result == {"ids": []}

    def test_array_field_bracket_string_int_elem_type_coerced(self):
        # [${id}] 求值后得到 "[123]"，coerce_json_strings 已能转回 [123]；
        # 此处验证 elem_type=int 时元素被正确强转为 int
        api = _api(fields=[_field("nums", "[1]", "array")])
        body = {"nums": "[123]"}
        result = apply_field_types(body, api)
        assert result == {"nums": [123]}

    def test_array_body_applies_to_first_element(self):
        api = _api(fields=[_field("id", "", "string")])
        body = [{"id": 123}]
        result = apply_field_types(body, api)
        assert result == [{"id": "123"}]

    def test_array_body_empty_list_unchanged(self):
        api = _api(fields=[_field("id", "", "string")])
        body = []
        assert apply_field_types(body, api) == []

    def test_array_body_first_not_dict_unchanged(self):
        api = _api(fields=[_field("id", "", "string")])
        body = ["plain string"]
        assert apply_field_types(body, api) == ["plain string"]

    def test_nested_path_field(self):
        api = _api(fields=[_field("to_customer.amount", "", "int")])
        body = {"to_customer": {"amount": "50"}}
        assert apply_field_types(body, api) == {"to_customer": {"amount": 50}}

    def test_multiple_fields(self):
        api = _api(fields=[
            _field("id", "", "string"),
            _field("amount", "", "int"),
            _field("enabled", "", "bool"),
        ])
        body = {"id": 123, "amount": "100", "enabled": "yes"}
        assert apply_field_types(body, api) == {
            "id": "123", "amount": 100, "enabled": True,
        }

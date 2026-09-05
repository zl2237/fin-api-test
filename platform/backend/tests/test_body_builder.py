"""body_builder 模块单测：请求体组装（从接口字段定义构建请求体）。

覆盖 build_request_body / parse_field_value / set_nested 的关键分支，
行为与原 DagExecutor 实现完全一致。
"""
from types import SimpleNamespace

from app.engine.preprocessor import set_nested_value
from app.services.body_builder import build_request_body, parse_field_value


def _field(key, default_value="", field_type="string"):
    return SimpleNamespace(key=key, default_value=default_value, field_type=field_type)


def _api(fields=None, request_template=None):
    return SimpleNamespace(fields=fields or [], request_template=request_template)


class TestBuildRequestBody:
    def test_no_fields_returns_template_deepcopy(self):
        tpl = {"a": 1, "b": {"c": 2}}
        api = _api(fields=[], request_template=tpl)
        body = build_request_body(api)
        assert body == {"a": 1, "b": {"c": 2}}
        # deepcopy：修改返回值不影响原模板
        body["b"]["c"] = 999
        assert tpl["b"]["c"] == 2

    def test_no_fields_template_none_returns_empty(self):
        api = _api(fields=[], request_template=None)
        assert build_request_body(api) == {}

    def test_fields_assemble_flat(self):
        api = _api(
            fields=[_field("bl_no", "BL001", "string"), _field("amount", "100", "int")],
            request_template={},
        )
        assert build_request_body(api) == {"bl_no": "BL001", "amount": 100}

    def test_fields_nested_path(self):
        api = _api(
            fields=[_field("to_customer.put_amount", "50", "int")],
            request_template={},
        )
        assert build_request_body(api) == {"to_customer": {"put_amount": 50}}

    def test_array_body_wrapped_in_list(self):
        # request_template 为 list → 数组请求体，结果包裹为 [{...}]
        api = _api(
            fields=[_field("id", "x", "string")],
            request_template=[],
        )
        assert build_request_body(api) == [{"id": "x"}]

    def test_field_with_empty_key_skipped(self):
        api = _api(
            fields=[_field("", "v", "string"), _field("keep", "v", "string")],
            request_template={},
        )
        assert build_request_body(api) == {"keep": "v"}

    def test_expression_value_preserved(self):
        # 含 ${} 的值原样保留，待表达式引擎求值
        api = _api(fields=[_field("order_id", "${order_id}", "string")], request_template={})
        assert build_request_body(api) == {"order_id": "${order_id}"}

    def test_array_field_json_parsed(self):
        api = _api(fields=[_field("ids", '["1","2"]', "array")], request_template={})
        assert build_request_body(api) == {"ids": ["1", "2"]}

    def test_none_fields_attr_falls_back_to_template(self):
        # getattr(api, "fields", None) 为 None 时回退模板
        api = SimpleNamespace(fields=None, request_template={"x": 1})
        assert build_request_body(api) == {"x": 1}


class TestParseFieldValue:
    def test_none_string_returns_empty(self):
        assert parse_field_value(None, "string") == ""
        assert parse_field_value("", "string") == ""

    def test_none_non_string_returns_none(self):
        assert parse_field_value(None, "int") is None
        assert parse_field_value("", "array") is None

    def test_expression_preserved(self):
        assert parse_field_value("${order_id}", "string") == "${order_id}"
        assert parse_field_value("[${id}]", "array") == "[${id}]"

    def test_array_json_parsed(self):
        assert parse_field_value('[1, 2, 3]', "array") == [1, 2, 3]

    def test_array_invalid_json_kept(self):
        assert parse_field_value("not json", "array") == "not json"

    def test_object_json_parsed(self):
        assert parse_field_value('{"k": "v"}', "object") == {"k": "v"}

    def test_int_parsed(self):
        assert parse_field_value("123", "int") == 123

    def test_int_invalid_kept(self):
        assert parse_field_value("abc", "int") == "abc"

    def test_bool_truthy(self):
        assert parse_field_value("true", "bool") is True
        assert parse_field_value("1", "bool") is True
        assert parse_field_value("yes", "bool") is True

    def test_bool_falsy(self):
        assert parse_field_value("false", "bool") is False
        assert parse_field_value("no", "bool") is False
        assert parse_field_value("0", "bool") is False

    def test_string_passthrough(self):
        assert parse_field_value("hello", "string") == "hello"


class TestSetNestedValue:
    """嵌套设值统一后的语义（build_request_body 与编排 set_field 共用）"""

    def test_simple_key(self):
        d = {}
        set_nested_value(d, "a", 1)
        assert d == {"a": 1}

    def test_nested_path(self):
        d = {}
        set_nested_value(d, "a.b.c", 1)
        assert d == {"a": {"b": {"c": 1}}}

    def test_overwrite_non_dict_intermediate(self):
        # 中间节点是非 dict 字符串，应被替换为 dict
        d = {"a": "x"}
        set_nested_value(d, "a.b", 1)
        assert d == {"a": {"b": 1}}

    def test_existing_dict_intermediate_preserved(self):
        d = {"a": {"existing": 1}}
        set_nested_value(d, "a.b", 2)
        assert d == {"a": {"existing": 1, "b": 2}}

    def test_list_index_into_existing_list(self):
        # 统一实现的既有语义：数字路径段只索引已存在的列表（与编排 set_field 同一行为）
        d = {"items": [{"name": "a"}]}
        set_nested_value(d, "items.0.name", "b")
        assert d == {"items": [{"name": "b"}]}

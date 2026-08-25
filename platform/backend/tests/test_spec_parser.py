"""spec_parser 模块单测：从 Swagger/OpenAPI 提取字段、生成接口编码。

覆盖 path_to_code / resolve_ref / swagger_type_to_field_type /
pick_default_value / coerce_default / extract_fields_from_spec 的关键分支。
"""
from app.services.spec_parser import (
    coerce_default,
    extract_fields_from_spec,
    path_to_code,
    pick_default_value,
    resolve_ref,
    swagger_type_to_field_type,
)


class TestPathToCode:
    def test_two_segments(self):
        assert path_to_code("/api/order/create", "POST") == "order_create_post"

    def test_single_segment(self):
        assert path_to_code("/login", "get") == "login_get"

    def test_skips_path_param(self):
        # {id} 段不计入，取最后两段非参数段
        assert path_to_code("/api/order/{id}/submit", "POST") == "order_submit_post"

    def test_only_path_param(self):
        assert path_to_code("/{id}", "GET") == "api_get"

    def test_root_path(self):
        assert path_to_code("/", "GET") == "api_get"

    def test_method_lowercased(self):
        assert path_to_code("/a/b", "Delete") == "a_b_delete"

    def test_trailing_slash(self):
        assert path_to_code("/api/order/create/", "POST") == "order_create_post"


class TestResolveRef:
    def test_v3_components_schemas(self):
        spec = {"components": {"schemas": {"Order": {"type": "object"}}}}
        assert resolve_ref("#/components/schemas/Order", spec) == {"type": "object"}

    def test_v2_definitions(self):
        spec = {"definitions": {"Item": {"type": "string"}}}
        assert resolve_ref("#/definitions/Item", spec) == {"type": "string"}

    def test_components_parameters(self):
        spec = {"components": {"parameters": {"Page": {"name": "page"}}}}
        assert resolve_ref("#/components/parameters/Page", spec) == {"name": "page"}

    def test_empty_ref(self):
        assert resolve_ref("", {}) == {}

    def test_missing_target(self):
        assert resolve_ref("#/components/schemas/Nope", {}) == {}


class TestSwaggerTypeToFieldType:
    def test_mapping(self):
        assert swagger_type_to_field_type("string") == "string"
        assert swagger_type_to_field_type("integer") == "int"
        assert swagger_type_to_field_type("number") == "string"
        assert swagger_type_to_field_type("boolean") == "bool"
        assert swagger_type_to_field_type("array") == "array"
        assert swagger_type_to_field_type("object") == "object"

    def test_unknown_falls_back_string(self):
        assert swagger_type_to_field_type("whatever") == "string"


class TestPickDefaultValue:
    def test_default_first(self):
        assert pick_default_value({"default": "d", "example": "e"}) == "d"

    def test_example_singular(self):
        assert pick_default_value({"example": "e"}) == "e"

    def test_examples_plural_with_value(self):
        node = {"examples": {"a": {"value": "v"}}}
        assert pick_default_value(node) == "v"

    def test_enum_first(self):
        assert pick_default_value({"enum": ["x", "y"]}) == "x"

    def test_empty_when_nothing(self):
        assert pick_default_value({}) == ""

    def test_non_dict(self):
        assert pick_default_value("not a dict") == ""

    def test_default_none_falls_through(self):
        # default 显式为 None 时回退到 example
        assert pick_default_value({"default": None, "example": "e"}) == "e"


class TestCoerceDefault:
    def test_empty_string(self):
        assert coerce_default("", "string") == ""

    def test_none(self):
        assert coerce_default(None, "string") == ""

    def test_string_value(self):
        assert coerce_default("abc", "string") == "abc"

    def test_int_to_string(self):
        assert coerce_default(123, "int") == "123"

    def test_array_json_serialized(self):
        assert coerce_default([1, 2], "array") == "[1, 2]"

    def test_object_json_serialized(self):
        assert coerce_default({"a": 1}, "object") == '{"a": 1}'

    def test_array_already_string_kept(self):
        assert coerce_default("[1,2]", "array") == "[1,2]"

    def test_ensure_ascii_false(self):
        assert coerce_default({"k": "中文"}, "object") == '{"k": "中文"}'


class TestExtractFieldsFromSpecV3:
    def _v3_spec(self):
        return {
            "openapi": "3.0.0",
            "components": {
                "schemas": {
                    "Order": {
                        "type": "object",
                        "required": ["bl_no"],
                        "properties": {
                            "bl_no": {"type": "string", "default": "BL001"},
                            "amount": {"type": "number", "example": 100.5},
                            "items": {"type": "array"},
                        },
                    }
                },
                "parameters": {
                    "PageParam": {"in": "query", "name": "page", "schema": {"type": "integer", "default": 1}},
                },
            },
        }

    def test_v3_body_fields_imported(self):
        spec = self._v3_spec()
        info = {
            "requestBody": {
                "content": {
                    "application/json": {
                        "schema": {"$ref": "#/components/schemas/Order"}
                    }
                }
            }
        }
        fields, is_array = extract_fields_from_spec(info, spec, is_v3=True)
        keys = {f.key for f in fields}
        assert keys == {"bl_no", "amount", "items"}
        assert is_array is False
        # required 标记
        bl = next(f for f in fields if f.key == "bl_no")
        assert bl.required is True
        assert bl.default_value == "BL001"
        # number -> string
        amt = next(f for f in fields if f.key == "amount")
        assert amt.field_type == "string"
        assert amt.default_value == "100.5"

    def test_v3_query_param_with_default(self):
        spec = self._v3_spec()
        info = {"parameters": [{"$ref": "#/components/parameters/PageParam"}]}
        fields, _ = extract_fields_from_spec(info, spec, is_v3=True)
        assert len(fields) == 1
        assert fields[0].key == "page"
        assert fields[0].field_type == "int"
        assert fields[0].default_value == "1"

    def test_v3_query_param_without_default_skipped(self):
        spec = self._v3_spec()
        info = {"parameters": [{"in": "query", "name": "noparam", "schema": {"type": "string"}}]}
        fields, _ = extract_fields_from_spec(info, spec, is_v3=True)
        assert fields == []

    def test_v3_header_param_skipped(self):
        spec = self._v3_spec()
        info = {"parameters": [{"in": "header", "name": "X-Trace", "schema": {"type": "string", "default": "t"}}]}
        fields, _ = extract_fields_from_spec(info, spec, is_v3=True)
        assert fields == []

    def test_v3_array_body(self):
        spec = {
            "openapi": "3.0.0",
            "components": {"schemas": {"Item": {"type": "object", "properties": {"id": {"type": "string", "default": "x"}}}}},
        }
        info = {
            "requestBody": {
                "content": {"application/json": {"schema": {"type": "array", "items": {"$ref": "#/components/schemas/Item"}}}}
            }
        }
        fields, is_array = extract_fields_from_spec(info, spec, is_v3=True)
        assert is_array is True
        assert [f.key for f in fields] == ["id"]

    def test_v3_schema_top_example_fallback(self):
        """body 字段无自身默认值时，回退 schema 顶层 example[key]"""
        spec = {"openapi": "3.0.0"}
        info = {
            "requestBody": {
                "content": {
                    "application/json": {
                        "schema": {
                            "type": "object",
                            "properties": {"foo": {"type": "string"}},
                            "example": {"foo": "from_schema_example"},
                        }
                    }
                }
            }
        }
        fields, _ = extract_fields_from_spec(info, spec, is_v3=True)
        foo = next(f for f in fields if f.key == "foo")
        assert foo.default_value == "from_schema_example"


class TestExtractFieldsFromSpecV2:
    def test_v2_body_param(self):
        spec = {"definitions": {"Body": {"type": "object", "properties": {"name": {"type": "string", "default": "n"}}}}}
        info = {
            "parameters": [
                {"in": "query", "name": "q", "type": "string", "default": "qv"},
                {"in": "body", "name": "body", "schema": {"$ref": "#/definitions/Body"}},
            ]
        }
        fields, is_array = extract_fields_from_spec(info, spec, is_v3=False)
        keys = [f.key for f in fields]
        assert keys == ["q", "name"]
        assert is_array is False

    def test_v2_query_without_default_skipped(self):
        spec = {}
        info = {"parameters": [{"in": "query", "name": "q", "type": "string"}]}
        fields, _ = extract_fields_from_spec(info, spec, is_v3=False)
        assert fields == []

    def test_empty_info(self):
        fields, is_array = extract_fields_from_spec({}, {}, is_v3=True)
        assert fields == []
        assert is_array is False

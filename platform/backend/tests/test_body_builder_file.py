"""body_builder file 类型字段单测：覆盖 file 类型字段的请求体构建与剥离。

- parse_field_value 支持 file 类型（原样保留 file_id 字符串）
- pop_file_fields_from_body 从 body 中剥离 file 字段，单独返回供 multipart 构建
"""
from types import SimpleNamespace

from app.services.body_builder import (
    build_request_body,
    parse_field_value,
    pop_file_fields_from_body,
)


def _field(key, default_value="", field_type="string"):
    return SimpleNamespace(key=key, default_value=default_value, field_type=field_type)


def _api(fields=None, request_template=None):
    return SimpleNamespace(fields=fields or [], request_template=request_template)


class TestParseFieldValueFile:
    def test_file_empty_returns_none(self):
        assert parse_field_value(None, "file") is None
        assert parse_field_value("", "file") is None

    def test_file_id_preserved(self):
        assert parse_field_value("123", "file") == "123"

    def test_file_expression_preserved(self):
        # 含 ${} 表达式的 file 值原样保留（理论上 file 类型暂不支持表达式，但解析层兼容）
        assert parse_field_value("${file_id}", "file") == "${file_id}"


class TestBuildRequestBodyWithFile:
    def test_file_field_included_in_body(self):
        # file 类型字段在 build_request_body 阶段保留在 body 中
        # 后续由 pop_file_fields_from_body 剥离
        api = _api(
            fields=[
                _field("order_id", "ORD001", "string"),
                _field("id_card", "123", "file"),
            ],
            request_template={},
        )
        body = build_request_body(api)
        assert body == {"order_id": "ORD001", "id_card": "123"}

    def test_mixed_file_and_normal_fields(self):
        api = _api(
            fields=[
                _field("name", "test", "string"),
                _field("amount", "100", "int"),
                _field("file1", "456", "file"),
                _field("file2", "789", "file"),
            ],
            request_template={},
        )
        body = build_request_body(api)
        assert body == {
            "name": "test",
            "amount": 100,
            "file1": "456",
            "file2": "789",
        }


class TestPopFileFieldsFromBody:
    def test_pop_single_file_from_dict(self):
        api = _api(
            fields=[
                _field("order_id", "ORD001", "string"),
                _field("id_card", "123", "file"),
            ],
            request_template={},
        )
        body = {"order_id": "ORD001", "id_card": "123"}
        body, file_fields = pop_file_fields_from_body(body, api)
        assert body == {"order_id": "ORD001"}
        assert file_fields == [("id_card", "123")]

    def test_pop_multiple_files_from_dict(self):
        api = _api(
            fields=[
                _field("file1", "100", "file"),
                _field("file2", "200", "file"),
            ],
            request_template={},
        )
        body = {"file1": "100", "file2": "200", "name": "test"}
        body, file_fields = pop_file_fields_from_body(body, api)
        assert body == {"name": "test"}
        assert sorted(file_fields) == [("file1", "100"), ("file2", "200")]

    def test_pop_nested_file_from_dict(self):
        api = _api(
            fields=[
                _field("to_customer.id_card", "123", "file"),
            ],
            request_template={},
        )
        body = {"to_customer": {"id_card": "123", "name": "test"}}
        body, file_fields = pop_file_fields_from_body(body, api)
        assert body == {"to_customer": {"name": "test"}}
        assert file_fields == [("to_customer.id_card", "123")]

    def test_pop_from_array_body(self):
        api = _api(
            fields=[
                _field("file1", "100", "file"),
            ],
            request_template=[],
        )
        body = [{"file1": "100", "name": "test"}]
        body, file_fields = pop_file_fields_from_body(body, api)
        assert body == [{"name": "test"}]
        assert file_fields == [("file1", "100")]

    def test_pop_no_file_fields_unchanged(self):
        api = _api(
            fields=[
                _field("name", "test", "string"),
            ],
            request_template={},
        )
        body = {"name": "test"}
        body, file_fields = pop_file_fields_from_body(body, api)
        assert body == {"name": "test"}
        assert file_fields == []

    def test_pop_skips_empty_file_value(self):
        api = _api(
            fields=[
                _field("file1", "", "file"),
                _field("file2", "200", "file"),
            ],
            request_template={},
        )
        body = {"file1": "", "file2": "200"}
        body, file_fields = pop_file_fields_from_body(body, api)
        # file1 值为空被 pop 但不加入 file_list
        assert "file1" not in body
        assert "file2" not in body
        assert file_fields == [("file2", "200")]


class TestFileFieldEndToEnd:
    """端到端：build_request_body → pop_file_fields_from_body"""

    def test_build_then_pop(self):
        api = _api(
            fields=[
                _field("order_id", "ORD001", "string"),
                _field("amount", "100", "int"),
                _field("id_card", "456", "file"),
            ],
            request_template={},
        )
        body = build_request_body(api)
        assert body == {"order_id": "ORD001", "amount": 100, "id_card": "456"}
        body, file_fields = pop_file_fields_from_body(body, api)
        assert body == {"order_id": "ORD001", "amount": 100}
        assert file_fields == [("id_card", "456")]

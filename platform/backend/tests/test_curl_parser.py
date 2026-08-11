"""curl_parser 模块单测：验证 cURL 命令解析为预览项的正确性。"""
from app.engine.curl_parser import parse_curl_to_previews, _split_curl_commands


class TestSplitCurlCommands:
    def test_single_command(self):
        cmds = _split_curl_commands("curl 'http://host/api/test'")
        assert len(cmds) == 1

    def test_multiple_commands_blank_line_separated(self):
        text = "curl 'http://host/api/a'\n\ncurl 'http://host/api/b'"
        cmds = _split_curl_commands(text)
        assert len(cmds) == 2

    def test_continuation_line(self):
        # 续行符 \ 后跟换行应合并
        text = "curl -X POST 'http://host/api/test' \\\n  -H 'Content-Type: application/json'"
        cmds = _split_curl_commands(text)
        assert len(cmds) == 1
        assert "Content-Type" in cmds[0]


class TestParseCurlToPreviews:
    def test_simple_get(self):
        text = "curl 'http://host/api/list?page=1&size=10'"
        previews, errors = parse_curl_to_previews(text)
        assert len(previews) == 1
        assert len(errors) == 0
        p = previews[0]
        assert p["method"] == "GET"
        assert p["path"] == "/api/list"
        # query 参数应被提取为字段
        keys = [f["key"] for f in p["fields"]]
        assert "page" in keys
        assert "size" in keys

    def test_post_with_json_body(self):
        text = """curl -X POST 'http://host/api/order/create' \\
        -H 'Content-Type: application/json' \\
        -d '{"bl_no":"BL001","amount":100}'"""
        previews, errors = parse_curl_to_previews(text)
        assert len(previews) == 1
        assert len(errors) == 0
        p = previews[0]
        assert p["method"] == "POST"
        assert p["path"] == "/api/order/create"
        assert p["is_array_body"] is False
        # body 字段应被提取
        field_map = {f["key"]: f for f in p["fields"]}
        assert "bl_no" in field_map
        assert field_map["bl_no"]["field_type"] == "string"
        assert field_map["bl_no"]["default_value"] == "BL001"
        assert "amount" in field_map
        assert field_map["amount"]["field_type"] == "int"

    def test_array_body(self):
        text = """curl -X POST 'http://host/api/batch' \\
        -H 'Content-Type: application/json' \\
        -d '[{"bl_no":"BL001"},{"bl_no":"BL002"}]'"""
        previews, errors = parse_curl_to_previews(text)
        assert len(previews) == 1
        p = previews[0]
        assert p["is_array_body"] is True
        # 取第一个元素的字段
        keys = [f["key"] for f in p["fields"]]
        assert "bl_no" in keys

    def test_method_inferred_from_data(self):
        # 无 -X 但有 -d，应推断为 POST
        text = "curl 'http://host/api/create' -d '{\"k\":\"v\"}'"
        previews, errors = parse_curl_to_previews(text)
        assert len(previews) == 1
        assert previews[0]["method"] == "POST"

    def test_dedup_same_method_path(self):
        text = """curl 'http://host/api/list'

        curl 'http://host/api/list'"""
        previews, errors = parse_curl_to_previews(text)
        assert len(previews) == 1
        # 第二条应被跳过
        assert len(errors) == 1
        assert "重复" in errors[0]

    def test_multiple_commands(self):
        text = """curl 'http://host/api/a'

        curl -X POST 'http://host/api/b' -d '{"x":1}'"""
        previews, errors = parse_curl_to_previews(text)
        assert len(previews) == 2
        paths = [p["path"] for p in previews]
        assert "/api/a" in paths
        assert "/api/b" in paths

    def test_double_quotes_url(self):
        text = 'curl "http://host/api/test"'
        previews, errors = parse_curl_to_previews(text)
        assert len(previews) == 1
        assert previews[0]["path"] == "/api/test"

    def test_skip_options(self):
        text = "curl -X OPTIONS 'http://host/api/test'"
        previews, errors = parse_curl_to_previews(text)
        assert len(previews) == 0
        assert len(errors) == 1

    def test_malformed_returns_error(self):
        text = "curl -X"  # 缺少方法和 URL
        previews, errors = parse_curl_to_previews(text)
        assert len(previews) == 0
        assert len(errors) == 1

    def test_data_raw_flag(self):
        text = """curl -X POST 'http://host/api/test' --data-raw '{"name":"test"}'"""
        previews, errors = parse_curl_to_previews(text)
        assert len(previews) == 1
        keys = [f["key"] for f in previews[0]["fields"]]
        assert "name" in keys

    def test_bool_field_type(self):
        text = """curl -X POST 'http://host/api/test' -d '{"enabled":true}'"""
        previews, _ = parse_curl_to_previews(text)
        field_map = {f["key"]: f for f in previews[0]["fields"]}
        assert field_map["enabled"]["field_type"] == "bool"

    def test_array_field_type(self):
        text = """curl -X POST 'http://host/api/test' -d '{"ids":[1,2,3]}'"""
        previews, _ = parse_curl_to_previews(text)
        field_map = {f["key"]: f for f in previews[0]["fields"]}
        assert field_map["ids"]["field_type"] == "array"

    def test_no_url_returns_error(self):
        text = "curl -X POST -H 'Content-Type: application/json'"
        previews, errors = parse_curl_to_previews(text)
        assert len(previews) == 0
        assert len(errors) >= 1

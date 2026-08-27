"""curl_parser 模块单测：验证 cURL 命令解析为预览项的正确性。"""
from app.engine.curl_parser import _split_curl_commands, parse_curl_to_previews


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

    def test_backtick_wrapped_url_cleaned(self):
        # markdown/聊天工具复制的 cURL，URL 外层常带成对反引号，应剥离后再解析
        text = "curl --url '`http://host/api/login`' -H 'Content-Type: application/json' -d '{\"u\":1}'"
        previews, errors = parse_curl_to_previews(text)
        assert len(errors) == 0
        assert previews[0]["path"] == "/api/login"
        assert previews[0]["url"] == "http://host/api/login"

    def test_backtick_wrapped_bare_url_cleaned(self):
        # 裸 URL 位置（无 --url）同样清洗
        text = "curl '`http://host/api/list`'"
        previews, errors = parse_curl_to_previews(text)
        assert len(errors) == 0
        assert previews[0]["path"] == "/api/list"

    def test_form_urlencoded_body_fields(self):
        # x-www-form-urlencoded：按键值对拆解为 body 字段，键值 URL 解码
        text = """curl --url 'http://host/admin/Home/Public/index' \\
        -H 'Content-Type: application/x-www-form-urlencoded' \\
        --data-raw 'data%5Busername%5D=yhxzl&data%5Bpassword%5D=zl179178%40%40%40&data%5Bremember%5D=0'"""
        previews, errors = parse_curl_to_previews(text)
        assert len(errors) == 0
        p = previews[0]
        assert p["method"] == "POST"
        assert p["content_type"] == "application/x-www-form-urlencoded"
        field_map = {f["key"]: f for f in p["fields"]}
        assert field_map["data[username]"]["default_value"] == "yhxzl"
        # %40 解码为 @
        assert field_map["data[password]"]["default_value"] == "zl179178@@@"
        assert field_map["data[remember]"]["default_value"] == "0"


class TestMultipartFormdata:
    def test_chrome_data_raw_multipart(self):
        # Chrome「Copy as cURL」的 multipart 完整报文（--data-raw $'...\r\n...'）：
        # 文本 part 与文件 part 都应提取为 body 字段
        text = r"""curl --url 'https://fin.example.com/api/order/orderDocument/uploadOrderDocument' \
  -H 'Content-Type: multipart/form-data; boundary=----WebKitFormBoundaryabc' \
  --data-raw $'------WebKitFormBoundaryabc\r\nContent-Disposition: form-data; name="order_id"\r\n\r\n351258043645689856\r\n------WebKitFormBoundaryabc\r\nContent-Disposition: form-data; name="document_type"\r\n\r\nDECLARATION\r\n------WebKitFormBoundaryabc\r\nContent-Disposition: form-data; name="file"; filename="报关单.pdf"\r\nContent-Type: application/pdf\r\n\r\n\r\n------WebKitFormBoundaryabc--\r\n'"""
        previews, errors = parse_curl_to_previews(text)
        assert len(errors) == 0
        p = previews[0]
        assert p["method"] == "POST"
        field_map = {f["key"]: f for f in p["fields"]}
        # 文本 part：实际值作默认值
        assert field_map["order_id"]["field_type"] == "string"
        assert field_map["order_id"]["default_value"] == "351258043645689856"
        assert field_map["document_type"]["default_value"] == "DECLARATION"
        # 文件 part：file 字段，默认值留空（运行时从文件中心选）
        assert field_map["file"]["field_type"] == "file"
        assert field_map["file"]["default_value"] == ""

    def test_form_flag_multipart(self):
        # -F/--form 形式：@ 文件 → file 字段；键值对 → string 字段
        text = """curl 'http://host/api/upload' -F 'order_id=123' -F 'file=@报关单.pdf'"""
        previews, errors = parse_curl_to_previews(text)
        assert len(errors) == 0
        p = previews[0]
        assert p["method"] == "POST"
        assert p["content_type"] == "multipart/form-data"
        field_map = {f["key"]: f for f in p["fields"]}
        assert field_map["order_id"]["field_type"] == "string"
        assert field_map["order_id"]["default_value"] == "123"
        assert field_map["file"]["field_type"] == "file"

    def test_multipart_without_boundary_no_crash(self):
        # Content-Type 声明 multipart 但无 boundary：静默跳过，不产出字段也不报错
        text = """curl 'http://host/api/upload' -H 'Content-Type: multipart/form-data' -d 'xxx'"""
        previews, errors = parse_curl_to_previews(text)
        assert len(errors) == 0
        assert previews[0]["fields"] == []

    def test_multipart_lf_line_endings(self):
        # 报文用 \n（而非 \r\n）换行的 ANSI-C 字面转义，同样应解析
        text = r"""curl 'http://host/api/upload' -H 'Content-Type: multipart/form-data; boundary=BB' --data-raw $'--BB\nContent-Disposition: form-data; name="a"\n\n1\n--BB--\n'"""
        previews, errors = parse_curl_to_previews(text)
        assert len(errors) == 0
        field_map = {f["key"]: f for f in previews[0]["fields"]}
        assert field_map["a"]["default_value"] == "1"

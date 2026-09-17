"""HttpClient 响应处理单测：非对象 JSON（裸标量/数组/null）按解析失败对待。

背景：ThinkPHP 后台接口常返回裸标量 JSON（如 "-404"），resp.json() 解析成功但
得到 str/list，原实现直接 resp_json.get("code") 抛 AttributeError，
调试/执行界面只能看到"未预期异常"，真实响应被吞。
"""
import io
from types import SimpleNamespace

import requests

import pytest
from utils.exceptions import AuthError, BusinessError, JsonParseError
from utils.http_client import HttpClient


class FakeRawResponse:
    def __init__(self, status_code=200, json_value=None, json_exc=None, text=""):
        self.status_code = status_code
        self.text = text or str(json_value)
        self._json_value = json_value
        self._json_exc = json_exc

    def json(self):
        if self._json_exc:
            raise self._json_exc
        return self._json_value


class FakeSession:
    def __init__(self, resp):
        self.resp = resp

    def request(self, method, url, headers=None, params=None, json=None, data=None, files=None, timeout=None):
        return self.resp


def _client(resp):
    c = HttpClient(base_url="http://t")
    c.session = FakeSession(resp)
    return c


class TestNonDictJsonResponse:
    def test_scalar_json_string_raises_json_parse_error(self):
        # ThinkPHP 裸标量响应 "-404"：解析成功但非 dict → JsonParseError（原文可取）
        with pytest.raises(JsonParseError) as ei:
            _client(FakeRawResponse(json_value="-404")).post("/x")
        assert ei.value.resp_text == "-404"

    def test_json_array_raises_json_parse_error(self):
        with pytest.raises(JsonParseError):
            _client(FakeRawResponse(json_value=[{"a": 1}])).get("/x")

    def test_json_null_raises_json_parse_error(self):
        # 合法 JSON null → json() 返回 None，与解析失败同等对待（原行为保持）
        with pytest.raises(JsonParseError):
            _client(FakeRawResponse(json_value=None)).get("/x")

    def test_invalid_json_raises_json_parse_error(self):
        with pytest.raises(JsonParseError):
            _client(FakeRawResponse(json_exc=ValueError("bad"))).get("/x")

    def test_dict_with_code_200_passes(self):
        resp = _client(FakeRawResponse(json_value={"code": 200, "data": 1})).get("/x")
        assert resp == {"code": 200, "data": 1}

    def test_dict_with_other_code_raises_business_error(self):
        with pytest.raises(BusinessError) as ei:
            _client(FakeRawResponse(json_value={"code": 40001, "msg": "x"})).get("/x")
        assert ei.value.code == 40001

    def test_dict_with_code_null_passes(self):
        # ThinkPHP 系统成功响应 {"code":null,...}：无业务码约定可依，
        # 不判业务失败，原样返回交断言裁决
        body = {"code": None, "auth": {"c1": {"search_btn": True}}}
        assert _client(FakeRawResponse(json_value=body)).get("/x") == body

    def test_dict_without_code_field_passes(self):
        # 响应不含 code 字段：同样不判业务失败
        body = {"list": [1, 2], "count": 2}
        assert _client(FakeRawResponse(json_value=body)).get("/x") == body

    def test_scalar_405_code_not_treated_as_auth_expire(self):
        # resp_json 非 dict 时不得因 code==405 误判鉴权失效（isinstance 守卫）
        # str "-404" 直接走 JsonParseError，不触发重登回调
        c = _client(FakeRawResponse(json_value="-404"))
        called = []
        c.set_token_refresh_callback(lambda: called.append(1))
        with pytest.raises(JsonParseError):
            c.get("/x")
        assert called == []


class TestSuccessCodes:
    """业务成功码：环境可配置（不同系统约定不同），命中任一即成功。"""

    def test_default_success_codes_200(self):
        # 未配置时默认 {200}：code:1 判为业务失败（平台原约定）
        with pytest.raises(BusinessError):
            _client(FakeRawResponse(json_value={"code": 1, "msg": "获取成功"})).get("/x")

    def test_configured_codes_accept_code_1(self):
        # 配置 "200,1"（ThinkPHP 系）后 code:1 通过——修复点
        c = _client(FakeRawResponse(json_value={"code": 1, "msg": "获取成功"}))
        c.set_success_codes("200,1")
        assert c.get("/x") == {"code": 1, "msg": "获取成功"}

    def test_configured_code_still_rejects_others(self):
        c = _client(FakeRawResponse(json_value={"code": 0, "msg": "失败"}))
        c.set_success_codes("200,1")
        with pytest.raises(BusinessError) as ei:
            c.get("/x")
        assert ei.value.code == 0

    def test_int_code_matches_string_config(self):
        # 响应 code 为 int 1，配置为字符串 "1"：归一化字符串比较命中
        c = _client(FakeRawResponse(json_value={"code": 1}))
        c.set_success_codes("1")
        assert c.get("/x") == {"code": 1}

    def test_list_input_supported(self):
        c = HttpClient()
        c.set_success_codes([200, 1, 0])
        assert c.success_codes == {"200", "1", "0"}

    def test_whitespace_and_empty_parts_ignored(self):
        c = HttpClient()
        c.set_success_codes(" 200 , 1 ,")
        assert c.success_codes == {"200", "1"}

    def test_none_or_empty_keeps_current(self):
        c = HttpClient()
        c.set_success_codes(None)
        assert c.success_codes == {"200"}
        c.set_success_codes("")
        assert c.success_codes == {"200"}
        c.set_success_codes("1")
        c.set_success_codes(" , ")  # 全空部分：保持现值不覆盖
        assert c.success_codes == {"1"}


class _SeqSession:
    """按序返回预置响应（重登重试链路：失败响应 → 成功响应）"""

    def __init__(self, resps):
        self.resps = list(resps)

    def request(self, method, url, headers=None, params=None, json=None, data=None, files=None, timeout=None):
        return self.resps.pop(0)


def _seq_client(*resps):
    c = HttpClient(base_url="http://t")
    c.session = _SeqSession(resps)
    return c


class TestAuthExpireCodes:
    """鉴权失效业务码：HTTP 200 + code 命中集合 → 触发重登回调并重试当前请求"""

    def test_default_405_triggers_refresh_and_retry(self):
        # 默认集合 {401,405}：code 405（异地登录）自动重登后重试成功
        c = _seq_client(
            FakeRawResponse(json_value={"code": 405, "msg": "账号异地登录"}),
            FakeRawResponse(json_value={"code": 200, "data": {"ok": 1}}),
        )
        refreshed = []
        c.set_token_refresh_callback(lambda: refreshed.append(1))
        assert c.get("/x") == {"code": 200, "data": {"ok": 1}}
        assert refreshed == [1]

    def test_configured_407_triggers_refresh_and_retry(self):
        # fin 系统：登录过期返回 HTTP 200 + code 407——配置后自动重登（修复点）
        c = _seq_client(
            FakeRawResponse(json_value={"code": 407, "msg": "登录已过期"}),
            FakeRawResponse(json_value={"code": 200, "data": {"ok": 1}}),
        )
        c.set_auth_expire_codes([407, 405])
        refreshed = []
        c.set_token_refresh_callback(lambda: refreshed.append(1))
        assert c.get("/x") == {"code": 200, "data": {"ok": 1}}
        assert refreshed == [1]

    def test_407_not_configured_raises_business_error(self):
        # 未配置时 407 是普通业务失败：不触发重登，BusinessError 交断言裁决
        c = _client(FakeRawResponse(json_value={"code": 407, "msg": "登录已过期"}))
        called = []
        c.set_token_refresh_callback(lambda: called.append(1))
        with pytest.raises(BusinessError) as ei:
            c.get("/x")
        assert ei.value.code == 407
        assert called == []

    def test_string_code_matches_int_config(self):
        # 响应 code 为字符串 "407"、配置为 int 407：归一化字符串比较命中
        c = _seq_client(
            FakeRawResponse(json_value={"code": "407", "msg": "登录已过期"}),
            FakeRawResponse(json_value={"code": 200, "data": 1}),
        )
        c.set_auth_expire_codes(407)
        c.set_token_refresh_callback(lambda: None)
        assert c.get("/x") == {"code": 200, "data": 1}

    def test_refresh_failure_raises_auth_error(self):
        # 重登回调抛异常 → AuthError（不再重试）
        c = _seq_client(FakeRawResponse(json_value={"code": 407, "msg": "登录已过期"}))
        c.set_auth_expire_codes([407])

        def _boom():
            raise RuntimeError("登录失败")

        c.set_token_refresh_callback(_boom)
        with pytest.raises(AuthError):
            c.get("/x")

    def test_set_auth_expire_codes_normalization(self):
        c = HttpClient()
        assert c.auth_expire_codes == {"401", "405"}
        c.set_auth_expire_codes(None)
        assert c.auth_expire_codes == {"401", "405"}  # 空值保持默认
        c.set_auth_expire_codes("407, 405 ,")
        assert c.auth_expire_codes == {"407", "405"}


class TestAuthExpireGuard:
    def test_dict_code_405_triggers_refresh(self):
        # dict 且 code==405 → 鉴权失效 → 回调刷新后重试成功
        c = HttpClient(base_url="http://t")
        responses = [FakeRawResponse(json_value={"code": 405, "msg": "异地登录"}),
                     FakeRawResponse(json_value={"code": 200})]
        c.session = SimpleNamespace(request=lambda *a, **k: responses.pop(0))
        c.set_token_refresh_callback(lambda: "new-token")
        assert c.get("/x") == {"code": 200}


class MultipartRecordingSession:
    """真实 requests 编码层记录每次 multipart 请求体。

    与 FakeSession 不同：这里用 requests.Request(...).prepare() 真实编码
    files 参数（等价于真实发送时的行为——句柄会被读到 EOF、bytes 原样写入），
    用于复现线上 614：重登重试复用同一 files 引用再次编码。
    """

    def __init__(self, resps):
        self.resps = list(resps)
        self.bodies = []

    def request(self, method, url, headers=None, params=None, json=None, data=None, files=None, timeout=None):
        prepared = requests.Request(method, url, headers=headers, data=data, files=files).prepare()
        self.bodies.append(prepared.body)
        return self.resps.pop(0)


class TestMultipartRetryFidelity:
    """614 回归：鉴权失效(405 异地登录)自动重登重试时，multipart 文件内容必须完整。

    线上真因：修复前 request_sender 传文件句柄，首次编码把句柄读到 EOF，
    重登重试再次编码得到 0 字节文件 part → 服务端报「请选择文件或者文件内容为空」。
    修复后传 read_bytes() 的 bytes，不可变天然幂等。
    """

    FILE_BYTES = b"%PDF-1.4\n614-retry-fidelity-full-content-marker\n%%EOF"

    def _retry_client(self):
        session = MultipartRecordingSession([
            FakeRawResponse(json_value={"code": 405, "msg": "账号异地登录"}),
            FakeRawResponse(json_value={"code": 200, "data": "上传成功"}),
        ])
        c = HttpClient(base_url="http://t")
        c.session = session
        c.set_token_refresh_callback(lambda: "new-token")
        return c, session

    def test_file_bytes_survive_auth_expire_retry(self):
        # bytes 方案：首发 + 405 重登重试，两次编码的请求体均含完整文件内容
        c, session = self._retry_client()
        files = [("file", ("report.pdf", self.FILE_BYTES, "application/pdf"))]
        assert c.post_multipart("/upload", data={"type": "1"}, files=files) == {
            "code": 200, "data": "上传成功"
        }
        assert len(session.bodies) == 2  # 首发一次 + 重试一次
        for i, body in enumerate(session.bodies, 1):
            assert self.FILE_BYTES in body, f"第{i}次请求 multipart 文件内容丢失"

    def test_file_handle_would_lose_content_on_retry(self):
        # 反证句柄方案（修复前实现）必败：同链路下第二次编码文件 part 为空——614 根因复现
        c, session = self._retry_client()
        handle = io.BytesIO(self.FILE_BYTES)
        files = [("file", ("report.pdf", handle, "application/pdf"))]
        assert c.post_multipart("/upload", data={"type": "1"}, files=files) == {
            "code": 200, "data": "上传成功"
        }
        assert self.FILE_BYTES in session.bodies[0]  # 首发：句柄读到内容
        assert self.FILE_BYTES not in session.bodies[1]  # 重试：句柄已在 EOF

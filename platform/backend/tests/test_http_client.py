"""HttpClient 响应处理单测：非对象 JSON（裸标量/数组/null）按解析失败对待。

背景：ThinkPHP 后台接口常返回裸标量 JSON（如 "-404"），resp.json() 解析成功但
得到 str/list，原实现直接 resp_json.get("code") 抛 AttributeError，
调试/执行界面只能看到"未预期异常"，真实响应被吞。
"""
from types import SimpleNamespace

import pytest
from utils.exceptions import BusinessError, JsonParseError
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


class TestAuthExpireGuard:
    def test_dict_code_405_triggers_refresh(self):
        # dict 且 code==405 → 鉴权失效 → 回调刷新后重试成功
        c = HttpClient(base_url="http://t")
        responses = [FakeRawResponse(json_value={"code": 405, "msg": "异地登录"}),
                     FakeRawResponse(json_value={"code": 200})]
        c.session = SimpleNamespace(request=lambda *a, **k: responses.pop(0))
        c.set_token_refresh_callback(lambda: "new-token")
        assert c.get("/x") == {"code": 200}

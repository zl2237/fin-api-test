"""runtime_service 模块单测：HTTP 客户端构建与登录编排。

build_http_client 测真实 HttpClient 的头装配；login 用 FakeClient 测编排逻辑
（占位头 → 提取 token → 渲染鉴权头 → 注册刷新回调 → 异常包装），不触真实网络。
form/session 登录模式用 FakeSession 测 Session 直发路径（表单头覆写/成功校验/Cookie 保持语义）。
"""
import json
from types import SimpleNamespace

import pytest

from app.services import runtime_service
from app.services.runtime_service import (
    _extract_by_jsonpath,
    build_db_client,
    build_http_client,
    login,
)
from app.services.token_cache import EnvTokenCache


@pytest.fixture(autouse=True)
def _reset_token_cache():
    """每个用例前清空共享 token 缓存，避免 shared 模式跨用例污染。"""
    EnvTokenCache._tokens.clear()
    yield
    EnvTokenCache._tokens.clear()


class FakeClient:
    """模拟 HttpClient：记录调用，可控地返回响应或抛异常。"""

    def __init__(self, post_resp=None, exc=None, session=None):
        self.headers = {}
        self._post_resp = post_resp
        self._exc = exc
        self.post_calls = []
        self.set_header_calls = []
        self.refresh_callback = None
        self.session = session

    def set_header(self, name, value):
        self.set_header_calls.append((name, value))
        self.headers[name] = value

    def post(self, path, json=None):
        self.post_calls.append((path, json))
        if self._exc:
            raise self._exc
        return self._post_resp

    def set_token_refresh_callback(self, cb):
        self.refresh_callback = cb


class FakeResponse:
    """模拟 requests.Response。"""

    def __init__(self, status_code=200, json_data=None, text=""):
        self.status_code = status_code
        self._json = json_data
        self.text = text if text else (json.dumps(json_data) if json_data is not None else "")

    def json(self):
        if self._json is None:
            raise ValueError("no json")
        return self._json


class FakeSession:
    """模拟 requests.Session：记录 request 调用，返回预置响应。"""

    def __init__(self, resp):
        self.resp = resp
        self.calls = []
        self.cookies = [SimpleNamespace(name="PHPSESSID")]

    def request(self, method, url, headers=None, json=None, data=None, timeout=None):
        self.calls.append({"method": method, "url": url, "headers": dict(headers or {}),
                           "json": json, "data": data})
        return self.resp


def _env(login_config=None, common_headers=None, base_url="http://test", db_config=None, env_id=1):
    return SimpleNamespace(
        id=env_id,
        login_config=login_config if login_config is not None else {},
        common_headers=common_headers,
        base_url=base_url,
        db_config=db_config if db_config is not None else {},
    )


class TestExtractByJsonpath:
    def test_valid_path(self):
        assert _extract_by_jsonpath({"data": {"token": "T"}}, "$.data.token") == "T"

    def test_no_match(self):
        assert _extract_by_jsonpath({"data": {}}, "$.data.token") is None

    def test_invalid_syntax(self):
        assert _extract_by_jsonpath({}, "$.[broken") is None

    def test_none_data(self):
        assert _extract_by_jsonpath(None, "$.data") is None

    def test_first_match(self):
        assert _extract_by_jsonpath({"a": [1, 2]}, "$.a[0]") == 1


class TestBuildHttpClient:
    def test_common_headers_used(self):
        env = _env(common_headers={"X-A": "1", "X-B": "2"})
        client = build_http_client(env)
        assert client.headers == {"X-A": "1", "X-B": "2"}

    def test_empty_common_headers_defaults_json(self):
        env = _env(common_headers={})
        client = build_http_client(env)
        assert client.headers == {"Content-Type": "application/json"}

    def test_none_common_headers_defaults_json(self):
        env = _env(common_headers=None)
        client = build_http_client(env)
        assert client.headers == {"Content-Type": "application/json"}

    def test_base_url_set(self):
        env = _env(base_url="http://myhost:8080")
        client = build_http_client(env)
        assert client.base_url == "http://myhost:8080"


class TestLogin:
    def test_no_login_body_skips(self):
        env = _env(login_config={})  # 无 login_body
        client = FakeClient()
        # 未配置 login_body 应直接返回，不发请求、不注册回调
        assert login(client, env) is None
        assert client.post_calls == []
        assert client.refresh_callback is None

    def test_login_success_sets_token_header(self):
        env = _env(login_config={
            "login_path": "/api/login",
            "login_body": {"user": "u", "pwd": "p"},
            "token_jsonpath": "$.data.token",
            "auth_header_name": "Authorization",
        })
        client = FakeClient(post_resp={"data": {"token": "TKN"}})
        login(client, env)
        # post 调用一次，路径与请求体正确
        assert client.post_calls == [("/api/login", {"user": "u", "pwd": "p"})]
        # 先设占位头，再用真实 token 覆盖
        assert client.set_header_calls[0] == ("Authorization", "skip-captcha-placeholder")
        assert client.headers["Authorization"] == "TKN"
        # 注册了刷新回调
        assert client.refresh_callback is not None

    def test_auth_header_value_template_default(self):
        env = _env(login_config={
            "login_body": {"u": 1},
            "token_jsonpath": "$.token",
        })
        client = FakeClient(post_resp={"token": "ABC"})
        login(client, env)
        # 默认模板 ${token} → 直接注入
        assert client.headers["Authorization"] == "ABC"

    def test_auth_header_value_template_bearer(self):
        env = _env(login_config={
            "login_body": {"u": 1},
            "token_jsonpath": "$.token",
            "auth_header_value_template": "Bearer ${token}",
        })
        client = FakeClient(post_resp={"token": "XYZ"})
        login(client, env)
        assert client.headers["Authorization"] == "Bearer XYZ"

    def test_auth_header_value_template_with_timestamp(self):
        env = _env(login_config={
            "login_body": {"u": 1},
            "token_jsonpath": "$.token",
            "auth_header_value_template": "${token}_${timestamp}",
        })
        client = FakeClient(post_resp={"token": "T"})
        login(client, env)
        val = client.headers["Authorization"]
        assert val.startswith("T_")
        assert val.split("_", 1)[1].isdigit()  # 时间戳为数字

    def test_custom_auth_header_name(self):
        env = _env(login_config={
            "login_body": {"u": 1},
            "token_jsonpath": "$.token",
            "auth_header_name": "X-Auth-Token",
        })
        client = FakeClient(post_resp={"token": "T"})
        login(client, env)
        assert client.headers["X-Auth-Token"] == "T"

    def test_login_failure_wrapped_runtime_error(self):
        env = _env(login_config={"login_body": {"u": 1}, "token_jsonpath": "$.token"})
        client = FakeClient(exc=ValueError("network down"))
        with pytest.raises(RuntimeError, match="登录失败"):
            login(client, env)

    def test_refresh_callback_success_relogs(self):
        env = _env(login_config={
            "login_body": {"u": 1},
            "token_jsonpath": "$.token",
        })
        client = FakeClient(post_resp={"token": "T1"})
        login(client, env)
        # 第二次登录返回新 token
        client._post_resp = {"token": "T2"}
        result = client.refresh_callback()
        assert result == "T2"
        assert len(client.post_calls) == 2  # 共两次 post
        assert client.headers["Authorization"] == "T2"

    def test_refresh_callback_failure_returns_none(self):
        env = _env(login_config={"login_body": {"u": 1}, "token_jsonpath": "$.token"})
        client = FakeClient(post_resp={"token": "T1"})
        login(client, env)
        # 刷新时登录失败
        client._exc = RuntimeError("boom")
        # 回调失败应返回 None，不抛出
        result = client.refresh_callback()
        assert result is None

    def test_login_token_not_extracted_no_header_overwrite(self):
        # 响应里没有 token → 不覆盖占位头（保留占位值）
        env = _env(login_config={"login_body": {"u": 1}, "token_jsonpath": "$.data.token"})
        client = FakeClient(post_resp={"data": {}})  # 无 token
        login(client, env)
        # 占位头仍在
        assert client.headers["Authorization"] == "skip-captcha-placeholder"
        # 仍注册了刷新回调
        assert client.refresh_callback is not None


class TestTokenShareMode:
    """shared（默认）与 isolated 两种 token 共享模式的登录编排。"""

    def _login_cfg(self, **extra):
        cfg = {"login_body": {"u": 1}, "token_jsonpath": "$.token"}
        cfg.update(extra)
        return cfg

    def test_shared_second_login_reuses_cache(self):
        # 同环境第二次登录：直接复用缓存 token，不发登录请求
        env = _env(login_config=self._login_cfg())
        login(FakeClient(post_resp={"token": "T1"}), env)  # 首登入缓存
        client2 = FakeClient(post_resp={"token": "SHOULD_NOT_BE_USED"})
        login(client2, env)
        assert client2.post_calls == []  # 零登录请求
        assert client2.headers["Authorization"] == "T1"

    def test_shared_different_env_logs_independently(self):
        # 不同环境各自缓存，互不影响
        env_a = _env(login_config=self._login_cfg(), env_id=1)
        env_b = _env(login_config=self._login_cfg(), env_id=2)
        login(FakeClient(post_resp={"token": "A"}), env_a)
        client_b = FakeClient(post_resp={"token": "B"})
        login(client_b, env_b)
        assert client_b.post_calls == [("/api/home/login/userLogin", {"u": 1})]
        assert client_b.headers["Authorization"] == "B"

    def test_shared_refresh_conditional_relogin(self):
        # 401 时缓存已被他人刷新 → 直接复用新 token，不再登录
        env = _env(login_config=self._login_cfg())
        client = FakeClient(post_resp={"token": "T1"})
        login(client, env)
        # 另一个执行刷新了缓存
        EnvTokenCache._tokens[1] = "T2"
        client._post_resp = {"token": "T3"}
        result = client.refresh_callback()
        assert result == "T2"  # 复用他人刷新的，不是自己重登的 T3
        assert len(client.post_calls) == 1  # 没有第二次登录
        assert client.headers["Authorization"] == "T2"

    def test_isolated_mode_bypasses_cache(self):
        # isolated：每次登录独立，不读不写共享缓存
        env = _env(login_config=self._login_cfg(token_share_mode="isolated"))
        login(FakeClient(post_resp={"token": "T1"}), env)
        assert EnvTokenCache.get(1) is None  # 未写缓存
        client2 = FakeClient(post_resp={"token": "T2"})
        login(client2, env)
        assert len(client2.post_calls) == 1  # 自己登录了
        assert client2.headers["Authorization"] == "T2"


class TestLoginSessionMode:
    """session 模式：Session 直发 + Cookie 会话，不提取 token 不注头。"""

    def _cfg(self, **extra):
        cfg = {
            "login_path": "/Home/Public/index",
            "login_body": {"data[username]": "u", "data[password]": "p"},
            "login_mode": "session",
            "login_content_type": "form",
        }
        cfg.update(extra)
        return cfg

    def _client(self, resp):
        session = FakeSession(resp)
        client = FakeClient(session=session)
        client.base_url = "https://test.host"
        return client, session

    def test_form_post_with_urlencoded_header(self):
        # 表单提交：data= 携带键值，Content-Type 覆写为 urlencoded（默认 JSON 头不得残留）
        client, session = self._client(FakeResponse(json_data={"status": 1}))
        client.headers = {"Content-Type": "application/json"}  # 模拟默认头
        login(client, _env(login_config=self._cfg()))
        assert len(session.calls) == 1
        call = session.calls[0]
        assert call["url"] == "https://test.host/Home/Public/index"
        assert call["data"] == {"data[username]": "u", "data[password]": "p"}
        assert call["headers"]["Content-Type"] == "application/x-www-form-urlencoded"
        # session 模式不注鉴权头、不设占位头
        assert client.set_header_calls == []
        assert client.refresh_callback is not None

    def test_check_jsonpath_match_success(self):
        # 成功校验：$.status == 1 才算登录成功
        client, _ = self._client(FakeResponse(json_data={"status": 1, "info": "ok"}))
        cfg = self._cfg(login_check_jsonpath="$.status", login_check_value="1")
        login(client, _env(login_config=cfg))  # 不抛即成功

    def test_check_jsonpath_mismatch_raises(self):
        # 特征不匹配（如验证码错误返回 status:0）→ 登录失败
        client, _ = self._client(FakeResponse(json_data={"status": 0, "info": "验证码错误"}))
        cfg = self._cfg(login_check_jsonpath="$.status", login_check_value="1")
        with pytest.raises(RuntimeError, match="登录失败"):
            login(client, _env(login_config=cfg))

    def test_http_error_raises(self):
        client, _ = self._client(FakeResponse(status_code=500, text="server error"))
        with pytest.raises(RuntimeError, match="登录失败"):
            login(client, _env(login_config=self._cfg()))

    def test_no_check_only_status_200(self):
        # 未配成功校验：HTTP 200 即成功（响应体不解析也不报错）
        client, _ = self._client(FakeResponse(json_data=None, text="<html>login</html>"))
        login(client, _env(login_config=self._cfg()))

    def test_session_mode_not_share_token_cache(self):
        # session 模式不进共享 token 缓存（Cookie 无法跨客户端共享）
        client, _ = self._client(FakeResponse(json_data={"status": 1}))
        login(client, _env(login_config=self._cfg()))
        assert EnvTokenCache.get(1) is None

    def test_refresh_callback_relogin(self):
        # 401 回调重登：再次发登录请求，失败返回 None 不抛
        client, session = self._client(FakeResponse(json_data={"status": 1}))
        login(client, _env(login_config=self._cfg()))
        assert client.refresh_callback() is True
        assert len(session.calls) == 2
        # 换成失败响应后刷新 → None
        session.resp = FakeResponse(status_code=403, text="forbidden")
        assert client.refresh_callback() is None


class TestLoginTokenFormMode:
    """token + form 模式：表单提交但响应提取 token 注入鉴权头。"""

    def test_form_token_extraction(self):
        session = FakeSession(FakeResponse(json_data={"data": {"token": "TKN"}}))
        client = FakeClient(session=session)
        client.base_url = "http://test"
        env = _env(login_config={
            "login_path": "/login",
            "login_body": {"data[username]": "u"},
            "login_mode": "token",
            "login_content_type": "form",
            "token_jsonpath": "$.data.token",
        })
        login(client, env)
        call = session.calls[0]
        assert call["headers"]["Content-Type"] == "application/x-www-form-urlencoded"
        assert call["data"] == {"data[username]": "u"}
        # 占位头先设，真实 token 后覆盖
        assert client.set_header_calls[0] == ("Authorization", "skip-captcha-placeholder")
        assert client.headers["Authorization"] == "TKN"

    def test_form_non_json_response_raises(self):
        session = FakeSession(FakeResponse(json_data=None, text="<html>"))
        client = FakeClient(session=session)
        client.base_url = "http://test"
        env = _env(login_config={
            "login_body": {"u": 1},
            "login_content_type": "form",
        })
        with pytest.raises(RuntimeError, match="登录失败"):
            login(client, env)


class FakeImageResponse:
    """模拟验证码图响应。"""

    def __init__(self, status_code=200, content=b"fake-png"):
        self.status_code = status_code
        self.content = content


class FakeOcr:
    """模拟 ddddocr 识别器：按序返回预置识别码（耗尽后复用最后一个）。"""

    def __init__(self, codes):
        self.codes = list(codes)
        self.calls = 0

    def classification(self, content):
        self.calls += 1
        if len(self.codes) > 1:
            return self.codes.pop(0)
        return self.codes[0]


class FakeCaptchaSession:
    """Session 模拟：GET 验证码图 + request 登录；登录响应按序弹出（耗尽后复用最后一个）。"""

    def __init__(self, login_responses, captcha_resp=None):
        self.login_responses = list(login_responses)
        self.captcha_resp = captcha_resp or FakeImageResponse()
        self.login_calls = []
        self.captcha_calls = []

    def get(self, url, headers=None, timeout=None):
        self.captcha_calls.append({"url": url})
        return self.captcha_resp

    def request(self, method, url, headers=None, json=None, data=None, timeout=None):
        self.login_calls.append({"url": url, "data": data, "json": json})
        if len(self.login_responses) > 1:
            return self.login_responses.pop(0)
        return self.login_responses[0]


class TestLoginCaptcha:
    """验证码自动识别：同会话取图→OCR→填码；识别错换图重试；ddddocr 缺失降级。"""

    def _cfg(self, **extra):
        cfg = {
            "login_path": "/Home/Public/index",
            "login_body": {"data[username]": "u", "data[password]": "p"},
            "login_mode": "session",
            "login_content_type": "form",
            "captcha_url": "/Public/verify.html",
            "captcha_field": "data[verify]",
            "login_check_jsonpath": "$.code",
            "login_check_value": "success",
        }
        cfg.update(extra)
        return cfg

    def _client(self, session):
        client = FakeClient(session=session)
        client.base_url = "https://test.host"
        client.headers = {"Content-Type": "application/json"}
        return client

    def test_captcha_filled_and_login_success(self, monkeypatch):
        # 验证码经同一 Session 取图识别后填入表单字段提交
        monkeypatch.setattr(runtime_service, "_ocr_instance", FakeOcr(["0128"]))
        session = FakeCaptchaSession([FakeResponse(json_data={"code": "success"})])
        client = self._client(session)
        login(client, _env(login_config=self._cfg()))
        assert len(session.captcha_calls) == 1
        assert session.captcha_calls[0]["url"] == "https://test.host/Public/verify.html"
        assert session.login_calls[0]["data"]["data[verify]"] == "0128"

    def test_ocr_unavailable_degrades(self, monkeypatch):
        # ddddocr 不可用：不取图不填码，字段保持原值，登录流程不阻断
        monkeypatch.setattr(runtime_service, "_ocr_instance", False)
        session = FakeCaptchaSession([FakeResponse(json_data={"code": "success"})])
        client = self._client(session)
        login(client, _env(login_config=self._cfg()))
        assert session.captcha_calls == []
        assert "data[verify]" not in session.login_calls[0]["data"]

    def test_wrong_code_retries_with_new_image(self, monkeypatch):
        # 首次识别错（特征不匹配）→ 换新图重试成功；每次重试都重新取图新码
        monkeypatch.setattr(runtime_service, "_ocr_instance", FakeOcr(["aa11", "9069"]))
        session = FakeCaptchaSession([
            FakeResponse(json_data={"code": "error", "info": "验证码输入错误"}),
            FakeResponse(json_data={"code": "success"}),
        ])
        client = self._client(session)
        login(client, _env(login_config=self._cfg(captcha_retry=3)))
        assert len(session.captcha_calls) == 2
        assert len(session.login_calls) == 2
        assert session.login_calls[0]["data"]["data[verify]"] == "aa11"
        assert session.login_calls[1]["data"]["data[verify]"] == "9069"

    def test_retry_exhausted_raises(self, monkeypatch):
        # 重试耗尽：抛最后一次失败，尝试次数 = captcha_retry
        monkeypatch.setattr(runtime_service, "_ocr_instance", FakeOcr(["1111"]))
        session = FakeCaptchaSession([FakeResponse(json_data={"code": "error"})])
        client = self._client(session)
        with pytest.raises(RuntimeError, match="登录失败"):
            login(client, _env(login_config=self._cfg(captcha_retry=2)))
        assert len(session.login_calls) == 2
        assert len(session.captcha_calls) == 2

    def test_not_enabled_when_only_url(self, monkeypatch):
        # 只配 captcha_url 不配 captcha_field：不启用，不取图
        monkeypatch.setattr(runtime_service, "_ocr_instance", FakeOcr(["0128"]))
        session = FakeCaptchaSession([FakeResponse(json_data={"code": "success"})])
        client = self._client(session)
        login(client, _env(login_config=self._cfg(captcha_field="")))
        assert session.captcha_calls == []
        assert "data[verify]" not in session.login_calls[0]["data"]

    def test_image_http_error_keeps_original(self, monkeypatch):
        # 取图失败（HTTP 404）：降级不填码，登录照常提交原表单
        monkeypatch.setattr(runtime_service, "_ocr_instance", FakeOcr(["0128"]))
        session = FakeCaptchaSession(
            [FakeResponse(json_data={"code": "success"})],
            captcha_resp=FakeImageResponse(status_code=404),
        )
        client = self._client(session)
        login(client, _env(login_config=self._cfg()))
        assert len(session.captcha_calls) == 1
        assert "data[verify]" not in session.login_calls[0]["data"]

    def test_token_json_mode_fills_captcha(self, monkeypatch):
        # token + json 模式：验证码经 Session 取图后填入 JSON 提交体，token 正常提取
        monkeypatch.setattr(runtime_service, "_ocr_instance", FakeOcr(["5d5b"]))
        session = FakeCaptchaSession([FakeResponse(json_data={"data": {"token": "TKN"}})])
        client = FakeClient(post_resp={"data": {"token": "TKN"}}, session=session)
        client.base_url = "https://test.host"
        login(client, _env(login_config=self._cfg(login_mode="token", login_content_type="json")))
        assert len(session.captcha_calls) == 1
        assert client.post_calls[0][1]["data[verify]"] == "5d5b"
        assert client.headers["Authorization"] == "TKN"


class TestPreprocessCaptcha:
    """验证码图预处理：正常图二值化放大输出 PNG；坏数据原样返回降级。"""

    def test_valid_image_processed(self):
        from io import BytesIO

        from PIL import Image
        img = Image.new("L", (40, 20), color=200)  # 低对比度灰底
        buf = BytesIO()
        img.save(buf, format="PNG")
        out = runtime_service._preprocess_captcha(buf.getvalue())
        processed = Image.open(BytesIO(out))
        assert processed.size == (80, 40)  # 2x 放大
        colors = processed.convert("L").getcolors()
        assert all(px in (0, 255) for _, px in colors)  # 已二值化

    def test_invalid_content_returns_original(self):
        garbage = b"not-an-image"
        assert runtime_service._preprocess_captcha(garbage) is garbage


class TestBuildDbClient:
    """build_db_client：按 env.db_config 构建 DBClient，失败时降级返回 None。"""

    def test_no_host_returns_none(self):
        env = _env(db_config={})
        assert build_db_client(env) is None

    def test_none_db_config_returns_none(self):
        env = _env(db_config=None)
        assert build_db_client(env) is None

    def test_valid_config_returns_dbclient(self):
        env = _env(db_config={
            "host": "127.0.0.1",
            "port": 3306,
            "user": "root",
            "password": "pwd",
            "database": "test_db",
        })
        client = build_db_client(env)
        # DBClient 构造不建连，仅存参数
        assert client is not None
        assert client.host == "127.0.0.1"
        assert client.port == 3306
        assert client.user == "root"
        assert client.database == "test_db"

    def test_default_port_when_missing(self):
        env = _env(db_config={"host": "localhost"})
        client = build_db_client(env)
        assert client is not None
        assert client.port == 3306

    def test_invalid_port_returns_none(self):
        # port 非数字 → int() 抛 ValueError → 被 build_db_client 捕获返回 None
        env = _env(db_config={"host": "localhost", "port": "abc"})
        assert build_db_client(env) is None

    def test_missing_optional_fields_uses_defaults(self):
        env = _env(db_config={"host": "localhost"})
        client = build_db_client(env)
        assert client is not None
        assert client.user == ""
        assert client.password == ""
        assert client.database == ""

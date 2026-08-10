"""runtime_service 模块单测：HTTP 客户端构建与登录编排。

build_http_client 测真实 HttpClient 的头装配；login 用 FakeClient 测编排逻辑
（占位头 → 提取 token → 渲染鉴权头 → 注册刷新回调 → 异常包装），不触真实网络。
行为与原 DagExecutor._build_http_client / _login 完全一致。
"""
from types import SimpleNamespace

import pytest

from app.services.runtime_service import (
    build_http_client,
    login,
    build_db_client,
    _extract_by_jsonpath,
)


class FakeClient:
    """模拟 HttpClient：记录调用，可控地返回响应或抛异常。"""

    def __init__(self, post_resp=None, exc=None):
        self.headers = {}
        self._post_resp = post_resp
        self._exc = exc
        self.post_calls = []
        self.set_header_calls = []
        self.refresh_callback = None

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


def _env(login_config=None, common_headers=None, base_url="http://test", db_config=None):
    return SimpleNamespace(
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

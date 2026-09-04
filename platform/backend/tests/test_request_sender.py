"""共享请求发送器单测（debug_api 与 DagExecutor 复用同一实现）。

已知事实独立复述自两处现有平行实现（dag_executor._send_request / apis.debug_api）：
- GET → client.get(path, params=body)
- POST 无文件 → client.post(path, json=body)
- POST 含文件 → multipart：Content-Type 头剥离/恢复、form_data 取 dict
- 异常四分类：HttpStatusError(status) / BusinessError(200+code) / Auth|Timeout|JsonParse(0) / 其他(0)
- multipart 文件句柄用后关闭
"""
from types import SimpleNamespace

import json

import pytest
from utils.exceptions import AuthError, BusinessError, HttpStatusError, HttpTimeoutError

from app.services.request_sender import send_request


class StubClient:
    def __init__(self, resp=None, exc=None):
        self.headers = {"Content-Type": "application/json", "X-Token": "t"}
        self._resp = resp if resp is not None else {"code": 200}
        self._exc = exc
        self.calls = []

    def get(self, path, params=None, timeout=None):
        self.calls.append(("get", path, params, timeout))
        if self._exc:
            raise self._exc
        return self._resp

    def post(self, path, json=None, timeout=None):
        self.calls.append(("post", path, json, timeout))
        if self._exc:
            raise self._exc
        return self._resp

    def post_form(self, path, data=None, timeout=None):
        self.calls.append(("post_form", path, data, timeout))
        if self._exc:
            raise self._exc
        return self._resp

    def post_multipart(self, path, data=None, files=None, timeout=None):
        self.calls.append(("multipart", path, data, [f[0] for f in files], timeout))
        if self._exc:
            raise self._exc
        return self._resp


def _api(method="POST"):
    return SimpleNamespace(method=method, path="/order")


class TestSendRequestDispatch:
    def test_get_uses_params(self):
        c = StubClient(resp={"ok": 1})
        code, data, err = send_request(None, c, _api("GET"), {"a": 1}, timeout=7)
        assert (code, err) == (200, None)
        assert data == {"ok": 1}
        assert c.calls[0][0] == "get"
        assert c.calls[0][2] == {"a": 1}

    def test_get_array_body_takes_first_dict_as_params(self):
        """数组请求体 GET：params 取首元素，避免 list 传 requests.params 触发解包异常"""
        c = StubClient(resp={"ok": 1})
        code, _, err = send_request(None, c, _api("GET"), [{"a": 1, "b": 2}], timeout=7)
        assert (code, err) == (200, None)
        assert c.calls[0][2] == {"a": 1, "b": 2}

    def test_post_uses_json(self):
        c = StubClient()
        code, data, err = send_request(None, c, _api("POST"), {"a": 1}, timeout=7)
        assert code == 200 and err is None
        assert c.calls[0][0] == "post"

    def test_multipart_strips_and_restores_content_type(self, tmp_path, monkeypatch):
        """含文件字段 → multipart 通道：Content-Type 剥离/恢复、form_data 直传 dict"""
        physical = tmp_path / "upload.bin"
        physical.write_bytes(b"file-content")
        import app.services.request_sender as rs
        monkeypatch.setattr(rs, "resolve_physical_path", lambda p: physical)

        class _Db:
            def query(self, *_a):
                class _Q:
                    def filter(self, *a):
                        return self

                    def first(self):
                        return SimpleNamespace(storage_path="files/ab/abc", name="f.bin", content_type="application/octet-stream")

                return _Q()

        c = StubClient()
        code, data, err = send_request(_Db(), c, _api("POST"), {"k": "v"}, file_fields=[("file1", "3")], timeout=7)
        assert code == 200 and err is None
        kind, _, form, field_names, _ = c.calls[0]
        assert kind == "multipart"
        assert field_names == ["file1"]
        assert form == {"k": "v"}
        # 请求后 Content-Type 恢复
        assert c.headers["Content-Type"] == "application/json"

    def test_multipart_list_body_takes_first_dict(self):
        """数组请求体时 form_data 取首元素（dag_executor 现行为）"""
        c = StubClient()

        class _Db:
            def query(self, *_a):
                class _Q:
                    def filter(self, *a):
                        return self

                    def first(self):
                        return None

                return _Q()

        # file 字段在 DB 中不存在 → files_payload 为空 → 退回 json 通道，数组体原样发出
        code, _, err = send_request(_Db(), c, _api("POST"), [{"a": 1}], file_fields=[("file1", "9")])
        assert code == 200
        assert c.calls[0][0] == "post"


class TestFormUrlencoded:
    """表单接口（headers 声明 x-www-form-urlencoded）按表单编码发送。

    回归场景：curl 导入声明 form 的接口（如 precheckSyncFiles.html）此前统一走
    json= 且 headers 已有 Content-Type 时 requests 不改写，形成「form 声明 +
    JSON 文本」的错配请求，服务端按表单解析取不到任何字段。
    """

    def test_form_headers_uses_post_form(self):
        c = StubClient()
        c.headers["Content-Type"] = "application/x-www-form-urlencoded"
        code, _, err = send_request(None, c, _api("POST"), {"order_no": "YHL1"}, timeout=7)
        assert (code, err) == (200, None)
        assert c.calls[0][0] == "post_form"
        assert c.calls[0][2] == {"order_no": "YHL1"}

    def test_form_array_body_takes_first_dict(self):
        c = StubClient()
        c.headers["Content-Type"] = "application/x-www-form-urlencoded"
        send_request(None, c, _api("POST"), [{"a": 1}, {"b": 2}])
        assert c.calls[0][2] == {"a": 1}

    def test_per_request_headers_used_and_restored(self):
        """headers 参数（prepare_request 组装产物）：发送期间生效，结束恢复 client.headers"""
        c = StubClient()
        req_headers = {"Content-Type": "application/x-www-form-urlencoded",
                       "Authorization": "Bearer t"}
        send_request(None, c, _api("POST"), {"order_no": "YHL1"}, headers=req_headers)
        assert c.calls[0][0] == "post_form"
        # 恢复：接口级 form 头不泄漏到 client 会话头（不影响后续 JSON 接口节点）
        assert c.headers["Content-Type"] == "application/json"

    def test_json_headers_still_uses_json(self):
        c = StubClient()
        send_request(None, c, _api("POST"), {"a": 1}, headers={"Content-Type": "application/json"})
        assert c.calls[0][0] == "post"


class TestSendRequestErrorTaxonomy:
    def test_http_status_error_keeps_status(self):
        c = StubClient(exc=HttpStatusError(502, "/order", "bad gateway"))
        code, data, err = send_request(None, c, _api(), {})
        assert code == 502
        assert "error" in data and err

    def test_business_error_returns_200_with_real_body(self):
        # 业务码异常：HTTP 200，响应体返回真实原文（调试展示/断言取值），error 保留说明
        real = {"code": 40001, "msg": "余额不足", "data": {"id": 7}}
        c = StubClient(exc=BusinessError(40001, "余额不足", "/order", json.dumps(real)))
        code, data, err = send_request(None, c, _api(), {})
        assert code == 200
        assert data == real
        assert "40001" in err

    def test_business_error_prefers_parsed_resp_json(self):
        # resp_text 被截断时优先用已解析的完整 resp_json（如超 2000 字符的大响应）
        real = {"code": None, "auth": {"c1": {"search_btn": True}}}
        c = StubClient(exc=BusinessError(None, "", "/order", "截断的半截 JSON", resp_json=real))
        code, data, err = send_request(None, c, _api(), {})
        assert code == 200
        assert data == real

    def test_business_error_non_json_body_falls_back_to_text(self):
        c = StubClient(exc=BusinessError(40001, "x", "/order", "not json"))
        code, data, err = send_request(None, c, _api(), {})
        assert code == 200
        assert data == {"text": "not json"}

    @pytest.mark.parametrize("exc", [
        AuthError("/order", "未登录"),
        HttpTimeoutError("/order", 15),
    ])
    def test_auth_timeout_returns_zero(self, exc):
        c = StubClient(exc=exc)
        code, data, err = send_request(None, c, _api(), {})
        assert code == 0 and err

    def test_json_parse_error_keeps_200_and_text(self):
        """非 JSON 响应（HTML/纯文本）：HTTP 已成功，状态码保留 200，原文进 text，err 为空"""
        exc = __import__("utils.exceptions", fromlist=["JsonParseError"]).JsonParseError("/order", "<html>x</html>")
        c = StubClient(exc=exc)
        code, data, err = send_request(None, c, _api(), {})
        assert code == 200 and err is None and data == {"text": "<html>x</html>"}

    def test_unexpected_error_returns_zero(self):
        c = StubClient(exc=RuntimeError("conn refused"))
        code, data, err = send_request(None, c, _api(), {})
        assert code == 0 and "conn refused" in str(data["error"])


class TestNoParallelImplementations:
    """架构守卫：请求发送只允许一份实现（services.request_sender）"""

    def test_debug_api_reuses_shared_sender(self):
        import inspect

        from app.routers import apis

        src = inspect.getsource(apis)
        assert "post_multipart" not in src, "debug_api 内联了 multipart 组装，应复用 services.request_sender"
        assert "from ..services.request_sender import send_request" in src

    def test_dag_executor_delegates_to_shared_sender(self):
        import inspect

        from app.engine import dag_executor

        src = inspect.getsource(dag_executor)
        assert "from ..services.request_sender import send_request" in src
        assert "_build_multipart_files" not in src, "DagExecutor 仍持有私有 multipart 组装，应删除并委托"

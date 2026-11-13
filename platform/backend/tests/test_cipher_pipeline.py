# -*- coding: utf-8 -*-
"""加密传输管线测试：request_sender 信封化 / 真 HttpClient decoder 接缝 / DAG 密文快照。

三条链路（用例执行 / 接口调试 / 步骤重放）都汇到 request_sender.send_request，
本文件覆盖其加密分支 + HttpClient.response_decoder 契约（decoder 在鉴权失效
判定之前介入、重登递归重发天然重挂）+ DagExecutor cipher_snapshot 落事件。

测试密钥全部现场生成（仓根 public_key.pem/private_key.pem 未入库，CI 无它们）。
"""
import base64
import json
from datetime import datetime
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.engine.dag_executor import DagExecutor
from app.engine.events import DbSink, StepResult
from app.services.cipher_service import decrypt_from_base64, encrypt_json_body
from app.services.request_sender import send_request
from utils.exceptions import CipherError
from utils.http_client import HttpClient


def make_pair_pems():
    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pub_pem = priv.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    priv_pem = priv.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption()).decode()
    return pub_pem, priv_pem


def _keys(pub, priv, name="customs"):
    return {name: {"public_key": pub, "private_key": priv}}


def _api(**over):
    base = dict(method="POST", path="/api/v1/customs/clearance/batchSubmit", name="报关单批量提交")
    base.update(over)
    return SimpleNamespace(**base)


REQ_ON = {"request": {"enabled": True, "key": "customs"}}


class CipherStubClient:
    """StubClient + 两项加密契约：
    - cipher_keys：环境密钥材料表（生产由 runtime_service.build_http_client 挂载）
    - post/get 内应用 response_decoder——模拟真 HttpClient._request 在鉴权失效
      判定/业务码校验之前介入 decoder 的接缝（普通 StubClient 不模拟此契约）
    """

    def __init__(self, resp=None, cipher_keys=None):
        self.headers = {"Content-Type": "application/json", "X-Token": "t"}
        self._resp = resp if resp is not None else {"code": 200}
        self.cipher_keys = cipher_keys or {}
        self.calls = []

    def get(self, path, params=None, timeout=None):
        self.calls.append(("get", path, params, timeout))
        return self._apply(self._resp)

    def post(self, path, json=None, timeout=None):
        self.calls.append(("post", path, json, timeout))
        return self._apply(self._resp)

    def post_form(self, path, data=None, timeout=None):
        self.calls.append(("post_form", path, data, timeout))
        return self._apply(self._resp)

    def _apply(self, resp):
        dec = getattr(self, "response_decoder", None)
        if dec is not None and resp is not None:
            resp = dec(resp)
        return resp


# ============ request_sender：请求加密 ============

class TestSenderRequestEncryption:
    def test_envelope_sent_and_body_untouched(self):
        """实际发出的是 {requestCipher: 密文} 信封；传入 body 原样不被改（明文落库语义）"""
        pub, priv = make_pair_pems()
        c = CipherStubClient(cipher_keys=_keys(pub, priv))
        body = {"requestTime": 1794550465073, "callbackUrl": "http://h/mock",
                "items": [{"bizNo": "BIZ-1", "declarationNo": "123456789012345678"}]}
        snapshot = dict(body)
        box = {}
        code, data, err = send_request(None, c, _api(crypto_config=REQ_ON), body, cipher_out=box)
        assert (code, err) == (200, None)
        kind, _, wire, _ = c.calls[0]
        assert kind == "post"
        assert set(wire) == {"requestCipher"}  # 信封：外层只有这一个字段
        assert json.loads(decrypt_from_base64(wire["requestCipher"], priv)) == body
        assert body == snapshot  # 绝不原地改
        assert box["request"] == wire["requestCipher"]
        raw = base64.b64decode(box["request"])
        assert len(raw) % 256 == 0  # 分段密文拼接

    def test_custom_wrapper_field_and_segment_size(self):
        pub, _ = make_pair_pems()
        c = CipherStubClient(cipher_keys=_keys(pub, None))
        cfg = {"request": {"enabled": True, "key": "customs",
                           "wrapper_field": "dataCipher", "segment_size": 100}}
        body = {"name": "x" * 200}  # JSON 序列化后 ~213 字节 → 100 分段 3 段
        send_request(None, c, _api(crypto_config=cfg), body)
        _, _, wire, _ = c.calls[0]
        assert set(wire) == {"dataCipher"}
        assert len(base64.b64decode(wire["dataCipher"])) == 3 * 256

    def test_get_rejected(self):
        pub, priv = make_pair_pems()
        c = CipherStubClient(cipher_keys=_keys(pub, priv))
        code, data, err = send_request(None, c, _api(method="GET", crypto_config=REQ_ON), {"a": 1})
        assert code == 0 and "GET" in err and "无法承载密文" in err
        assert c.calls == []

    def test_form_urlencoded_rejected(self):
        pub, priv = make_pair_pems()
        c = CipherStubClient(cipher_keys=_keys(pub, priv))
        c.headers["Content-Type"] = "application/x-www-form-urlencoded"
        code, _, err = send_request(None, c, _api(crypto_config=REQ_ON), {"a": 1})
        assert code == 0 and "仅支持 JSON 请求体" in err
        assert c.calls == []

    def test_file_field_rejected(self):
        pub, priv = make_pair_pems()
        c = CipherStubClient(cipher_keys=_keys(pub, priv))
        code, _, err = send_request(None, c, _api(crypto_config=REQ_ON), {"a": 1},
                                    file_fields=[("file", "1")])
        assert code == 0 and "仅支持 JSON 请求体" in err
        assert c.calls == []

    def test_missing_key_name_rejected(self):
        pub, priv = make_pair_pems()
        c = CipherStubClient(cipher_keys=_keys(pub, priv))
        code, _, err = send_request(None, c, _api(crypto_config={"request": {"enabled": True}}), {})
        assert code == 0 and "未指定密钥对名称" in err
        assert c.calls == []

    def test_key_not_in_env_rejected(self):
        pub, priv = make_pair_pems()
        c = CipherStubClient(cipher_keys=_keys(pub, priv))
        code, _, err = send_request(None, c, _api(crypto_config={
            "request": {"enabled": True, "key": "cfca"}}), {})
        assert code == 0 and "环境未配置名为「cfca」" in err
        assert c.calls == []

    def test_missing_public_key_rejected(self):
        _, priv = make_pair_pems()
        c = CipherStubClient(cipher_keys=_keys(None, priv))
        code, _, err = send_request(None, c, _api(crypto_config=REQ_ON), {})
        assert code == 0 and "缺少公钥" in err
        assert c.calls == []

    def test_disabled_config_is_plain_json(self):
        """crypto_config 关闭/缺省 → 与既有行为完全一致（零回归守卫）"""
        c = CipherStubClient()
        send_request(None, c, _api(crypto_config={"request": {"enabled": False}}), {"a": 1})
        assert c.calls[0][2] == {"a": 1}
        send_request(None, c, _api(), {"b": 2})
        assert c.calls[1][2] == {"b": 2}


# ============ request_sender：响应解密 ============

class TestSenderResponseDecryption:
    def test_full_roundtrip_request_and_response(self):
        """请求加密 + 响应解密全链路：发出信封、收到信封解成明文业务体；
        响应密钥缺省复用请求密钥对"""
        pub, priv = make_pair_pems()
        inner = {"code": 200, "data": {"batchNo": "CUS-B-1000"}}
        resp_cipher = encrypt_json_body(inner, pub)
        c = CipherStubClient(resp={"responseCipher": resp_cipher},
                             cipher_keys=_keys(pub, priv))
        cfg = {"request": {"enabled": True, "key": "customs"},
               "response": {"enabled": True}}  # 未单独配 key → 复用 customs
        body = {"requestNo": "1001"}
        box = {}
        code, data, err = send_request(None, c, _api(crypto_config=cfg), body, cipher_out=box)
        assert (code, err) == (200, None)
        assert data == inner  # 解密结果整体替换响应：断言直接打业务字段
        assert box["response"] == resp_cipher
        assert box["request"] == c.calls[0][2]["requestCipher"]
        assert c.response_decoder is None  # finally 恢复，不泄漏到后续请求

    def test_guard_plaintext_response_passthrough(self):
        """字段守卫：响应无密文字段（明文错误响应/重登响应）→ 原样透传"""
        pub, priv = make_pair_pems()
        plain = {"code": 405, "msg": "凭证过期"}
        c = CipherStubClient(resp=plain, cipher_keys=_keys(pub, priv))
        cfg = {"response": {"enabled": True, "key": "customs"}}
        code, data, err = send_request(None, c, _api(crypto_config=cfg), {})
        assert (code, err) == (200, None)
        assert data == plain

    def test_guard_non_dict_response_passthrough(self):
        pub, priv = make_pair_pems()
        c = CipherStubClient(resp=[1, 2], cipher_keys=_keys(pub, priv))
        cfg = {"response": {"enabled": True, "key": "customs"}}
        code, data, _ = send_request(None, c, _api(crypto_config=cfg), {})
        assert data == [1, 2]

    def test_body_mode_string_response(self):
        """mode=body：响应整体是 Base64 密文字符串（JSON 字符串形态）"""
        pub, priv = make_pair_pems()
        inner = {"code": 200, "list": [1, 2]}
        c = CipherStubClient(resp=encrypt_json_body(inner, pub),
                             cipher_keys=_keys(pub, priv))
        cfg = {"response": {"enabled": True, "key": "customs", "mode": "body"}}
        code, data, err = send_request(None, c, _api(crypto_config=cfg), {})
        assert (code, err) == (200, None)
        assert data == inner

    def test_missing_key_name_rejected(self):
        pub, priv = make_pair_pems()
        c = CipherStubClient(cipher_keys=_keys(pub, priv))
        code, _, err = send_request(None, c, _api(crypto_config={"response": {"enabled": True}}), {})
        assert code == 0 and "响应解密" in err and "未指定密钥对名称" in err
        assert c.calls == []

    def test_missing_private_key_rejected(self):
        pub, _ = make_pair_pems()
        c = CipherStubClient(cipher_keys=_keys(pub, None))
        code, _, err = send_request(None, c, _api(crypto_config={"response": {"enabled": True, "key": "customs"}}), {})
        assert code == 0 and "缺少私钥" in err
        assert c.calls == []

    def test_bad_cipher_stage_response_visible(self):
        """密文损坏：HTTP 已 200 收到报文 → status 200 + err 非空（步骤判负可见）"""
        pub, priv = make_pair_pems()
        bad = base64.b64encode(b"short-not-256").decode()
        c = CipherStubClient(resp={"responseCipher": bad}, cipher_keys=_keys(pub, priv))
        cfg = {"response": {"enabled": True, "key": "customs"}}
        code, data, err = send_request(None, c, _api(crypto_config=cfg), {})
        assert code == 200 and err and "256" in err


# ============ 真 HttpClient：decoder 接缝 ============

class FakeRawResponse:
    def __init__(self, json_value):
        self.status_code = 200
        self.text = str(json_value)
        self._json_value = json_value

    def json(self):
        return self._json_value


class _SeqSession:
    def __init__(self, resps):
        self.resps = list(resps)

    def request(self, method, url, headers=None, params=None, json=None,
                data=None, files=None, timeout=None):
        return self.resps.pop(0)


class TestHttpClientDecoder:
    """decoder 契约：插入点在鉴权失效判定之前——密文信封里的 code 405 也能触发
    自动重登，且重登递归重发读取同一实例属性，decoder 天然重挂。"""

    def test_decoder_before_auth_expire_and_relogin_remounts(self):
        pub, priv = make_pair_pems()
        c = HttpClient(base_url="http://t")
        c.session = _SeqSession([
            FakeRawResponse({"responseCipher": encrypt_json_body(
                {"code": 405, "msg": "账号异地登录"}, pub)}),
            FakeRawResponse({"responseCipher": encrypt_json_body(
                {"code": 200, "data": {"ok": 1}}, pub)}),
        ])
        refreshed = []
        c.set_token_refresh_callback(lambda: refreshed.append(1))

        def decoder(resp):
            raw = resp.get("responseCipher")
            return json.loads(decrypt_from_base64(raw, priv)) if isinstance(raw, str) else resp

        c.response_decoder = decoder
        assert c.get("/x") == {"code": 200, "data": {"ok": 1}}
        assert refreshed == [1]  # 解密后的明文 405 触发重登；重试响应也被同一 decoder 解开

    def test_guard_plaintext_dict_unchanged(self):
        pub, priv = make_pair_pems()
        c = HttpClient(base_url="http://t")
        plain = {"code": 200, "msg": "明文响应"}
        c.session = _SeqSession([FakeRawResponse(plain)])

        def decoder(resp):
            raw = resp.get("responseCipher") if isinstance(resp, dict) else None
            return json.loads(decrypt_from_base64(raw, priv)) if isinstance(raw, str) else resp

        c.response_decoder = decoder
        assert c.get("/x") == plain

    def test_cipher_error_bubbles(self):
        """decoder 抛出的 CipherError 不被 HttpClient 吞掉（冒泡给 send_request 分流）"""
        c = HttpClient(base_url="http://t")
        c.session = _SeqSession([FakeRawResponse({"responseCipher": "!!!"})])

        def decoder(resp):
            return json.loads(decrypt_from_base64(resp["responseCipher"], "irrelevant"))

        c.response_decoder = decoder
        with pytest.raises(CipherError):
            c.get("/x")


# ============ DAG 集成：cipher_snapshot 落事件 ============

class FakeDb:
    def __init__(self, first_results=None):
        self._firsts = list(first_results or [])
        self.added = []

    def query(self, *_a, **_kw):
        db = self

        class _Q:
            def filter(self, *a, **kw):
                return self

            def first(self):
                return db._firsts.pop(0) if db._firsts else None

        return _Q()

    def add(self, obj):
        self.added.append(obj)

    def flush(self):
        pass

    def commit(self):
        pass

    def refresh(self, _obj):
        pass


class MemorySink:
    def __init__(self):
        self.steps = []

    def record_step(self, result):
        self.steps.append(result)


class RecordingCipherClient(CipherStubClient):
    """DAG 替身：记录最后一次实际发出的 json body"""

    def __init__(self, resp=None, cipher_keys=None):
        super().__init__(resp=resp, cipher_keys=cipher_keys)
        self.last_json_body = None

    def post(self, path, json=None, timeout=None):
        self.last_json_body = json
        return super().post(path, json=json, timeout=timeout)


class TestDagCipherIntegration:
    def test_node_encrypts_and_cipher_snapshot_lands(self):
        """DAG 主链路：实际发出信封体；StepResult.request_body 明文 +
        cipher_snapshot 留实际密文（报告/重放语义的根基）"""
        pub, priv = make_pair_pems()
        config = SimpleNamespace(api_id=10, post_extract=None, assertions=None, wait_after_ms=0)
        api = _api(id=10, crypto_config=REQ_ON, request_template={}, api_fields=None, fields=[])
        db = FakeDb(first_results=[config, api])
        sink = MemorySink()
        ex = DagExecutor(db, SimpleNamespace(id=1, dag_config={"nodes": [], "edges": []}),
                         SimpleNamespace(variables={}, timeout=5), sink=sink)
        stub = RecordingCipherClient(resp={"code": 200, "data": {"batchNo": "CUS-B-1000"}},
                                     cipher_keys=_keys(pub, priv))
        ex.http_client = stub

        passed, _ = ex._execute_node(100, "n1", {"id": "n1"})

        assert passed is True
        ev = sink.steps[0]
        assert ev.status == "success"
        # 明文语义：事件里 request_body 与实际发出的密文解密结果一致
        wire = stub.last_json_body
        assert set(wire) == {"requestCipher"}
        assert json.loads(decrypt_from_base64(wire["requestCipher"], priv)) == ev.request_body
        # 密文快照与实际发出的信封一致
        assert ev.cipher_snapshot == {"request": wire["requestCipher"]}
        assert ev.response_body == {"code": 200, "data": {"batchNo": "CUS-B-1000"}}

    def test_plain_node_keeps_cipher_snapshot_none(self):
        """未开加密的节点：cipher_snapshot 保持 None（不写空 dict 噪音）"""
        config = SimpleNamespace(api_id=10, post_extract=None, assertions=None, wait_after_ms=0)
        api = _api(id=10, crypto_config=None, request_template={}, api_fields=None, fields=[])
        db = FakeDb(first_results=[config, api])
        sink = MemorySink()
        ex = DagExecutor(db, SimpleNamespace(id=1, dag_config={"nodes": [], "edges": []}),
                         SimpleNamespace(variables={}, timeout=5), sink=sink)
        ex.http_client = RecordingCipherClient()
        ex._execute_node(100, "n1", {"id": "n1"})
        assert sink.steps[0].cipher_snapshot is None


class TestDbSinkCipherSnapshot:
    def test_record_step_writes_cipher_snapshot(self):
        from app import models

        db = FakeDb()
        DbSink(db).record_step(StepResult(
            execution_id=1, node_id="n1", api_name="下单", api_path="/o",
            api_method="POST", request_headers={}, request_body={"a": 1},
            response_status=200, response_body={"code": 200}, response_time_ms=5,
            started_at=datetime.now(), ended_at=datetime.now(), status="success",
            cipher_snapshot={"request": "QkFTRTY0", "response": "QkFTRTY0"},
        ))
        assert isinstance(db.added[0], models.StepRecord)
        assert db.added[0].cipher_snapshot == {"request": "QkFTRTY0", "response": "QkFTRTY0"}

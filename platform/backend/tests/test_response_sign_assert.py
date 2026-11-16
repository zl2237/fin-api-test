# -*- coding: utf-8 -*-
"""response_sign_verify 断言（第 18 种）单测。

密钥对现场生成（同 test_callback_sign 夹具口径），私钥自造签名 → 公钥验签：
验证的是断言分支的接线（路径解析/密钥名解析/失败原因），签名算法本身由
test_callback_sign.py 的金标向量覆盖。
"""
from types import SimpleNamespace

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.engine.assertion_engine import AssertionEngine
from app.services.cipher_service import (
    build_assertion_cipher_ctx,
    canonicalize_callback,
    sign_callback_canonical,
)


def make_pair_pems():
    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pub_pem = priv.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    priv_pem = priv.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption()).decode()
    return pub_pem, priv_pem


def make_signed_payload(priv_pem: str, **fields) -> dict:
    """按协议自造签名报文：字段 + sign/signType（签名覆盖其余全部顶层键）"""
    payload = {"signType": "RSA2", **fields}
    canonical, _ = canonicalize_callback(payload)
    payload["sign"] = sign_callback_canonical(canonical, priv_pem)
    return payload


def make_cipher_ctx(pub_pem: str, name="customs", default_key=None) -> dict:
    return {"key_pairs": {name: {"public_key": pub_pem, "private_key": None}},
            "default_key": default_key}


RESPONSE = {
    "code": 200,
    "data": {
        "batchNo": "CUS-B-1000",
        "items": [{"bizNo": "BIZ-1", "taskStatus": 2}],
        "signType": "RSA2",
    },
}


class TestResponseSignVerify:
    def test_pass_root(self):
        """签名对象在响应根（默认 path=$）"""
        pub, priv = make_pair_pems()
        body = make_signed_payload(priv, batchNo="CUS-B-1000", items=[{"bizNo": "BIZ-1"}])
        engine = AssertionEngine({"extracted": {}}, cipher_ctx=make_cipher_ctx(pub))
        r = engine.evaluate_all(body, 200, 50, [{"type": "response_sign_verify"}])[0]
        assert r["pass"] is True

    def test_pass_nested_path(self):
        """签名对象嵌套在 $.data（海关 410 形态）"""
        pub, priv = make_pair_pems()
        signed = make_signed_payload(priv, batchNo="CUS-B-1000", taskStatus=2)
        body = {"code": 200, "data": signed}
        engine = AssertionEngine({"extracted": {}}, cipher_ctx=make_cipher_ctx(pub))
        r = engine.evaluate_all(body, 200, 50,
                                [{"type": "response_sign_verify", "path": "$.data"}])[0]
        assert r["pass"] is True

    def test_fail_tampered_with_canonical_in_message(self):
        """篡改字段 → 失败，且失败原因带重建待签原串（排障不回工具页）"""
        pub, priv = make_pair_pems()
        body = make_signed_payload(priv, batchNo="CUS-B-1000", requestNo="1001")
        body["requestNo"] = "9999"  # 签名后篡改
        engine = AssertionEngine({"extracted": {}}, cipher_ctx=make_cipher_ctx(pub))
        r = engine.evaluate_all(body, 200, 50, [{"type": "response_sign_verify"}])[0]
        assert r["pass"] is False
        assert "待签原串" in r["message"]
        assert "batchNo=CUS-B-1000" in r["message"]

    def test_key_resolution_order(self):
        """密钥名解析：断言 key > default_key（接口加密配置） > 环境第一对"""
        pub_a, priv_a = make_pair_pems()
        pub_b, priv_b = make_pair_pems()
        # 报文用 B 签；环境第一对是 A、default_key 指向 B：无断言 key 时应命中 B
        body = make_signed_payload(priv_b, batchNo="X")
        ctx = {"key_pairs": {"alpha": {"public_key": pub_a, "private_key": None},
                             "beta": {"public_key": pub_b, "private_key": None}},
               "default_key": "beta"}
        engine = AssertionEngine({"extracted": {}}, cipher_ctx=ctx)
        assert engine.evaluate_all(body, 200, 50, [{"type": "response_sign_verify"}])[0]["pass"] is True
        # 断言显式 key=alpha（A 公钥验 B 的签名）→ 失败，证明 default_key 被覆盖
        r = engine.evaluate_all(body, 200, 50,
                                [{"type": "response_sign_verify", "key": "alpha"}])[0]
        assert r["pass"] is False
        assert "alpha" in r["message"]

    def test_default_key_falls_to_first_pair(self):
        """无断言 key 且接口无加密配置 → 环境第一对（与工具页留空语义一致）"""
        pub, priv = make_pair_pems()
        body = make_signed_payload(priv, batchNo="X")
        ctx = make_cipher_ctx(pub, name="only")  # default_key=None
        engine = AssertionEngine({"extracted": {}}, cipher_ctx=ctx)
        assert engine.evaluate_all(body, 200, 50, [{"type": "response_sign_verify"}])[0]["pass"] is True

    def test_missing_sign_field(self):
        pub, _ = make_pair_pems()
        engine = AssertionEngine({"extracted": {}}, cipher_ctx=make_cipher_ctx(pub))
        r = engine.evaluate_all({"batchNo": "X"}, 200, 50,
                                [{"type": "response_sign_verify"}])[0]
        assert r["pass"] is False
        assert "sign" in r["message"]

    def test_path_not_object(self):
        pub, _ = make_pair_pems()
        engine = AssertionEngine({"extracted": {}}, cipher_ctx=make_cipher_ctx(pub))
        r = engine.evaluate_all({"data": "ok"}, 200, 50,
                                [{"type": "response_sign_verify", "path": "$.data"}])[0]
        assert r["pass"] is False
        assert "不是 JSON 对象" in r["message"]

    def test_no_cipher_ctx_guidance(self):
        """环境无密钥对（ctx=None）：失败 + 指引文案，不抛异常"""
        engine = AssertionEngine({"extracted": {}})
        r = engine.evaluate_all({"sign": "x"}, 200, 50, [{"type": "response_sign_verify"}])[0]
        assert r["pass"] is False
        assert "环境未配置" in r["message"]

    def test_key_name_missing_guidance(self):
        """指定/默认密钥名在环境里不存在 → 带名称的指引"""
        pub, _ = make_pair_pems()
        engine = AssertionEngine({"extracted": {}}, cipher_ctx=make_cipher_ctx(pub))
        r = engine.evaluate_all({"sign": "x"}, 200, 50,
                                [{"type": "response_sign_verify", "key": "ghost"}])[0]
        assert r["pass"] is False
        assert "ghost" in r["message"]

    def test_public_key_missing(self):
        """密钥对存在但没录公钥 → 指引补录"""
        ctx = {"key_pairs": {"k": {"public_key": None, "private_key": None}},
               "default_key": "k"}
        engine = AssertionEngine({"extracted": {}}, cipher_ctx=ctx)
        r = engine.evaluate_all({"sign": "x"}, 200, 50, [{"type": "response_sign_verify"}])[0]
        assert r["pass"] is False
        assert "缺少公钥" in r["message"]


class TestBuildAssertionCipherCtx:
    def test_default_key_from_api_crypto_config(self):
        """默认密钥名：请求加密 key 优先，其次响应解密 key"""
        env = SimpleNamespace(cipher_config={
            "key_pairs": [{"name": "customs", "public_key": "PUB", "private_key": None}]})
        api_req = SimpleNamespace(crypto_config={
            "request": {"enabled": True, "key": "customs"}})
        api_resp = SimpleNamespace(crypto_config={
            "response": {"enabled": True, "key": "cfca"}})
        ctx = build_assertion_cipher_ctx(env, api_req)
        assert ctx["default_key"] == "customs"
        assert set(ctx["key_pairs"]) == {"customs"}
        assert build_assertion_cipher_ctx(env, api_resp)["default_key"] == "cfca"
        assert build_assertion_cipher_ctx(env, None)["default_key"] is None

    def test_env_without_pairs_returns_none(self):
        env = SimpleNamespace(cipher_config={"key_pairs": []})
        assert build_assertion_cipher_ctx(env) is None
        assert build_assertion_cipher_ctx(SimpleNamespace(cipher_config=None)) is None

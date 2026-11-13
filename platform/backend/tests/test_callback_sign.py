# -*- coding: utf-8 -*-
"""回调验签规范化测试：金标向量逐字节对齐 docs/回调验签说明.txt 103-104 行。

对方（Fastjson2 侧）规则：顶层剔除 sign/signType，其余键字典序 k=v&k=v 拼接；
顶层 null→空串、数字十进制、布尔 true/false、字符串原样不 URL 编码；
items 用 Fastjson2 紧凑 JSON（递归字典序键、数组保序、嵌套 null 保持、
中文原字符、仅转义引号/反斜杠/控制字符）。
"""
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.services.cipher_service import (
    canonicalize_callback,
    sign_callback_canonical,
    verify_callback_sign,
)
from utils.exceptions import CipherError

# ===== 金标向量：回调验签说明.txt 103-104 行的两条真实待签原串（一字不改）=====
GOLDEN_1 = ('batchNo=CUS-B-1000&items=[{"bizNo":"BIZ-1","decStatus":'
            '[{"status":"已结关","time":"2026-11-02 10:00:00"}],'
            '"declarationNo":"123456789012345678","queryFailReason":"",'
            '"requestNo":"1001","taskStatus":2,"taxStatus":[]}]')
GOLDEN_2 = ('batchNo=CUS-B-1000&items=[{"bizNo":"BIZ-1","decStatus":null,'
            '"declarationNo":"123456789012345678","queryFailReason":"查询失败",'
            '"requestNo":"1001","taskStatus":3,"taxStatus":null}]')

# 生成上述原串的回调报文（字段故意乱序插入——规范化必须排序）：
PAYLOAD_1 = {
    "signType": "RSA2",
    "batchNo": "CUS-B-1000",
    "items": [{
        "taxStatus": [],
        "taskStatus": 2,
        "requestNo": "1001",
        "queryFailReason": "",
        "declarationNo": "123456789012345678",
        "decStatus": [{"time": "2026-11-02 10:00:00", "status": "已结关"}],  # 内层同样乱序
        "bizNo": "BIZ-1",
    }],
}
PAYLOAD_2 = {
    "signType": "RSA2",
    "batchNo": "CUS-B-1000",
    "items": [{
        "taxStatus": None,
        "taskStatus": 3,
        "requestNo": "1001",
        "queryFailReason": "查询失败",
        "declarationNo": "123456789012345678",
        "decStatus": None,
        "bizNo": "BIZ-1",
    }],
}


def make_pair_pems():
    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pub_pem = priv.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    priv_pem = priv.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption()).decode()
    return pub_pem, priv_pem


class TestGoldenVectors:
    """金标：canonicalize 产物与文档两条原串逐字节一致（含中文不转义、
    嵌套 null 保持 null、键序字典序、数组保序）"""

    def test_vector_1_status_ok(self):
        canonical, items_json = canonicalize_callback(PAYLOAD_1)
        assert canonical == GOLDEN_1
        assert canonical.encode("utf-8") == GOLDEN_1.encode("utf-8")
        assert items_json == canonical.split("items=", 1)[1]

    def test_vector_2_null_forms(self):
        canonical, items_json = canonicalize_callback(PAYLOAD_2)
        assert canonical == GOLDEN_2
        assert items_json == canonical.split("items=", 1)[1]

    def test_sign_and_sign_type_excluded(self):
        """顶层 sign/signType 剔除：带上假 sign 重建的原串也不变"""
        with_sign = dict(PAYLOAD_1, sign="FAKE-SIGN==")
        assert canonicalize_callback(with_sign)[0] == GOLDEN_1


class TestTopLevelValueForms:
    def test_null_bool_int_string(self):
        payload = {"e": "hello", "d": 3, "c": True, "b": False, "a": None}
        canonical, _ = canonicalize_callback(payload)
        assert canonical == "a=&b=false&c=true&d=3&e=hello"

    def test_string_with_specials_not_url_encoded(self):
        payload = {"q": "a=b&c=d 中文"}
        assert canonicalize_callback(payload)[0] == "q=a=b&c=d 中文"

    def test_no_items_key_returns_none_items_json(self):
        canonical, items_json = canonicalize_callback({"x": "1"})
        assert canonical == "x=1"
        assert items_json is None

    def test_non_dict_payload_rejected(self):
        with pytest.raises(CipherError):
            canonicalize_callback([1, 2])

    def test_unsupported_value_type_rejected(self):
        with pytest.raises(CipherError) as ei:
            canonicalize_callback({"s": {1, 2}})
        assert "不支持序列化" in str(ei.value)


class TestSignVerifyRoundtrip:
    """私钥自造签名 → 公钥验签（线上真实签名在对方侧，这里验证的是验签通道本身）"""

    def _signed_payload(self):
        pub, priv = make_pair_pems()
        canonical, _ = canonicalize_callback(PAYLOAD_1)
        sign = sign_callback_canonical(canonical, priv)
        payload = dict(PAYLOAD_1, sign=sign)
        return pub, payload, sign

    def test_valid_sign_passes(self):
        pub, payload, sign = self._signed_payload()
        assert verify_callback_sign(payload, sign, pub) is True

    def test_tampered_payload_fails(self):
        pub, payload, sign = self._signed_payload()
        payload["batchNo"] = "CUS-B-9999"
        assert verify_callback_sign(payload, sign, pub) is False

    def test_tampered_nested_value_fails(self):
        pub, payload, sign = self._signed_payload()
        payload["items"][0]["taskStatus"] = 9
        assert verify_callback_sign(payload, sign, pub) is False

    def test_wrong_key_fails(self):
        _, payload, sign = self._signed_payload()
        other_pub, _ = make_pair_pems()
        assert verify_callback_sign(payload, sign, other_pub) is False

    def test_garbage_sign_fails_not_raises(self):
        pub, payload, _ = self._signed_payload()
        assert verify_callback_sign(payload, "%%not-base64%%", pub) is False

    def test_empty_sign_fails_not_raises(self):
        pub, payload, _ = self._signed_payload()
        assert verify_callback_sign(payload, "", pub) is False

    def test_golden_payload_signed_and_verified(self):
        """端到端：金标原串签名后经 verify_callback_sign 全流程通过（工具页同路径）"""
        pub, priv = make_pair_pems()
        canonical, _ = canonicalize_callback(PAYLOAD_2)
        sign = sign_callback_canonical(canonical, priv)
        assert sign.endswith("==")  # 256 字节签名 → Base64 344 字符含填充
        payload = dict(PAYLOAD_2, sign=sign)
        assert verify_callback_sign(payload, sign, pub) is True

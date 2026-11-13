# -*- coding: utf-8 -*-
"""加密内核单测：分段加解密、密钥双格式解析、报错文案。

协议（docs/调用加密说明.txt）：RSA-2048 PKCS1v1.5 分段加密，明文每段 ≤244
字节、每段密文 256 字节、全部拼接后整体一次 Base64（不得逐段 Base64）。
"""
import base64
import json
import re

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from utils.exceptions import CipherError

from app.services.cipher_service import (
    CIPHER_BLOCK_SIZE,
    MAX_SEGMENT_SIZE,
    decrypt_from_base64,
    encrypt_json_body,
    encrypt_to_base64,
    key_pairs_from_config,
    load_private_key,
    load_public_key,
    resolve_key_pair,
    verify_key_pair,
)


def make_pair_pems():
    """生成 RSA-2048 测试密钥对（PEM：SPKI 公钥 / PKCS#8 私钥）"""
    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pub = priv.public_key()
    pub_pem = pub.public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    priv_pem = priv.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption()).decode()
    return pub_pem, priv_pem


def der_b64(pub_pem: str, priv_pem: str) -> tuple[str, str]:
    """从 PEM 提取裸 Base64（X.509 / PKCS#8 DER 的 b64 形态）"""
    pub_b64 = "".join(pub_pem.splitlines()[1:-1])
    priv_b64 = "".join(priv_pem.splitlines()[1:-1])
    return pub_b64, priv_b64


class TestSegmentedRoundtrip:
    @pytest.mark.parametrize("size", [0, 1, 243, 244, 245, 248, 488, 489, 600])
    def test_roundtrip_various_sizes(self, size):
        pub, priv = make_pair_pems()
        plain = bytes(range(256)) * (size // 256 + 1)
        plain = plain[:size] if size else b""
        cipher = encrypt_to_base64(plain, pub)
        assert decrypt_from_base64(cipher, priv) == plain

    def test_cipher_length_invariant(self):
        """n 字节明文 → ceil(n/244)*256 字节密文；空明文也是单段"""
        pub, _ = make_pair_pems()
        for size, expect_blocks in [(0, 1), (243, 1), (244, 1), (245, 2), (489, 3)]:
            raw = base64.b64decode(encrypt_to_base64(b"x" * size, pub))
            assert len(raw) == expect_blocks * CIPHER_BLOCK_SIZE, f"size={size}"

    def test_whole_base64_not_per_segment(self):
        """「整体一次 Base64」判别：中间不得出现 = 填充（逐段 Base64 会在段尾出 =）"""
        pub, _ = make_pair_pems()
        # 2 段（245 字节）：逐段 Base64 会在 344 字符处出现 =；整体一次只在末尾
        cipher = encrypt_to_base64(b"y" * 245, pub)
        assert "=" not in cipher[:-4]  # 整体一次 Base64：填充只允许出现在末尾
        assert len(cipher) == 684 and cipher.endswith("=")  # 512 字节 → 684 字符、末尾恰 1 个 =

    def test_single_segment_b64_len_344(self):
        """单段 256 字节密文 → Base64 恰 344 字符（与线上 api_fields 样本密文同构）"""
        pub, _ = make_pair_pems()
        assert len(encrypt_to_base64(b"z" * 100, pub)) == 344

    def test_utf8_chinese_multibyte_cross_segment(self):
        pub, priv = make_pair_pems()
        body = {"name": "跨境电商物流" * 40, "items": [{"bizNo": "测试-001"}]}
        cipher = encrypt_json_body(body, pub)
        assert json.loads(decrypt_from_base64(cipher, priv).decode("utf-8")) == body

    def test_segment_size_override(self):
        pub, priv = make_pair_pems()
        plain = b"a" * 250
        cipher = encrypt_to_base64(plain, pub, segment_size=100)
        raw = base64.b64decode(cipher)
        assert len(raw) == 3 * CIPHER_BLOCK_SIZE  # 250/100 → 100+100+50 共 3 段
        assert decrypt_from_base64(cipher, priv) == plain


class TestKeyFormats:
    def test_bare_b64_der_compatible_with_pem(self):
        """同一把钥匙：PEM 加密 ← 裸 b64 私钥可解；裸 b64 公钥加密 ← PEM 私钥可解"""
        pub_pem, priv_pem = make_pair_pems()
        pub_b64, priv_b64 = der_b64(pub_pem, priv_pem)
        cipher = encrypt_to_base64(b"k" * 10, pub_b64)
        assert decrypt_from_base64(cipher, priv_pem) == b"k" * 10
        cipher2 = encrypt_to_base64(b"k" * 10, pub_pem)
        assert decrypt_from_base64(cipher2, priv_b64) == b"k" * 10

    def test_pem_newlines_lost_still_parses(self):
        """PEM 头尾在但换行丢失（单行粘贴）→ 取密钥体按 DER 兜底解析"""
        pub_pem, _ = make_pair_pems()
        one_line = re.sub(r"\s+", "", pub_pem)
        assert "-----BEGIN" in one_line and "\n" not in one_line
        assert load_public_key(one_line) is not None

    def test_empty_material_rejected(self):
        for fn in (load_public_key, load_private_key):
            with pytest.raises(CipherError) as ei:
                fn("")
            assert "为空" in str(ei.value)

    def test_garbage_public_rejected(self):
        with pytest.raises(CipherError) as ei:
            load_public_key("not-a-key@@@")
        assert "公钥" in str(ei.value)

    def test_garbage_private_rejected(self):
        with pytest.raises(CipherError) as ei:
            load_private_key("not-a-key@@@")
        assert "私钥" in str(ei.value)


class TestErrorMessages:
    def test_segment_size_over_limit(self):
        pub, _ = make_pair_pems()
        with pytest.raises(CipherError) as ei:
            encrypt_to_base64(b"x", pub, segment_size=MAX_SEGMENT_SIZE + 1)
        assert str(MAX_SEGMENT_SIZE) in str(ei.value)

    def test_segment_size_zero(self):
        pub, _ = make_pair_pems()
        with pytest.raises(CipherError):
            encrypt_to_base64(b"x", pub, segment_size=0)

    def test_cipher_not_multiple_of_256(self):
        _, priv = make_pair_pems()
        bad = base64.b64encode(b"x" * 100).decode()
        with pytest.raises(CipherError) as ei:
            decrypt_from_base64(bad, priv)
        assert "256" in str(ei.value)

    def test_empty_cipher_rejected(self):
        _, priv = make_pair_pems()
        with pytest.raises(CipherError):
            decrypt_from_base64("  ", priv)

    def test_mismatched_pair(self):
        """A 公钥加密 + B 私钥解密：两种栈行为都必须「可被察觉」，绝不能静默
        还原出正确明文——旧栈（OpenSSL<3.6）padding 校验失败抛 ValueError →
        包装成配对类 CipherError；新栈（OpenSSL≥3.6 反 Bleichenbacher）不抛错
        而返回垃圾明文 → 靠往返比对/下游 JSON 解析暴露"""
        pub_a, _ = make_pair_pems()
        _, priv_b = make_pair_pems()
        cipher = encrypt_to_base64(b"secret", pub_a)
        try:
            out = decrypt_from_base64(cipher, priv_b)
        except CipherError as ei:
            assert "配对" in str(ei.value) or "混用" in str(ei.value)
        else:
            assert out != b"secret"

    def test_resolve_key_pair_missing(self):
        with pytest.raises(CipherError) as ei:
            resolve_key_pair({}, "customs")
        msg = str(ei.value)
        assert "环境" in msg and "加密配置" in msg and "customs" in msg

    def test_verify_key_pair_ok(self):
        pub, priv = make_pair_pems()
        sample_len = verify_key_pair(pub, priv)
        # 600 字节 / 244 → 3 段 → 768 字节密文 → 1024 Base64 字符
        assert sample_len == 1024

    def test_verify_key_pair_requires_both(self):
        pub, _ = make_pair_pems()
        with pytest.raises(CipherError) as ei:
            verify_key_pair(pub, None)
        assert "公钥" in str(ei.value) and "私钥" in str(ei.value)

    def test_verify_key_pair_mismatched(self):
        pub_a, _ = make_pair_pems()
        _, priv_b = make_pair_pems()
        with pytest.raises(CipherError):
            verify_key_pair(pub_a, priv_b)


class TestKeyPairsFromConfig:
    def test_parse_and_defaults(self):
        cfg = {"key_pairs": [
            {"name": "customs", "public_key": "P1", "private_key": "K1"},
            {"name": "cfca", "public_key": "P2", "private_key": None},
            {"broken": "x"},  # 非 dict / 无 name 的行跳过
            {"name": "customs", "public_key": "P3"},  # 重名后者覆盖
        ]}
        table = key_pairs_from_config(cfg)
        assert set(table) == {"customs", "cfca"}
        assert table["customs"] == {"public_key": "P3", "private_key": None}
        assert table["cfca"]["public_key"] == "P2"

    def test_none_config(self):
        assert key_pairs_from_config(None) == {}
        assert key_pairs_from_config({}) == {}

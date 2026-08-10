"""auth 模块单测：密码哈希、密码强度校验、Token 签发与验证。"""
import base64
import hashlib
import hmac
import json
import time

from app import auth


class TestPasswordHash:
    def test_hash_returns_non_empty(self):
        h = auth.hash_password("test1234")
        assert isinstance(h, str)
        assert "$" in h

    def test_hash_contains_salt_and_hash(self):
        h = auth.hash_password("test1234")
        parts = h.split("$", 1)
        assert len(parts) == 2
        # salt 是 32 位十六进制
        assert len(parts[0]) == 32

    def test_verify_correct_password(self):
        h = auth.hash_password("myPassword1")
        assert auth.verify_password("myPassword1", h) is True

    def test_verify_wrong_password(self):
        h = auth.hash_password("myPassword1")
        assert auth.verify_password("wrongPassword", h) is False

    def test_hash_unique_per_call(self):
        # 随机 salt 保证同一密码两次哈希结果不同
        h1 = auth.hash_password("samePass1")
        h2 = auth.hash_password("samePass1")
        assert h1 != h2

    def test_verify_invalid_stored_format(self):
        assert auth.verify_password("test", "invalid_no_dollar") is False
        assert auth.verify_password("test", "") is False


class TestPasswordStrength:
    def test_valid_password(self):
        ok, msg = auth.validate_password_strength("abcd1234")
        assert ok is True
        assert msg == ""

    def test_too_short(self):
        ok, msg = auth.validate_password_strength("ab1")
        assert ok is False
        assert "8" in msg

    def test_too_long(self):
        ok, msg = auth.validate_password_strength("a" * 65 + "1")
        assert ok is False
        assert "64" in msg

    def test_no_digits(self):
        ok, msg = auth.validate_password_strength("abcdefgh")
        assert ok is False
        assert "字母" in msg or "数字" in msg

    def test_no_letters(self):
        ok, msg = auth.validate_password_strength("12345678")
        assert ok is False
        assert "字母" in msg or "数字" in msg

    def test_empty_password(self):
        ok, msg = auth.validate_password_strength("")
        assert ok is False

    def test_boundary_length_8(self):
        ok, _ = auth.validate_password_strength("abcd1234")
        assert ok is True


class TestToken:
    def test_create_token_returns_string(self):
        token = auth.create_token(1, "admin", "admin")
        assert isinstance(token, str)
        assert "." in token

    def test_decode_valid_token(self):
        token = auth.create_token(42, "testuser", "member")
        payload = auth.decode_token(token)
        assert payload is not None
        assert payload["uid"] == 42
        assert payload["username"] == "testuser"
        assert payload["role"] == "member"
        assert "exp" in payload

    def test_decode_invalid_token(self):
        assert auth.decode_token("invalid.token.string") is None
        assert auth.decode_token("") is None
        assert auth.decode_token("no_dot_here") is None

    def test_decode_tampered_payload(self):
        token = auth.create_token(1, "admin", "admin")
        payload_b64, sig_b64 = token.split(".", 1)
        # 篡改 payload：把 uid 改成 999
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        payload["uid"] = 999
        tampered_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode())
        tampered_token = f"{tampered_b64.decode()}.{sig_b64}"
        # 验签失败
        assert auth.decode_token(tampered_token) is None

    def test_decode_expired_token(self):
        # 手动构造过期 token
        payload = {
            "uid": 1,
            "username": "admin",
            "role": "admin",
            "exp": int(time.time()) - 1,  # 已过期
        }
        payload_b64 = base64.urlsafe_b64encode(
            json.dumps(payload, separators=(",", ":")).encode("utf-8")
        )
        sig = hmac.new(
            auth._SECRET_KEY.encode("utf-8"), payload_b64, hashlib.sha256
        ).digest()
        sig_b64 = base64.urlsafe_b64encode(sig)
        expired_token = f"{payload_b64.decode()}.{sig_b64.decode()}"
        assert auth.decode_token(expired_token) is None

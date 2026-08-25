"""
鉴权模块：密码哈希（pbkdf2_hmac）+ Token（HMAC-SHA256 签名）+ get_current_user 依赖。

零第三方依赖，全部使用 Python 标准库（hashlib / hmac / secrets / base64 / json / time），
避免 Python 3.14 下 passlib/bcrypt 的 wheel 兼容问题。
"""
import base64
import hashlib
import hmac
import json
import os
import secrets
import time

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from . import models
from .database import get_db

# Token 签名密钥：必须从环境变量 JWT_SECRET_KEY 读取，启动时由 main.py 校验
_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "")

# Token 有效期：7 天
_TOKEN_EXPIRE_SECONDS = 7 * 24 * 3600

# 登录失败统一提示，避免泄露用户是否存在
_BAD_CREDENTIALS = "用户名或密码错误"

_bearer = HTTPBearer(auto_error=False)


# ============ 密码哈希 ============
def hash_password(password: str) -> str:
    """生成密码哈希：pbkdf2_hmac(sha256) + 随机 salt，返回 'salt$hash' 十六进制串"""
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), 100000)
    return f"{salt}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """校验密码：stored 格式 'salt$hash'"""
    try:
        salt, hash_hex = stored.split("$", 1)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), 100000)
        return hmac.compare_digest(dk.hex(), hash_hex)
    except (ValueError, AttributeError):
        return False


# ============ 密码强度校验 ============
# 规则：长度≥8，必须同时包含数字和字母
_PASSWORD_MIN_LENGTH = 8
_PASSWORD_MAX_LENGTH = 64
_PASSWORD_LETTER_RE = None  # 延迟初始化，避免在模块加载时编译
_PASSWORD_DIGIT_RE = None


def validate_password_strength(password: str) -> tuple[bool, str]:
    """校验密码强度。
    返回 (是否通过, 错误提示)。通过时错误提示为空字符串。
    规则：长度 8-64，必须同时包含字母和数字。
    """
    global _PASSWORD_LETTER_RE, _PASSWORD_DIGIT_RE
    if _PASSWORD_LETTER_RE is None:
        import re
        _PASSWORD_LETTER_RE = re.compile(r"[A-Za-z]")
        _PASSWORD_DIGIT_RE = re.compile(r"[0-9]")
    if not password or len(password) < _PASSWORD_MIN_LENGTH:
        return False, f"密码长度不能少于 {_PASSWORD_MIN_LENGTH} 位"
    if len(password) > _PASSWORD_MAX_LENGTH:
        return False, f"密码长度不能超过 {_PASSWORD_MAX_LENGTH} 位"
    if not _PASSWORD_LETTER_RE.search(password):
        return False, "密码必须同时包含字母和数字"
    if not _PASSWORD_DIGIT_RE.search(password):
        return False, "密码必须同时包含字母和数字"
    return True, ""


# ============ Token ============
def create_token(user_id: int, username: str, role: str) -> str:
    """生成 token：base64(payload).base64(hmac_sig)"""
    payload = {
        "uid": user_id,
        "username": username,
        "role": role,
        "exp": int(time.time()) + _TOKEN_EXPIRE_SECONDS,
    }
    payload_b64 = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    sig = hmac.new(_SECRET_KEY.encode("utf-8"), payload_b64, hashlib.sha256).digest()
    sig_b64 = base64.urlsafe_b64encode(sig)
    return f"{payload_b64.decode()}.{sig_b64.decode()}"


def decode_token(token: str) -> dict | None:
    """解析并校验 token：验签 + 验过期。失败返回 None。"""
    try:
        payload_b64, sig_b64 = token.split(".", 1)
        # 验签
        expected_sig = hmac.new(_SECRET_KEY.encode("utf-8"), payload_b64.encode("utf-8"), hashlib.sha256).digest()
        actual_sig = base64.urlsafe_b64decode(sig_b64)
        if not hmac.compare_digest(expected_sig, actual_sig):
            return None
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        if int(payload.get("exp", 0)) < int(time.time()):
            return None
        return payload
    except (ValueError, KeyError, json.JSONDecodeError):
        return None


# ============ FastAPI 依赖 ============
def get_current_user(
    cred: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> models.User:
    """解析 Bearer token，返回当前用户。未登录或 token 失效抛 401。"""
    if cred is None or not cred.credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录或登录已过期")
    payload = decode_token(cred.credentials)
    if payload is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录已过期，请重新登录")
    user = db.query(models.User).filter(models.User.id == payload.get("uid")).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在")
    return user


def get_optional_user(
    cred: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> models.User | None:
    """可选鉴权：有 token 且有效返回用户，否则返回 None（用于兼容老接口的可选审计）"""
    if cred is None or not cred.credentials:
        return None
    payload = decode_token(cred.credentials)
    if payload is None:
        return None
    return db.query(models.User).filter(models.User.id == payload.get("uid")).first()

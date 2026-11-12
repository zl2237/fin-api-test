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
from datetime import datetime

from fastapi import Depends, Header, HTTPException, status
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
        payload: dict = json.loads(base64.urlsafe_b64decode(payload_b64))
        if int(payload.get("exp", 0)) < int(time.time()):
            return None
        return payload
    except (ValueError, KeyError, json.JSONDecodeError):
        return None


# ============ API Key（外部触发用） ============
# 明文格式：fin_ + 43 位 urlsafe 随机串；库中只存 sha256，明文仅创建时返回一次
_API_KEY_PREFIX = "fin_"


def generate_api_key() -> str:
    """生成 API 密钥明文（仅此一处产生，调用方负责一次性展示）。"""
    return _API_KEY_PREFIX + secrets.token_urlsafe(32)


def hash_api_key(raw: str) -> str:
    """密钥明文 → sha256 十六进制（64 位），入库与比对都用哈希。"""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def resolve_api_key_user(db: Session, raw_key: str) -> tuple[models.User, models.ApiKey] | None:
    """按明文解析密钥 → (密钥身份用户, 密钥记录)。无效/不存在返回 None。

    命中即回写 last_used_at（失败静默，不影响认证主流程）。
    """
    raw = (raw_key or "").strip()
    if not raw.startswith(_API_KEY_PREFIX):
        return None
    key = db.query(models.ApiKey).filter(models.ApiKey.key_hash == hash_api_key(raw)).first()
    if key is None:
        return None
    user = db.query(models.User).filter(models.User.id == key.created_by).first()
    if user is None:
        return None
    try:
        key.last_used_at = datetime.now()
        db.commit()
    except Exception:  # noqa: BLE001  last_used_at 回写失败不阻断认证
        db.rollback()
    return user, key


# ============ FastAPI 依赖 ============
def get_current_user(
    cred: HTTPAuthorizationCredentials | None = Depends(_bearer),
    x_api_key: str | None = Header(None, alias="X-API-Key"),
    db: Session = Depends(get_db),
) -> models.User:
    """鉴权双通道：API 密钥（Bearer fin_* 或 X-API-Key 头）→ JWT。

    密钥认证即创建人身份（member 密钥只有 member 权限）；
    非密钥凭据走原 JWT 路径，行为不变。
    """
    raw_key: str | None = None
    if x_api_key:
        raw_key = x_api_key
    elif cred is not None and (cred.credentials or "").startswith(_API_KEY_PREFIX):
        raw_key = cred.credentials
    if raw_key:
        resolved = resolve_api_key_user(db, raw_key)
        if resolved is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="API 密钥无效或已吊销")
        return resolved[0]
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

"""auth 域：登录安全策略 / 注册 / 自助改密 / 头像校验。

不变量（从 routers/auth.py 下沉）：
- 登录锁定：连续失败 5 次锁定 15 分钟；锁定期间拒绝登录并提示剩余分钟
- 注册：首个用户自动 admin，其余 member；重名拒绝
- 改密：新密码不得与当前相同；成功清除 must_change_password
- 头像：base64 data URL（jpeg/png/webp），上限 200KB
"""
import re
from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy.orm import Session

from .. import models
from ..auth import hash_password, verify_password, validate_password_strength

# 登录安全策略：连续失败 5 次锁定 15 分钟
LOGIN_MAX_FAILS = 5
LOGIN_LOCK_MINUTES = 15

# 头像校验：base64 data URL，支持 jpeg/png/webp，上限 200KB（base64 后约 270KB 字符）
_AVATAR_DATA_URL_RE = re.compile(r"^data:image/(jpeg|png|webp);base64,([A-Za-z0-9+/=]+)$")
_AVATAR_MAX_BYTES = 200 * 1024


def get_user_by_username(db: Session, username: str):
    return db.query(models.User).filter(models.User.username == username).first()


def get_user_by_id(db: Session, user_id: int):
    return db.query(models.User).filter(models.User.id == user_id).first()


def authenticate_user(db: Session, username: str, password: str) -> models.User:
    """校验用户名密码。通过返回 user（计数已清零），否则抛 HTTPException。

    锁定检查在密码校验之前，避免泄露用户是否存在。
    """
    user = get_user_by_username(db, username)

    if user and user.locked_until and user.locked_until > datetime.now():
        remain = int((user.locked_until - datetime.now()).total_seconds() / 60) + 1
        raise HTTPException(403, f"账号已锁定，请 {remain} 分钟后重试")

    if not user or not verify_password(password, user.password_hash):
        # 登录失败：累加失败计数，达到阈值则锁定
        if user:
            user.failed_count = (user.failed_count or 0) + 1
            if user.failed_count >= LOGIN_MAX_FAILS:
                user.locked_until = datetime.now() + timedelta(minutes=LOGIN_LOCK_MINUTES)
                db.commit()
                raise HTTPException(403, f"连续登录失败 {LOGIN_MAX_FAILS} 次，账号已锁定 {LOGIN_LOCK_MINUTES} 分钟")
            db.commit()
        raise HTTPException(401, "用户名或密码错误")

    # 登录成功：清空失败计数和锁定状态
    user.failed_count = 0
    user.locked_until = None
    db.commit()
    return user


def register_user(db: Session, data) -> models.User:
    """注册新用户。首个用户自动成为 admin，其余为 member。"""
    if get_user_by_username(db, data.username):
        raise HTTPException(400, "用户名已存在")
    ok, msg = validate_password_strength(data.password)
    if not ok:
        raise HTTPException(400, msg)
    is_first = db.query(models.User).count() == 0
    user = models.User(
        username=data.username,
        password_hash=hash_password(data.password),
        name=data.name or data.username,
        role="admin" if is_first else "member",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def change_password(db: Session, user: models.User, new_password: str) -> None:
    """自助修改密码：强度校验 + 不得与当前相同；成功清除 must_change_password。"""
    ok, msg = validate_password_strength(new_password)
    if not ok:
        raise HTTPException(400, msg)
    if verify_password(new_password, user.password_hash):
        raise HTTPException(400, "新密码不能与当前密码相同")
    user.password_hash = hash_password(new_password)
    user.must_change_password = False
    db.commit()


def validate_avatar(data_url: str) -> None:
    """校验 base64 头像 data URL：格式 + 大小"""
    m = _AVATAR_DATA_URL_RE.match(data_url or "")
    if not m:
        raise HTTPException(400, "头像格式不正确，需为 jpeg/png/webp 的 base64 data URL")
    b64 = m.group(2)
    # base64 字符串长度估算原始字节数：len * 3/4
    if len(b64) * 3 // 4 > _AVATAR_MAX_BYTES:
        raise HTTPException(400, f"头像过大（超过 {_AVATAR_MAX_BYTES // 1024}KB），请先压缩")

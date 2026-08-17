"""鉴权路由：登录 / 注册 / 获取当前用户 / 头像管理"""
import re
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from .. import models, schemas
from ..auth import (
    hash_password, verify_password, create_token, get_current_user,
    validate_password_strength,
)

router = APIRouter(prefix="/api/auth", tags=["鉴权"])

# 登录安全策略：连续失败 5 次锁定 15 分钟
_LOGIN_MAX_FAILS = 5
_LOGIN_LOCK_MINUTES = 15

# 头像校验：base64 data URL，支持 jpeg/png/webp，上限 200KB（base64 后约 270KB 字符）
_AVATAR_DATA_URL_RE = re.compile(r"^data:image/(jpeg|png|webp);base64,([A-Za-z0-9+/=]+)$")
_AVATAR_MAX_BYTES = 200 * 1024


@router.post("/login", response_model=schemas.LoginResponse)
def login(data: schemas.LoginRequest, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.username == data.username).first()

    # 账号锁定检查（在密码校验之前，避免泄露用户是否存在）
    if user and user.locked_until and user.locked_until > datetime.now():
        remain = int((user.locked_until - datetime.now()).total_seconds() / 60) + 1
        raise HTTPException(403, f"账号已锁定，请 {remain} 分钟后重试")

    if not user or not verify_password(data.password, user.password_hash):
        # 登录失败：累加失败计数，达到阈值则锁定
        if user:
            user.failed_count = (user.failed_count or 0) + 1
            if user.failed_count >= _LOGIN_MAX_FAILS:
                user.locked_until = datetime.now() + timedelta(minutes=_LOGIN_LOCK_MINUTES)
                db.commit()
                raise HTTPException(403, f"连续登录失败 {_LOGIN_MAX_FAILS} 次，账号已锁定 {_LOGIN_LOCK_MINUTES} 分钟")
            db.commit()
        raise HTTPException(401, "用户名或密码错误")

    # 登录成功：清空失败计数和锁定状态
    user.failed_count = 0
    user.locked_until = None
    db.commit()

    token = create_token(user.id, user.username, user.role)
    return schemas.LoginResponse(
        token=token,
        user=schemas.UserOut.model_validate(user),
    )


@router.post("/register", response_model=schemas.LoginResponse)
def register(data: schemas.RegisterRequest, db: Session = Depends(get_db)):
    """注册新用户。首个用户自动成为 admin，其余为 member。"""
    existing = db.query(models.User).filter(models.User.username == data.username).first()
    if existing:
        raise HTTPException(400, "用户名已存在")
    # 密码强度校验
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
    token = create_token(user.id, user.username, user.role)
    return schemas.LoginResponse(
        token=token,
        user=schemas.UserOut.model_validate(user),
    )


@router.get("/me", response_model=schemas.UserOut)
def me(current: models.User = Depends(get_current_user)):
    return current


@router.post("/change-password")
def change_password(
    data: schemas.ChangePasswordRequest,
    current: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """用户自助修改密码。

    用于默认 admin 首次登录强制改密，或用户主动修改自己的密码。
    强制改密场景用户刚登录已验证身份，故不要求旧密码。
    改密成功后清空 must_change_password 标记。
    """
    ok, msg = validate_password_strength(data.new_password)
    if not ok:
        raise HTTPException(400, msg)
    # 新密码不能与旧密码相同
    if verify_password(data.new_password, current.password_hash):
        raise HTTPException(400, "新密码不能与当前密码相同")
    current.password_hash = hash_password(data.new_password)
    current.must_change_password = False
    db.commit()
    return {"message": "密码修改成功"}


# ============ 头像管理 ============
def _validate_avatar(data_url: str) -> None:
    """校验 base64 头像 data URL：格式 + 大小"""
    m = _AVATAR_DATA_URL_RE.match(data_url or "")
    if not m:
        raise HTTPException(400, "头像格式不正确，需为 jpeg/png/webp 的 base64 data URL")
    b64 = m.group(2)
    # base64 字符串长度估算原始字节数：len * 3/4
    if len(b64) * 3 // 4 > _AVATAR_MAX_BYTES:
        raise HTTPException(400, f"头像过大（超过 {_AVATAR_MAX_BYTES // 1024}KB），请先压缩")


@router.put("/avatar")
def update_avatar(
    data: schemas.AvatarUpdate,
    current: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """上传/更新当前用户头像（前端 canvas 压缩后的 base64 data URL）"""
    _validate_avatar(data.avatar)
    current.avatar = data.avatar
    db.commit()
    return {"message": "头像已更新"}


@router.delete("/avatar")
def remove_avatar(
    current: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """删除当前用户头像"""
    current.avatar = None
    db.commit()
    return {"message": "头像已删除"}


@router.get("/avatar/{user_id}")
def get_avatar(
    user_id: int,
    db: Session = Depends(get_db),
    _current: models.User = Depends(get_current_user),
):
    """按用户 ID 获取头像。未设置返回 null。"""
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(404, "用户不存在")
    return {"avatar": user.avatar, "name": user.name or user.username}

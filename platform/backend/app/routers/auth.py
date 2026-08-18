"""鉴权路由：登录 / 注册 / 获取当前用户 / 头像管理

登录锁定策略 / 首管理员规则 / 改密不变量 / 头像校验在 app.crud.auth 域模块；本层只管 HTTP 语义。
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from .. import models, schemas
from ..auth import create_token, get_current_user
from ..crud import auth as auth_domain

router = APIRouter(prefix="/api/auth", tags=["鉴权"])


@router.post("/login", response_model=schemas.LoginResponse)
def login(data: schemas.LoginRequest, db: Session = Depends(get_db)):
    user = auth_domain.authenticate_user(db, data.username, data.password)
    token = create_token(user.id, user.username, user.role)
    return schemas.LoginResponse(
        token=token,
        user=schemas.UserOut.model_validate(user),
    )


@router.post("/register", response_model=schemas.LoginResponse)
def register(data: schemas.RegisterRequest, db: Session = Depends(get_db)):
    """注册新用户。首个用户自动成为 admin，其余为 member。"""
    user = auth_domain.register_user(db, data)
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
    auth_domain.change_password(db, current, data.new_password)
    return {"message": "密码修改成功"}


# ============ 头像管理 ============
@router.put("/avatar")
def update_avatar(
    data: schemas.AvatarUpdate,
    current: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """上传/更新当前用户头像（前端 canvas 压缩后的 base64 data URL）"""
    auth_domain.validate_avatar(data.avatar)
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


@router.get("/avatar/{user_id}", response_model=schemas.AvatarOut)
def get_avatar(
    user_id: int,
    db: Session = Depends(get_db),
    _current: models.User = Depends(get_current_user),
):
    """按用户 ID 获取头像。未设置返回 null。"""
    user = auth_domain.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(404, "用户不存在")
    return {"avatar": user.avatar, "name": user.name or user.username}

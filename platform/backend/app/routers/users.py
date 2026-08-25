"""用户管理路由：仅管理员可访问。列表 / 新增 / 删除 / 重置密码 / 修改角色 / 编辑资料

业务不变量（唯一性/最后管理员保护/审计）在 app.crud.users 域模块；本层只管 HTTP 语义。
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import crud, models, schemas
from ..auth import get_current_user
from ..crud import users as users_domain
from ..database import get_db

router = APIRouter(prefix="/api/users", tags=["用户管理"])


def _require_admin(user: models.User = Depends(get_current_user)) -> models.User:
    """仅管理员可访问用户管理接口"""
    if user.role != "admin":
        raise HTTPException(403, "需要管理员权限")
    return user


@router.get("", response_model=list[schemas.UserOut])
def list_users(db: Session = Depends(get_db), _admin: models.User = Depends(_require_admin)):
    objs = users_domain.list_users(db)
    crud.fill_audit_names_batch(db, objs)
    return objs


@router.get("/simple", response_model=list[schemas.SimpleUserOut])
def list_users_simple(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """所有登录用户可访问的轻量用户列表，仅供筛选下拉用，仅返回 id 和显示名"""
    return users_domain.list_users_simple(db)


@router.post("", response_model=schemas.UserOut)
def create_user(data: schemas.UserCreateRequest, db: Session = Depends(get_db), _admin: models.User = Depends(_require_admin)):
    return users_domain.create_user(db, data, operator=_admin)


@router.put("/{user_id}/role", response_model=schemas.UserOut)
def update_role(user_id: int, data: schemas.UserRoleUpdate, db: Session = Depends(get_db), admin: models.User = Depends(_require_admin)):
    user = users_domain.get_user(db, user_id)
    if not user:
        raise HTTPException(404, "用户不存在")
    return users_domain.update_role(db, user, data.role, operator=admin)


@router.put("/{user_id}", response_model=schemas.UserOut)
def update_user_info(user_id: int, data: schemas.UserInfoUpdate, db: Session = Depends(get_db), admin: models.User = Depends(_require_admin)):
    """编辑用户弹窗：用户名/显示名/手机号/邮箱/角色一次保存"""
    user = users_domain.get_user(db, user_id)
    if not user:
        raise HTTPException(404, "用户不存在")
    return users_domain.update_user_info(db, user, data, operator=admin)


@router.put("/{user_id}/password")
def reset_password(user_id: int, data: schemas.UserPasswordReset, db: Session = Depends(get_db), _admin: models.User = Depends(_require_admin)):
    user = users_domain.get_user(db, user_id)
    if not user:
        raise HTTPException(404, "用户不存在")
    users_domain.reset_password(db, user, data.password, operator=_admin)
    return {"message": "密码已重置"}


@router.delete("/{user_id}")
def delete_user(user_id: int, db: Session = Depends(get_db), admin: models.User = Depends(_require_admin)):
    user = users_domain.get_user(db, user_id)
    if not user:
        raise HTTPException(404, "用户不存在")
    users_domain.delete_user(db, user, operator=admin)
    return {"message": "已删除"}

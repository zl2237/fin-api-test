"""用户管理路由：仅管理员可访问。列表 / 新增 / 删除 / 重置密码 / 修改角色"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from .. import models, schemas, auth, crud
from ..auth import get_current_user, hash_password, validate_password_strength

router = APIRouter(prefix="/api/users", tags=["用户管理"])


def _require_admin(user: models.User = Depends(get_current_user)) -> models.User:
    """仅管理员可访问用户管理接口"""
    if user.role != "admin":
        raise HTTPException(403, "需要管理员权限")
    return user


@router.get("", response_model=list[schemas.UserOut])
def list_users(db: Session = Depends(get_db), _admin: models.User = Depends(_require_admin)):
    objs = db.query(models.User).order_by(models.User.id).all()
    crud.fill_audit_names_batch(db, objs)
    return objs


@router.get("/simple")
def list_users_simple(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """所有登录用户可访问的轻量用户列表，仅供筛选下拉用，仅返回 id 和显示名"""
    rows = db.query(models.User.id, models.User.name, models.User.username).order_by(models.User.id).all()
    return [{"id": r[0], "name": r[1] or r[2]} for r in rows]


@router.post("", response_model=schemas.UserOut)
def create_user(data: schemas.UserCreateRequest, db: Session = Depends(get_db), _admin: models.User = Depends(_require_admin)):
    if db.query(models.User).filter(models.User.username == data.username).first():
        raise HTTPException(400, "用户名已存在")
    # 密码强度校验
    ok, msg = validate_password_strength(data.password)
    if not ok:
        raise HTTPException(400, msg)
    user = models.User(
        username=data.username,
        password_hash=hash_password(data.password),
        name=data.name or data.username,
        role=data.role if data.role in ("admin", "member") else "member",
        created_by=_admin.id,
        updated_by=_admin.id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    crud.log_operation(db, _admin, "create", "user", user.id, user.username)
    return user


@router.put("/{user_id}/role", response_model=schemas.UserOut)
def update_role(user_id: int, data: schemas.UserRoleUpdate, db: Session = Depends(get_db), admin: models.User = Depends(_require_admin)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(404, "用户不存在")
    if data.role not in ("admin", "member"):
        raise HTTPException(400, "角色无效")
    # 防止最后一个管理员把自己降级
    if user.role == "admin" and data.role == "member":
        admin_count = db.query(models.User).filter(models.User.role == "admin").count()
        if admin_count <= 1:
            raise HTTPException(400, "至少保留一个管理员")
    user.role = data.role
    user.updated_by = admin.id
    db.commit()
    db.refresh(user)
    crud.log_operation(db, admin, "update", "user", user.id, user.username, f"修改角色为{data.role}")
    return user


@router.put("/{user_id}/password")
def reset_password(user_id: int, data: schemas.UserPasswordReset, db: Session = Depends(get_db), _admin: models.User = Depends(_require_admin)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(404, "用户不存在")
    # 密码强度校验
    ok, msg = validate_password_strength(data.password)
    if not ok:
        raise HTTPException(400, msg)
    user.password_hash = hash_password(data.password)
    user.updated_by = _admin.id
    # 重置密码时清空失败计数和锁定状态
    user.failed_count = 0
    user.locked_until = None
    db.commit()
    crud.log_operation(db, _admin, "update", "user", user.id, user.username, "重置密码")
    return {"message": "密码已重置"}


@router.delete("/{user_id}")
def delete_user(user_id: int, db: Session = Depends(get_db), admin: models.User = Depends(_require_admin)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(404, "用户不存在")
    if user.id == admin.id:
        raise HTTPException(400, "不能删除自己")
    if user.role == "admin":
        admin_count = db.query(models.User).filter(models.User.role == "admin").count()
        if admin_count <= 1:
            raise HTTPException(400, "至少保留一个管理员")
    db.delete(user)
    db.commit()
    crud.log_operation(db, admin, "delete", "user", user.id, user.username)
    return {"message": "已删除"}

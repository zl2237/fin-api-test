"""users 域：用户管理的不变量与事务（唯一性 / 最后管理员保护 / 审计变更拼接）。

router 只保留 HTTP 语义（状态码/权限校验），数据访问与业务规则收敛到此。
"""
import re
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from .. import models, crud
from ..auth import hash_password, validate_password_strength

# 手机号：1 开头 + 10 位数字；邮箱：常规格式校验
_PHONE_RE = re.compile(r"^1[3-9]\d{9}$")
_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")


def list_users(db: Session):
    return db.query(models.User).order_by(models.User.id).all()


def list_users_simple(db: Session):
    """轻量用户列表（筛选下拉用），仅返回 id 和显示名"""
    rows = db.query(models.User.id, models.User.name, models.User.username).order_by(models.User.id).all()
    return [{"id": r[0], "name": r[1] or r[2]} for r in rows]


def get_user(db: Session, user_id: int) -> Optional[models.User]:
    return db.query(models.User).filter(models.User.id == user_id).first()


def create_user(db: Session, data, operator: models.User) -> models.User:
    """创建用户：用户名唯一 + 密码强度 + 角色白名单（非法回退 member）"""
    if db.query(models.User).filter(models.User.username == data.username).first():
        raise HTTPException(400, "用户名已存在")
    ok, msg = validate_password_strength(data.password)
    if not ok:
        raise HTTPException(400, msg)
    user = models.User(
        username=data.username,
        password_hash=hash_password(data.password),
        name=data.name or data.username,
        role=data.role if data.role in ("admin", "member") else "member",
        created_by=operator.id,
        updated_by=operator.id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    crud.log_operation(db, operator, "create", "user", user.id, user.username)
    return user


def _assert_last_admin_protection(db: Session, user: models.User, new_role: str):
    """最后管理员保护：降级最后一个 admin 前必须还剩其他 admin"""
    if user.role == "admin" and new_role == "member":
        admin_count = db.query(models.User).filter(models.User.role == "admin").count()
        if admin_count <= 1:
            raise HTTPException(400, "至少保留一个管理员")


def update_role(db: Session, user: models.User, new_role: str, operator: models.User) -> models.User:
    """修改角色：角色白名单 + 最后管理员保护"""
    if new_role not in ("admin", "member"):
        raise HTTPException(400, "角色无效")
    _assert_last_admin_protection(db, user, new_role)
    user.role = new_role
    user.updated_by = operator.id
    db.commit()
    db.refresh(user)
    crud.log_operation(db, operator, "update", "user", user.id, user.username, f"修改角色为{new_role}")
    return user


def update_user_info(db: Session, user: models.User, data, operator: models.User) -> models.User:
    """编辑用户：用户名/显示名/手机号/邮箱/角色一次保存，含格式与唯一性校验、审计变更拼接"""
    if data.role not in ("admin", "member"):
        raise HTTPException(400, "角色无效")
    new_username = data.username.strip()
    if len(new_username) < 2:
        raise HTTPException(400, "用户名至少 2 个字符")
    if db.query(models.User).filter(models.User.username == new_username, models.User.id != user.id).first():
        raise HTTPException(400, "用户名已存在")
    new_phone = (data.phone or "").strip() or None
    if new_phone and not _PHONE_RE.match(new_phone):
        raise HTTPException(400, "手机号格式不正确")
    if new_phone and db.query(models.User).filter(models.User.phone == new_phone, models.User.id != user.id).first():
        raise HTTPException(400, "手机号已被其他用户使用")
    new_email = (data.email or "").strip().lower() or None
    if new_email and not _EMAIL_RE.match(new_email):
        raise HTTPException(400, "邮箱格式不正确")
    if new_email and db.query(models.User).filter(models.User.email == new_email, models.User.id != user.id).first():
        raise HTTPException(400, "邮箱已被其他用户使用")
    _assert_last_admin_protection(db, user, data.role)

    changes = []
    if user.username != new_username:
        user.username = new_username
        changes.append(f"用户名 -> {new_username}")
    new_name = (data.name or "").strip() or None
    if user.name != new_name:
        user.name = new_name
        changes.append(f"显示名 -> {new_name or new_username}")
    if user.phone != new_phone:
        user.phone = new_phone
        changes.append(f"手机号 -> {new_phone or '空'}")
    if user.email != new_email:
        user.email = new_email
        changes.append(f"邮箱 -> {new_email or '空'}")
    new_department = (data.department or "").strip() or None
    if user.department != new_department:
        user.department = new_department
        changes.append(f"部门 -> {new_department or '空'}")
    if user.role != data.role:
        user.role = data.role
        changes.append(f"角色 -> {data.role}")
    user.updated_by = operator.id
    db.commit()
    db.refresh(user)
    crud.fill_audit_names_batch(db, [user])
    crud.log_operation(db, operator, "update", "user", user.id, user.username, "；".join(changes) or "无变更")
    return user


def reset_password(db: Session, user: models.User, new_password: str, operator: models.User) -> None:
    """重置密码：强度校验 + 清空失败计数/锁定状态"""
    ok, msg = validate_password_strength(new_password)
    if not ok:
        raise HTTPException(400, msg)
    user.password_hash = hash_password(new_password)
    user.updated_by = operator.id
    user.failed_count = 0
    user.locked_until = None
    db.commit()
    crud.log_operation(db, operator, "update", "user", user.id, user.username, "重置密码")


def delete_user(db: Session, user: models.User, operator: models.User) -> None:
    """删除用户：不能删自己 + 最后管理员保护"""
    if user.id == operator.id:
        raise HTTPException(400, "不能删除自己")
    if user.role == "admin":
        admin_count = db.query(models.User).filter(models.User.role == "admin").count()
        if admin_count <= 1:
            raise HTTPException(400, "至少保留一个管理员")
    db.delete(user)
    db.commit()
    crud.log_operation(db, operator, "delete", "user", user.id, user.username)

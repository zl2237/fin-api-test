"""API 密钥管理：供外部系统（Jenkins/CI/脚本）以密钥身份触发执行。

- 创建：生成 fin_ 前缀明文，库中只存 sha256；明文仅创建响应返回一次
- 认证：auth.get_current_user 双通道（Authorization: Bearer fin_* 或 X-API-Key 头），
  密钥身份 = 创建人身份（member 创建的 key 只有 member 权限）
- 吊销：删除即失效（下一次请求 401）
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import auth, crud, models, schemas
from ..auth import get_current_user
from ..database import get_db

router = APIRouter(prefix="/api/api-keys", tags=["API密钥"])


@router.get("", response_model=list[schemas.ApiKeyOut])
def list_keys(
    project_id: int | None = None,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """密钥列表（按项目过滤）。密钥材料永不回显，只有 key_prefix 辨识。"""
    q = db.query(models.ApiKey)
    if project_id:
        q = q.filter(models.ApiKey.project_id == project_id)
    objs = q.order_by(models.ApiKey.id.desc()).all()
    crud.fill_audit_names_batch(db, objs)
    return objs


@router.post("", response_model=schemas.ApiKeyCreatedOut)
def create_key(
    data: schemas.ApiKeyCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """创建密钥：member 即可（外部触发不限于管理员）。

    明文只在本次响应返回一次；前端弹窗关闭后不可再查，丢失只能删旧建新。
    """
    project = db.query(models.Project).filter(models.Project.id == data.project_id).first()
    if project is None:
        raise HTTPException(404, "项目不存在")
    raw = auth.generate_api_key()
    obj = models.ApiKey(
        project_id=data.project_id,
        name=data.name,
        key_hash=auth.hash_api_key(raw),
        key_prefix=raw[:12],
        created_by=user.id,
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    crud.fill_audit_names(db, obj)
    crud.log_operation(db, user, "create", "api_key", obj.id, obj.name)
    out = schemas.ApiKeyOut.model_validate(obj)
    return schemas.ApiKeyCreatedOut(**out.model_dump(), api_key=raw)


@router.delete("/{key_id}", response_model=schemas.MessageOut)
def delete_key(
    key_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """吊销密钥：本人自删或管理员删任意；删除即失效。"""
    obj = db.query(models.ApiKey).filter(models.ApiKey.id == key_id).first()
    if obj is None:
        raise HTTPException(404, "密钥不存在")
    if user.role != "admin" and obj.created_by != user.id:
        raise HTTPException(403, "只能删除自己创建的密钥")
    key_id, name = obj.id, obj.name  # 先捕获：删除提交后实例过期不可再取
    db.delete(obj)
    db.commit()
    crud.log_operation(db, user, "delete", "api_key", key_id, name)
    return {"message": "已吊销"}

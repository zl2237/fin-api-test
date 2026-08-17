"""文件中心路由：文件上传/下载/预览/重命名/删除 + 分类/标签 CRUD

存储约定：
- 物理目录：{UPLOAD_ROOT}/files/{sha256前2位}/{sha256}（默认 backend/uploads/files）
- 去重：同项目同 sha256 复用物理文件，ref_count 累加
- 删除：ref_count - 1，归零时删除物理文件
- 预览：图片/PDF 直接流式返回，其他类型仅下载
"""
import hashlib
import os
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..database import get_db
from .. import crud, schemas, models
from ..auth import get_current_user
from ..services.file_helpers import (
    build_storage_path as _build_storage_path,
    resolve_physical_path as _resolve_physical_path,
    is_previewable as _is_previewable,
)

router = APIRouter(prefix="/api/files", tags=["文件中心"])

_MAX_UPLOAD_SIZE_MB = int(os.getenv("MAX_UPLOAD_SIZE_MB", "50"))


# ============ 文件上传 ============
@router.post("/upload", response_model=schemas.FileOut)
async def upload_file(
    project_id: int = Query(..., description="所属项目ID"),
    file: UploadFile = File(...),
    category_id: Optional[int] = Query(None, description="分类ID"),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """上传单个文件，sha256 去重，同项目同内容复用物理文件"""
    content = await file.read()
    size = len(content)
    if size > _MAX_UPLOAD_SIZE_MB * 1024 * 1024:
        raise HTTPException(400, f"文件过大（超过 {_MAX_UPLOAD_SIZE_MB}MB）")
    if size == 0:
        raise HTTPException(400, "文件为空")

    sha256 = hashlib.sha256(content).hexdigest()
    content_type = file.content_type or "application/octet-stream"
    original_name = file.filename or "unnamed"

    # 项目内同 sha256 已存在：ref_count + 1，不重新落盘
    existing = crud.get_file_by_sha256(db, project_id, sha256)
    if existing:
        existing.ref_count += 1
        if user is not None:
            existing.updated_by = user.id
        db.commit()
        db.refresh(existing)
        crud.fill_audit_names(db, existing)
        crud.fill_file_tag_ids(db, [existing])
        return existing

    # 落盘
    storage_path = _build_storage_path(sha256)
    physical = _resolve_physical_path(storage_path)
    physical.parent.mkdir(parents=True, exist_ok=True)
    if not physical.exists():
        physical.write_bytes(content)

    obj = crud.create_file_record(
        db,
        project_id=project_id,
        name=original_name,
        original_name=original_name,
        content_type=content_type,
        size=size,
        sha256=sha256,
        storage_path=storage_path,
        category_id=category_id,
        user_id=user.id,
    )
    crud.fill_audit_names(db, obj)
    crud.fill_file_tag_ids(db, [obj])
    crud.log_operation(db, user, "upload", "file", obj.id, obj.name)
    return obj


# ============ 文件列表/详情 ============
@router.get("", response_model=List[schemas.FileOut])
def list_files(
    project_id: int = Query(..., description="所属项目ID"),
    category_id: Optional[int] = Query(None, description="按分类过滤"),
    tag_id: Optional[int] = Query(None, description="按标签过滤（单选，兼容旧参数）"),
    tag_ids: Optional[List[int]] = Query(None, description="按标签过滤（多选，OR 语义）"),
    keyword: Optional[str] = Query(None, description="按名称模糊搜索"),
    db: Session = Depends(get_db),
    _user: models.User = Depends(get_current_user),
):
    objs = crud.list_files(db, project_id, category_id, tag_id, keyword, tag_ids)
    crud.fill_audit_names_batch(db, objs)
    crud.fill_file_tag_ids(db, objs)
    return objs


@router.get("/{file_id}", response_model=schemas.FileOut)
def get_file_detail(
    file_id: int,
    db: Session = Depends(get_db),
    _user: models.User = Depends(get_current_user),
):
    obj = crud.get_file(db, file_id)
    if not obj:
        raise HTTPException(404, "文件不存在")
    crud.fill_audit_names(db, obj)
    crud.fill_file_tag_ids(db, [obj])
    return obj


# ============ 下载 / 预览 ============
@router.get("/{file_id}/download")
def download_file(
    file_id: int,
    db: Session = Depends(get_db),
    _user: models.User = Depends(get_current_user),
):
    """下载文件：返回原文件名"""
    obj = crud.get_file(db, file_id)
    if not obj:
        raise HTTPException(404, "文件不存在")
    physical = _resolve_physical_path(obj.storage_path)
    if not physical.exists():
        raise HTTPException(404, "物理文件已丢失")
    return FileResponse(
        path=str(physical),
        filename=obj.name,
        media_type=obj.content_type,
    )


@router.get("/{file_id}/preview")
def preview_file(
    file_id: int,
    db: Session = Depends(get_db),
    _user: models.User = Depends(get_current_user),
):
    """预览文件：图片/PDF 内嵌展示，其他类型返回 415 不支持"""
    obj = crud.get_file(db, file_id)
    if not obj:
        raise HTTPException(404, "文件不存在")
    if not _is_previewable(obj.content_type):
        raise HTTPException(415, f"不支持预览的类型：{obj.content_type}")
    physical = _resolve_physical_path(obj.storage_path)
    if not physical.exists():
        raise HTTPException(404, "物理文件已丢失")
    return FileResponse(
        path=str(physical),
        media_type=obj.content_type,
        filename=obj.name,
    )


# ============ 重命名 / 改分类 / 改标签 ============
@router.put("/{file_id}", response_model=schemas.FileOut)
def update_file(
    file_id: int,
    data: schemas.FileUpdateRequest,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    obj = crud.get_file(db, file_id)
    if not obj:
        raise HTTPException(404, "文件不存在")
    obj = crud.update_file(db, obj, data, user.id)
    crud.fill_audit_names(db, obj)
    crud.fill_file_tag_ids(db, [obj])
    crud.log_operation(db, user, "update", "file", obj.id, obj.name)
    return obj


# ============ 删除 ============
@router.delete("/{file_id}")
def delete_file(
    file_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    obj = crud.get_file(db, file_id)
    if not obj:
        raise HTTPException(404, "文件不存在")
    name = obj.name
    storage_path = obj.storage_path
    deleted_physical = crud.delete_file(db, obj)
    if deleted_physical:
        physical = _resolve_physical_path(storage_path)
        try:
            if physical.exists():
                physical.unlink()
        except Exception as e:
            print(f"[文件清理] 删除物理文件失败（忽略）: {e}")
    crud.log_operation(db, user, "delete", "file", file_id, name)
    return {"message": "已删除", "physical_removed": deleted_physical}


# ============ 文件分类 CRUD ============
category_router = APIRouter(prefix="/api/file-categories", tags=["文件中心"])


@category_router.get("", response_model=List[schemas.FileCategoryOut])
def list_categories(
    project_id: int = Query(...),
    db: Session = Depends(get_db),
    _user: models.User = Depends(get_current_user),
):
    objs = crud.list_file_categories(db, project_id)
    crud.fill_audit_names_batch(db, objs)
    return objs


@category_router.post("", response_model=schemas.FileCategoryOut)
def create_category(
    data: schemas.FileCategoryCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    obj = crud.create_file_category(db, data, user.id)
    crud.fill_audit_names(db, obj)
    crud.log_operation(db, user, "create", "file_category", obj.id, obj.name)
    return obj


@category_router.put("/{category_id}", response_model=schemas.FileCategoryOut)
def update_category(
    category_id: int,
    data: schemas.FileCategoryUpdate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    obj = crud.get_file_category(db, category_id)
    if not obj:
        raise HTTPException(404, "分类不存在")
    obj = crud.update_file_category(db, obj, data)
    crud.fill_audit_names(db, obj)
    crud.log_operation(db, user, "update", "file_category", obj.id, obj.name)
    return obj


@category_router.delete("/{category_id}")
def delete_category(
    category_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    obj = crud.get_file_category(db, category_id)
    if not obj:
        raise HTTPException(404, "分类不存在")
    crud.log_operation(db, user, "delete", "file_category", obj.id, obj.name)
    crud.delete_file_category(db, obj)
    return {"message": "已删除"}


# ============ 文件标签 CRUD ============
tag_router = APIRouter(prefix="/api/file-tags", tags=["文件中心"])


@tag_router.get("", response_model=List[schemas.FileTagOut])
def list_tags(
    project_id: int = Query(...),
    db: Session = Depends(get_db),
    _user: models.User = Depends(get_current_user),
):
    objs = crud.list_file_tags(db, project_id)
    crud.fill_audit_names_batch(db, objs)
    return objs


@tag_router.post("", response_model=schemas.FileTagOut)
def create_tag(
    data: schemas.FileTagCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    if crud.get_file_tag_by_name(db, data.project_id, data.name):
        raise HTTPException(400, f"标签已存在：{data.name}")
    obj = crud.create_file_tag(db, data, user.id)
    crud.fill_audit_names(db, obj)
    crud.log_operation(db, user, "create", "file_tag", obj.id, obj.name)
    return obj


@tag_router.put("/{tag_id}", response_model=schemas.FileTagOut)
def update_tag(
    tag_id: int,
    data: schemas.FileTagUpdate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    obj = crud.get_file_tag(db, tag_id)
    if not obj:
        raise HTTPException(404, "标签不存在")
    obj = crud.update_file_tag(db, obj, data)
    crud.fill_audit_names(db, obj)
    crud.log_operation(db, user, "update", "file_tag", obj.id, obj.name)
    return obj


@tag_router.delete("/{tag_id}")
def delete_tag(
    tag_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    obj = crud.get_file_tag(db, tag_id)
    if not obj:
        raise HTTPException(404, "标签不存在")
    crud.log_operation(db, user, "delete", "file_tag", obj.id, obj.name)
    crud.delete_file_tag(db, obj)
    return {"message": "已删除"}

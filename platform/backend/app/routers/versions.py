from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from .. import crud, schemas, models
from ..auth import get_current_user

router = APIRouter(tags=["项目版本"])


@router.post("/api/projects/{project_id}/versions", response_model=schemas.ProjectVersionOut)
def create_version(
    project_id: int,
    data: schemas.ProjectVersionCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """手动生成项目版本快照（接口+用例，不含环境）"""
    project = crud.get_project(db, project_id)
    if not project:
        raise HTTPException(404, "项目不存在")
    v = crud.create_project_version(db, project_id, data.name, data.description, user.id)
    crud.fill_version_audit_names(db, [v])
    crud.log_operation(db, user, "create", "project_version", v.id, f"{project.name} v{v.version_no}")
    return v


@router.get("/api/projects/{project_id}/versions")
def list_versions(
    project_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """项目版本列表（按版本号倒序，不含 snapshot 大字段以减小响应体积）"""
    project = crud.get_project(db, project_id)
    if not project:
        raise HTTPException(404, "项目不存在")
    versions = crud.list_project_versions(db, project_id)
    crud.fill_version_audit_names(db, versions)
    # 列表不返回 snapshot 大字段
    return [
        {
            "id": v.id,
            "project_id": v.project_id,
            "version_no": v.version_no,
            "name": v.name,
            "description": v.description,
            "created_by": v.created_by,
            "created_by_name": getattr(v, "created_by_name", None),
            "created_at": v.created_at,
        }
        for v in versions
    ]


@router.get("/api/project-versions/{version_id}", response_model=schemas.ProjectVersionOut)
def get_version(version_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    v = crud.get_project_version(db, version_id)
    if not v:
        raise HTTPException(404, "版本不存在")
    crud.fill_version_audit_names(db, [v])
    return v


@router.get("/api/project-versions/{version_id}/diff", response_model=schemas.ProjectVersionDiff)
def diff_version(
    version_id: int,
    target_id: int = Query(..., description="对比目标版本ID"),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """对比两个项目版本：返回各类资源的 added/removed/modified"""
    base = crud.get_project_version(db, version_id)
    if not base:
        raise HTTPException(404, "基础版本不存在")
    target = crud.get_project_version(db, target_id)
    if not target:
        raise HTTPException(404, "对比目标版本不存在")
    if base.project_id != target.project_id:
        raise HTTPException(400, "两个版本不属于同一项目，无法对比")
    crud.fill_version_audit_names(db, [base, target])
    diff = crud.diff_project_versions(base, target)
    return schemas.ProjectVersionDiff(base=base, target=target, diff=diff)


@router.post("/api/project-versions/{version_id}/rollback")
def rollback_version(version_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """硬回滚项目到指定版本：删当前所有接口/用例/分组，用快照重建。
    回滚前自动打一个"回滚前快照"留痕，确保可恢复。"""
    v = crud.get_project_version(db, version_id)
    if not v:
        raise HTTPException(404, "版本不存在")
    project = crud.get_project(db, v.project_id)
    if not project:
        raise HTTPException(404, "项目不存在")
    try:
        crud.rollback_project_version(db, project, v, user.id)
    except Exception as e:
        db.rollback()
        import traceback
        traceback.print_exc()
        raise HTTPException(500, f"回滚失败：{e}")
    crud.log_operation(db, user, "rollback", "project", project.id, f"回滚到 v{v.version_no}")
    return {"message": f"已回滚到 v{v.version_no}"}


@router.delete("/api/project-versions/{version_id}")
def delete_version(version_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    v = crud.get_project_version(db, version_id)
    if not v:
        raise HTTPException(404, "版本不存在")
    crud.delete_project_version(db, v)
    crud.log_operation(db, user, "delete", "project_version", v.id, f"v{v.version_no}")
    return {"message": "已删除"}

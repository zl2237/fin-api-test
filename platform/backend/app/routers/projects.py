from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import crud, models, schemas
from ..auth import get_current_user
from ..database import get_db

router = APIRouter(prefix="/api/projects", tags=["项目"])


@router.post("", response_model=schemas.ProjectOut)
def create(data: schemas.ProjectCreate, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    obj = crud.create_project(db, data, user.id)
    crud.fill_audit_names(db, obj)
    crud.log_operation(db, user, "create", "project", obj.id, obj.name)
    return obj


@router.get("", response_model=list[schemas.ProjectOut])
def list_all(created_by: int | None = None, updated_by: int | None = None, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    objs = crud.list_projects(db, created_by, updated_by)
    crud.fill_audit_names_batch(db, objs)
    return objs


@router.get("/{project_id}", response_model=schemas.ProjectOut)
def get_one(project_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    obj = crud.get_project(db, project_id)
    if not obj:
        raise HTTPException(404, "项目不存在")
    crud.fill_audit_names(db, obj)
    return obj


@router.put("/{project_id}", response_model=schemas.ProjectOut)
def update(project_id: int, data: schemas.ProjectUpdate, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    obj = crud.get_project(db, project_id)
    if not obj:
        raise HTTPException(404, "项目不存在")
    obj = crud.update_project(db, obj, data, user.id)
    crud.fill_audit_names(db, obj)
    crud.log_operation(db, user, "update", "project", obj.id, obj.name)
    return obj


@router.delete("/{project_id}")
def delete(project_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    obj = crud.get_project(db, project_id)
    if not obj:
        raise HTTPException(404, "项目不存在")
    crud.delete_project(db, obj)
    crud.log_operation(db, user, "delete", "project", obj.id, obj.name)
    return {"message": "已删除"}


@router.post("/reorder")
def reorder(data: schemas.ProjectReorderRequest, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    items = [{"id": it["id"], "sort_order": it["sort_order"]} for it in data.items]
    updated = crud.reorder_projects(db, items, user.id)
    return {"message": f"已更新 {updated} 个项目排序", "updated": updated}

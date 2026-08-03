from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from .. import crud, schemas, models
from ..auth import get_current_user

router = APIRouter(prefix="/api/testcases", tags=["用例"])

# 注意：分组路由单独前缀，避免和 /api/testcases/{case_id} 冲突
group_router = APIRouter(prefix="/api/case-groups", tags=["用例分组"])


# ============ 用例分组 ============
@group_router.post("", response_model=schemas.CaseGroupOut)
def create_group(data: schemas.CaseGroupCreate, db: Session = Depends(get_db)):
    obj = crud.create_case_group(db, data)
    crud.log_operation(db, None, "create", "case_group", obj.id, obj.name)
    return obj


@group_router.get("", response_model=list[schemas.CaseGroupOut])
def list_groups(project_id: int, db: Session = Depends(get_db)):
    return crud.list_case_groups(db, project_id)


@group_router.put("/{group_id}", response_model=schemas.CaseGroupOut)
def update_group(group_id: int, data: schemas.CaseGroupUpdate, db: Session = Depends(get_db)):
    obj = crud.get_case_group(db, group_id)
    if not obj:
        raise HTTPException(404, "用例分组不存在")
    obj = crud.update_case_group(db, obj, data)
    crud.log_operation(db, None, "update", "case_group", obj.id, obj.name)
    return obj


@group_router.delete("/{group_id}")
def delete_group(group_id: int, db: Session = Depends(get_db)):
    obj = crud.get_case_group(db, group_id)
    if not obj:
        raise HTTPException(404, "用例分组不存在")
    crud.delete_case_group(db, obj)
    crud.log_operation(db, None, "delete", "case_group", obj.id, obj.name)
    return {"message": "已删除"}


# ============ 用例 ============
@router.post("", response_model=schemas.TestCaseOut)
def create(data: schemas.TestCaseCreate, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    obj = crud.create_testcase(db, data, user.id)
    crud.fill_audit_names(db, obj)
    crud.log_operation(db, user, "create", "testcase", obj.id, obj.name)
    return obj


@router.get("", response_model=list[schemas.TestCaseOut])
def list_all(project_id: int | None = None, created_by: int | None = None, updated_by: int | None = None, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    objs = crud.list_testcases(db, project_id, created_by, updated_by)
    crud.fill_audit_names_batch(db, objs)
    return objs


@router.get("/{case_id}", response_model=schemas.TestCaseOut)
def get_one(case_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    obj = crud.get_testcase(db, case_id)
    if not obj:
        raise HTTPException(404, "用例不存在")
    crud.fill_audit_names(db, obj)
    return obj


@router.put("/{case_id}", response_model=schemas.TestCaseOut)
def update(case_id: int, data: schemas.TestCaseUpdate, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    obj = crud.get_testcase(db, case_id)
    if not obj:
        raise HTTPException(404, "用例不存在")
    obj = crud.update_testcase(db, obj, data, user.id)
    crud.fill_audit_names(db, obj)
    crud.log_operation(db, user, "update", "testcase", obj.id, obj.name)
    return obj


@router.delete("/{case_id}")
def delete(case_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    obj = crud.get_testcase(db, case_id)
    if not obj:
        raise HTTPException(404, "用例不存在")
    crud.delete_testcase(db, obj)
    crud.log_operation(db, user, "delete", "testcase", obj.id, obj.name)
    return {"message": "已删除"}


@router.post("/{case_id}/copy", response_model=schemas.TestCaseOut)
def copy(case_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    obj = crud.get_testcase(db, case_id)
    if not obj:
        raise HTTPException(404, "用例不存在")
    new_obj = crud.copy_testcase(db, obj)
    # 复制后标记新创建人
    new_obj.created_by = user.id
    new_obj.updated_by = user.id
    db.commit()
    db.refresh(new_obj)
    crud.fill_audit_names(db, new_obj)
    crud.log_operation(db, user, "copy", "testcase", new_obj.id, new_obj.name)
    return new_obj


@router.post("/batch-move")
def batch_move(data: schemas.CaseBatchMove, db: Session = Depends(get_db)):
    """批量移动用例到指定分组"""
    # 注意：此路由需在 /{case_id} 之前注册，否则会被 path 参数拦截
    updated = crud.batch_move_testcases(db, data.case_ids, data.group_id)
    crud.log_operation(db, None, "update", "testcase", None, f"批量移动{updated}个用例")
    return {"message": f"已移动 {updated} 个用例", "updated": updated}

"""字段字典路由：项目级英文字段名 → 中文含义映射，所有登录用户可编辑"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from .. import crud, schemas, models
from ..auth import get_current_user

router = APIRouter(prefix="/api/field-dictionaries", tags=["字段字典"])


@router.get("", response_model=list[schemas.FieldDictionaryOut])
def list_all(
    project_id: int,
    keyword: str | None = None,
    db: Session = Depends(get_db),
    _user: models.User = Depends(get_current_user),
):
    """查询指定项目的字段字典，支持按 key/label 关键词搜索"""
    objs = crud.list_field_dictionaries(db, project_id, keyword)
    crud.fill_audit_names_batch(db, objs)
    return objs


@router.get("/map")
def get_map(
    project_id: int,
    db: Session = Depends(get_db),
    _user: models.User = Depends(get_current_user),
):
    """返回 {key: label} 映射，供前端运行时查询"""
    return crud.get_field_dict_map(db, project_id)


@router.post("", response_model=schemas.FieldDictionaryOut)
def create(
    data: schemas.FieldDictionaryCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """新增字段字典条目"""
    if crud.get_field_dictionary_by_key(db, data.project_id, data.key):
        raise HTTPException(400, f"字段已存在: {data.key}")
    obj = crud.create_field_dictionary(db, data, user.id)
    crud.fill_audit_names(db, obj)
    crud.log_operation(db, user, "create", "field_dictionary", obj.id, obj.key)
    return obj


@router.post("/batch")
def batch_import(
    data: schemas.FieldDictionaryBatchIn,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """批量导入字段字典（覆盖式：同 key 更新 label，新 key 插入）

    请求体示例：
    {
      "project_id": 1,
      "items": [
        {"key": "order_id", "label": "订单ID"},
        {"key": "bl_no", "label": "提单号"}
      ]
    }
    """
    if not data.items:
        raise HTTPException(400, "导入列表不能为空")
    count = crud.batch_upsert_field_dictionaries(db, data.project_id, data.items, user.id)
    crud.log_operation(db, user, "batch_import", "field_dictionary", None, f"{count} items")
    return {"message": f"已导入 {count} 条字段字典", "count": count}


@router.put("/{dict_id}", response_model=schemas.FieldDictionaryOut)
def update(
    dict_id: int,
    data: schemas.FieldDictionaryUpdate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """更新字段字典条目"""
    obj = crud.get_field_dictionary(db, dict_id)
    if not obj:
        raise HTTPException(404, "字典条目不存在")
    # 若修改了 key，检查新 key 是否冲突
    if data.key and data.key != obj.key:
        if crud.get_field_dictionary_by_key(db, obj.project_id, data.key):
            raise HTTPException(400, f"字段已存在: {data.key}")
    obj = crud.update_field_dictionary(db, obj, data, user.id)
    crud.fill_audit_names(db, obj)
    crud.log_operation(db, user, "update", "field_dictionary", obj.id, obj.key)
    return obj


@router.delete("/{dict_id}")
def remove(
    dict_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """删除字段字典条目"""
    obj = crud.get_field_dictionary(db, dict_id)
    if not obj:
        raise HTTPException(404, "字典条目不存在")
    crud.log_operation(db, user, "delete", "field_dictionary", obj.id, obj.key)
    crud.delete_field_dictionary(db, obj)
    return {"message": "已删除"}

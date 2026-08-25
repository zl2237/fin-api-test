from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from .. import crud, models, schemas
from ..auth import get_current_user
from ..database import get_db

router = APIRouter(prefix="/api/testcases", tags=["用例"])

# 注意：分组路由单独前缀，避免和 /api/testcases/{case_id} 冲突
group_router = APIRouter(prefix="/api/case-groups", tags=["用例分组"])


# ============ 用例分组 ============
@group_router.post("", response_model=schemas.CaseGroupOut)
def create_group(data: schemas.CaseGroupCreate, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    obj = crud.create_case_group(db, data)
    crud.log_operation(db, user, "create", "case_group", obj.id, obj.name)
    return obj


@group_router.get("", response_model=list[schemas.CaseGroupOut])
def list_groups(project_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    return crud.list_case_groups(db, project_id)


@group_router.put("/{group_id}", response_model=schemas.CaseGroupOut)
def update_group(group_id: int, data: schemas.CaseGroupUpdate, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    obj = crud.get_case_group(db, group_id)
    if not obj:
        raise HTTPException(404, "用例分组不存在")
    obj = crud.update_case_group(db, obj, data)
    crud.log_operation(db, user, "update", "case_group", obj.id, obj.name)
    return obj


@group_router.delete("/{group_id}")
def delete_group(group_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    obj = crud.get_case_group(db, group_id)
    if not obj:
        raise HTTPException(404, "用例分组不存在")
    crud.delete_case_group(db, obj)
    crud.log_operation(db, user, "delete", "case_group", obj.id, obj.name)
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


@router.get("/export")
def export_list(
    project_id: int,
    format: str = "excel",
    created_by: int | None = None,
    updated_by: int | None = None,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """用例列表导出：Excel 简表或 JSON 全量（含 DAG 与节点配置），筛选条件与列表页一致。
    注意：此路由需在 /{case_id} 之前注册，否则 GET /export 会被 path 参数拦截。"""
    if format not in ("excel", "json"):
        raise HTTPException(400, "format 仅支持 excel / json")

    objs = crud.list_testcases(db, project_id, created_by, updated_by)
    if not objs:
        raise HTTPException(400, "当前筛选条件下没有可导出的用例")
    crud.fill_audit_names_batch(db, objs)

    groups = crud.list_case_groups(db, project_id) if project_id else []
    group_names = {g.id: g.name for g in groups}
    project = crud.get_project(db, project_id)
    project_name = project.name if project else ""
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    from ..services.export_service import export_cases_excel, export_cases_json
    if format == "json":
        content = export_cases_json(objs, group_names, project_name)
        crud.log_operation(db, user, "export", "testcase", None, f"导出{len(objs)}个用例（json）")
        return Response(
            content=content,
            media_type="application/json; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="cases_{stamp}.json"'},
        )
    content = export_cases_excel(objs, group_names)
    crud.log_operation(db, user, "export", "testcase", None, f"导出{len(objs)}个用例（excel）")
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="cases_{stamp}.xlsx"'},
    )


@router.post("/combine", response_model=schemas.TestCaseOut)
def combine(data: schemas.CaseCombineRequest, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """多用例组合：按 case_ids 顺序拼接为一个新的复制式用例，段间自动串接保证先后"""
    from ..services.case_combine_service import combine_cases
    try:
        obj = combine_cases(db, data.case_ids, data.name, data.group_id, user.id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    crud.log_operation(db, user, "combine", "testcase", obj.id, obj.name)
    return obj


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
    # 数据集绑定校验（显式传 dataset_id 时）：须存在且与用例同项目
    if "dataset_id" in data.model_fields_set:
        from ..services.dataset_service import validate_binding
        try:
            validate_binding(db, obj, data.dataset_id)
        except ValueError as e:
            raise HTTPException(400, str(e))
    obj = crud.update_testcase(db, obj, data, user.id)
    crud.fill_audit_names(db, obj)
    crud.log_operation(db, user, "update", "testcase", obj.id, obj.name)
    return obj


@router.delete("/{case_id}")
def delete(case_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    obj = crud.get_testcase(db, case_id)
    if not obj:
        raise HTTPException(404, "用例不存在")
    # 用例删除连带清理其定时任务（业务行 + 调度器 job），避免孤儿任务空转
    # 先移除 job（remove_by_case 需查业务行取 id），再删业务行
    from ..services.scheduler import scheduler_service
    scheduler_service.remove_by_case(case_id)
    db.query(models.TestSchedule).filter(models.TestSchedule.case_id == case_id).delete()
    db.commit()
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


@router.post("/{case_id}/scan-split")
def scan_split(case_id: int, data: schemas.CaseSplitRequest, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """拆分前置扫描：返回跨界变量清单，前端弹窗供用户确认后再执行拆分。
    outgoing = 被抽离节点提取、留驻节点引用（随迁后留驻方悬空）
    incoming = 留驻节点提取、被抽离节点引用（不随迁则新用例侧悬空）"""
    from ..services.case_combine_service import scan_split_boundary
    try:
        result = scan_split_boundary(db, case_id, data.node_ids)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {
        "node_ids": data.node_ids,
        "outgoing_count": len(result["outgoing"]),
        "incoming_count": len(result["incoming"]),
        **result,
    }


@router.post("/{case_id}/split")
def split(case_id: int, data: schemas.CaseSplitRequest, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """执行拆分：抽离节点 + 相关边 + 节点配置到新用例，原用例同步收缩。"""
    from ..services.case_combine_service import split_case
    try:
        new_case, updated = split_case(db, case_id, data.node_ids, data.new_name, data.new_group_id, user.id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    crud.log_operation(db, user, "split", "testcase", new_case.id, f"从 #{case_id} 拆分")
    return {
        "message": "拆分完成",
        "new_case": schemas.TestCaseOut.model_validate(new_case).model_dump(),
        "origin_case": schemas.TestCaseOut.model_validate(updated).model_dump(),
    }


@router.post("/batch-move")
def batch_move(data: schemas.CaseBatchMove, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """批量移动用例到指定分组"""
    # 注意：此路由需在 /{case_id} 之前注册，否则会被 path 参数拦截
    updated = crud.batch_move_testcases(db, data.case_ids, data.group_id)
    crud.log_operation(db, user, "update", "testcase", None, f"批量移动{updated}个用例")
    return {"message": f"已移动 {updated} 个用例", "updated": updated}


@router.post("/reorder")
def reorder(data: schemas.CaseReorderRequest, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """批量重排序用例（组内拖拽排序）"""
    # 注意：此路由需在 /{case_id} 之前注册，否则会被 path 参数拦截
    items = [{"id": it.id, "sort_order": it.sort_order} for it in data.items]
    updated = crud.reorder_testcases(db, items, user.id)
    return {"message": f"已更新 {updated} 个用例排序", "updated": updated}

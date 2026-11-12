from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from .. import crud, models, schemas
from ..auth import get_current_user
from ..database import get_db
from ..engine.validation import validate_post_extract_sql

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


@group_router.delete("/{group_id}", response_model=schemas.MessageOut)
def delete_group(group_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    obj = crud.get_case_group(db, group_id)
    if not obj:
        raise HTTPException(404, "用例分组不存在")
    try:
        crud.delete_case_group(db, obj)
    except ValueError as e:
        # 组非空时阻止删除（有子分组/有用例），前端提示用户先移走
        raise HTTPException(400, str(e))
    crud.log_operation(db, user, "delete", "case_group", obj.id, obj.name)
    return {"message": "已删除"}


# ============ 用例 ============
def _validate_case_env(db: Session, data) -> None:
    """环境严格绑定校验：显式传入 env_id 时须存在（创建/更新共用）"""
    if data.env_id is not None and not crud.get_environment(db, data.env_id):
        raise HTTPException(400, f"绑定的环境不存在: {data.env_id}")


def _validate_node_envs(db: Session, case, data) -> None:
    """节点级环境绑定校验（跨系统编排，2026-11-12）：env 须存在，且项目须与
    该节点绑定接口的项目一致（api 为空时与用例项目一致）——相对 path 拼错域
    会全数打偏，宁可在保存期拦下。"""
    node_configs = getattr(data, "node_configs", None) or []
    case_project = getattr(case, "project_id", None) if case is not None else getattr(data, "project_id", None)
    for nc in node_configs:
        if not getattr(nc, "env_id", None):
            continue
        env = crud.get_environment(db, nc.env_id)
        if not env:
            raise HTTPException(400, f"节点 {nc.node_id} 绑定的环境不存在: {nc.env_id}")
        if nc.api_id:
            api = crud.get_api(db, nc.api_id)
            api_project = api.project_id if api else None
        else:
            api_project = case_project
        if env.project_id != api_project:
            raise HTTPException(
                400, f"节点 {nc.node_id} 的环境「{env.name}」(项目 {env.project_id}) "
                     f"与接口所在项目 ({api_project}) 不一致——跨系统节点须绑定接口所属项目的环境")


@router.post("", response_model=schemas.TestCaseOut)
def create(data: schemas.TestCaseCreate, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    try:
        validate_post_extract_sql(getattr(data, "node_configs", None),
                                  getattr(data, "dag_config", None))
    except ValueError as e:
        raise HTTPException(400, str(e))
    _validate_case_env(db, data)
    _validate_node_envs(db, None, data)
    obj = crud.create_testcase(db, data, user.id)
    # 默认数据集自动初始化（Q7）：新用例自动建「默认数据集」（示例值）并置 bound
    from ..services.dataset_service import ensure_case_dataset
    ensure_case_dataset(db, obj, user.id)
    crud.fill_audit_names(db, obj)
    crud.fill_case_env_names(db, obj)
    crud.fill_involved_projects(db, [obj])
    crud.fill_bound_datasets(db, [obj])
    crud.log_operation(db, user, "create", "testcase", obj.id, obj.name)
    return obj


@router.get("", response_model=list[schemas.TestCaseOut])
def list_all(project_id: int | None = None, created_by: int | None = None, updated_by: int | None = None, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    objs = crud.list_testcases(db, project_id, created_by, updated_by)
    crud.fill_audit_names_batch(db, objs)
    crud.fill_case_env_names(db, objs)
    crud.fill_involved_projects(db, objs)  # 派生归属：跨系统用例在涉及项目下可见
    crud.fill_bound_datasets(db, objs)
    return objs


@router.get("/export")
def export_list(
    project_id: int,
    format: str = "excel",
    created_by: int | None = None,
    updated_by: int | None = None,
    case_ids: str | None = None,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """用例列表导出：Excel 简表或 JSON 全量（含 DAG 与节点配置）。
    列表页勾选了用例时传 case_ids（逗号分隔）只导勾选的；否则按筛选条件导全量。
    注意：此路由需在 /{case_id} 之前注册，否则 GET /export 会被 path 参数拦截。"""
    if format not in ("excel", "json"):
        raise HTTPException(400, "format 仅支持 excel / json")

    objs = crud.list_testcases(db, project_id, created_by, updated_by)
    selected = False
    if case_ids:
        try:
            wanted = {int(x) for x in case_ids.split(",") if x.strip()}
        except ValueError:
            raise HTTPException(400, "case_ids 格式非法（应为逗号分隔的用例ID）")
        objs = [c for c in objs if c.id in wanted]
        selected = True
    if not objs:
        raise HTTPException(400, "勾选的用例中没有可导出的用例" if selected else "当前筛选条件下没有可导出的用例")
    crud.fill_audit_names_batch(db, objs)
    crud.fill_case_env_names(db, objs)

    groups = crud.list_case_groups(db, project_id) if project_id else []
    group_names = {g.id: g.name for g in groups}
    project = crud.get_project(db, project_id)
    project_name = project.name if project else ""
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    from ..services.export_service import export_cases_excel, export_cases_json
    if format == "json":
        # 数据集入参配置随用例全量导出（备份完整性）
        exported_ids = [c.id for c in objs]
        dss = (db.query(models.DataSet)
               .filter(models.DataSet.case_id.in_(exported_ids))
               .order_by(models.DataSet.id).all()) if exported_ids else []
        datasets_by_case: dict[int, list] = {}
        for d in dss:
            if d.rows:
                datasets_by_case.setdefault(d.case_id, []).append(d)
        content = export_cases_json(objs, group_names, project_name, datasets_by_case, db=db)
        crud.log_operation(db, user, "export", "testcase", None, f"导出{len(objs)}个用例（json{'，选中' if selected else ''}）")
        return Response(
            content=content,
            media_type="application/json; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="cases_{stamp}.json"'},
        )
    content = export_cases_excel(objs, group_names)
    crud.log_operation(db, user, "export", "testcase", None, f"导出{len(objs)}个用例（excel{'，选中' if selected else ''}）")
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="cases_{stamp}.xlsx"'},
    )


@router.post("/import")
def import_cases(data: schemas.CaseImportRequest, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """用例导入（导出 v2 迁移包）：dry_run 先预演（接口复用/新建统计），确认后整批重建。
    注意：此路由需在 /{case_id} 之前注册（同 /export，避免被 path 参数拦截）。"""
    from ..services.case_import_service import ImportPayloadError, import_cases as do_import
    try:
        result = do_import(db, data.payload, data.project_id, user.id,
                           group_id=data.group_id, env_id=data.env_id, dry_run=data.dry_run)
    except ImportPayloadError as e:
        raise HTTPException(400, str(e))
    crud.log_operation(db, user, "import", "testcase", None,
                       f"导入{'预演 ' if data.dry_run else ''}{result['case_count']} 个用例")
    return result


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
    crud.fill_case_env_names(db, obj)
    crud.fill_involved_projects(db, [obj])
    crud.fill_bound_datasets(db, [obj])
    return obj


@router.put("/{case_id}", response_model=schemas.TestCaseOut)
def update(case_id: int, data: schemas.TestCaseUpdate, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    obj = crud.get_testcase(db, case_id)
    if not obj:
        raise HTTPException(404, "用例不存在")
    # 执行中的用例禁止改编排：运行线程读库内配置，保存会串版本
    from ..crud.executions import ensure_case_not_running
    try:
        ensure_case_not_running(db, case_id, "保存用例")
    except ValueError as e:
        raise HTTPException(409, str(e))
    # 后置提取 SQL 基本校验（关键字粘连/缺失——静默坏 SQL 运行时只会在报告里表现为提取为空）
    try:
        validate_post_extract_sql(getattr(data, "node_configs", None),
                                  getattr(data, "dag_config", None))
    except ValueError as e:
        raise HTTPException(400, str(e))
    # 环境严格绑定：显式改绑时校验存在（普通用例须绑定环境才能执行，编辑入口必填）
    if "env_id" in data.model_fields_set:
        _validate_case_env(db, data)
    # 跨系统编排：节点级环境绑定校验（env 与接口项目一致性）
    _validate_node_envs(db, obj, data)
    obj = crud.update_testcase(db, obj, data, user.id)
    # 默认数据集初始化/增量（Q7）：无 bound 数据集时自动建+绑定；有 bound 时补画布
    # 新增节点的初始参数（示例值）。数据集绑定改走 PUT /{case_id}/dataset-binding
    from ..services.dataset_service import ensure_case_dataset
    ensure_case_dataset(db, obj, user.id)
    crud.fill_audit_names(db, obj)
    crud.fill_case_env_names(db, obj)
    crud.fill_involved_projects(db, [obj])
    crud.fill_bound_datasets(db, [obj])
    crud.log_operation(db, user, "update", "testcase", obj.id, obj.name)
    return obj


@router.put("/{case_id}/dataset-binding", response_model=schemas.TestCaseOut)
def set_dataset_binding(case_id: int, data: schemas.DatasetBindingIn,
                        db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """用例绑定数据集（多选整体替换，2026-11-12 B3 定案）。

    dataset_ids 列表内的置 bound，其余本用例数据集解绑；空列表 = 全部解绑。
    执行强绑定：全部解绑后用例不可执行（保存不自动重建，与旧 dataset_id 语义一致）。
    """
    obj = crud.get_testcase(db, case_id)
    if not obj:
        raise HTTPException(404, "用例不存在")
    from ..crud.executions import ensure_case_not_running
    try:
        ensure_case_not_running(db, case_id, "绑定数据集")
    except ValueError as e:
        raise HTTPException(409, str(e))
    from ..services.dataset_service import set_case_binding
    try:
        bound = set_case_binding(db, obj, data.dataset_ids)
    except ValueError as e:
        raise HTTPException(400, str(e))
    crud.fill_audit_names(db, obj)
    crud.fill_case_env_names(db, obj)
    crud.fill_involved_projects(db, [obj])
    crud.fill_bound_datasets(db, [obj])
    crud.log_operation(db, user, "update", "testcase", obj.id,
                       f"绑定数据集 ×{len(bound)}")
    return obj


@router.put("/{case_id}/nodes/{node_id}/contract-template", response_model=schemas.MessageOut)
def bind_node_contract_template(case_id: int, node_id: str, data: schemas.NodeTemplateBindIn,
                                db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """节点级契约模板绑定（画布抽屉/数据集节点页共用；null = 解绑回全量口径）。

    模板须属于该节点绑定的接口（防跨接口错绑）；仅改结构层一列，不触碰数据集参数。
    """
    obj = crud.get_testcase(db, case_id)
    if not obj:
        raise HTTPException(404, "用例不存在")
    from ..crud.executions import ensure_case_not_running
    try:
        ensure_case_not_running(db, case_id, "绑定契约模板")
    except ValueError as e:
        raise HTTPException(409, str(e))
    cfg = (db.query(models.CaseNodeConfig)
           .filter(models.CaseNodeConfig.case_id == case_id,
                   models.CaseNodeConfig.node_id == node_id).first())
    if not cfg:
        raise HTTPException(404, f"节点 {node_id} 无配置行（先在编排中保存该节点）")
    tpl_name = "（解绑）"
    if data.template_id is not None:
        tpl = (db.query(models.ApiContractTemplate)
               .filter(models.ApiContractTemplate.id == data.template_id).first())
        if not tpl:
            raise HTTPException(404, "契约模板不存在")
        if cfg.api_id is None or tpl.api_id != cfg.api_id:
            raise HTTPException(400, f"模板「{tpl.name}」不属于该节点绑定的接口")
        tpl_name = f"「{tpl.name}」"
    cfg.contract_template_id = data.template_id
    db.commit()
    crud.log_operation(db, user, "update", "testcase", case_id,
                       f"节点 {node_id} 契约模板绑定 → {tpl_name}")
    return {"message": f"节点契约模板已更新为 {tpl_name}"}


@router.delete("/{case_id}", response_model=schemas.MessageOut)
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
    crud.fill_case_env_names(db, new_obj)
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
    if not data.new_name:
        raise HTTPException(400, "新用例名不能为空")
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


@router.post("/batch-move", response_model=schemas.ReorderResultOut)
def batch_move(data: schemas.CaseBatchMove, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """批量移动用例到指定分组"""
    # 注意：此路由需在 /{case_id} 之前注册，否则会被 path 参数拦截
    updated = crud.batch_move_testcases(db, data.case_ids, data.group_id)
    crud.log_operation(db, user, "update", "testcase", None, f"批量移动{updated}个用例")
    return {"message": f"已移动 {updated} 个用例", "updated": updated}


@router.post("/reorder", response_model=schemas.ReorderResultOut)
def reorder(data: schemas.CaseReorderRequest, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """批量重排序用例（组内拖拽排序）"""
    # 注意：此路由需在 /{case_id} 之前注册，否则会被 path 参数拦截
    items = [{"id": it.id, "sort_order": it.sort_order} for it in data.items]
    updated = crud.reorder_testcases(db, items, user.id)
    return {"message": f"已更新 {updated} 个用例排序", "updated": updated}

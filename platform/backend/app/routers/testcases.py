from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from .. import crud, models, schemas
from ..auth import get_current_user
from ..database import get_db

router = APIRouter(prefix="/api/testcases", tags=["用例"])

# 注意：分组路由单独前缀，避免和 /api/testcases/{case_id} 冲突
group_router = APIRouter(prefix="/api/case-groups", tags=["用例分组"])


# ============ 后置提取 SQL 基本校验 ============
# 目标是拦截"肉眼难察、运行时静默失败"的低级笔误（提取结果为空、报告里查不到原因）：
# - 列名与关键字粘连（pay_invoice_apply_idfrom —— FROM 非独立词，TiDB 直接语法错误）
# - SELECT 缺 FROM / 语句不以 SQL 关键字开头
# ${} 变量先替换为占位字面量再扫描（避免 ${x}from 这类表达式写法误判）
import re  # noqa: E402

_SQL_START_RE = re.compile(r"^\s*(select|insert|update|delete|show|with|desc)\b", re.I)
# 关键字前紧贴字母/数字（无空格/括号/下划线分隔）→ 粘连。只收长关键字，避免 in/is/as/on/set
# 这类常见子串（login/visit）误报；下划线连接的合法列名（user_group/group_id）不命中
# （下划线属标识符连接，不算粘连；\b 在 group_id 的 _g 处也不成立）
_SQL_GLUED_RE = re.compile(
    r"[A-Za-z0-9](?:from|where|select|insert|update|delete|values|into|order|group|limit|"
    r"having|between|union|distinct|inner|outer)\b", re.I)


def validate_post_extract_sql(node_configs: list | None) -> None:
    """编排保存入口：校验各节点 post_extract 中 source=db 的 SQL 基本形态。"""
    if not node_configs:
        return
    for nc in node_configs:
        node_id = (nc or {}).get("node_id") or "?"
        for rule in (nc or {}).get("post_extract") or []:
            if not isinstance(rule, dict) or rule.get("source") != "db":
                continue
            sql = str(rule.get("sql") or "").strip()
            if not sql:
                continue
            name = rule.get("name") or "?"
            # ${xxx} → 占位（防表达式内容干扰词法扫描）
            scanned = re.sub(r"\$\{[^{}]*\}", "1", sql)
            if not _SQL_START_RE.match(scanned):
                raise ValueError(
                    f"节点 {node_id} 后置提取「{name}」的 SQL 未以 SELECT/UPDATE/DELETE 等关键字开头，请检查")
            m = _SQL_GLUED_RE.search(scanned)
            if m:
                frag = m.group(0)
                raise ValueError(
                    f"节点 {node_id} 后置提取「{name}」的 SQL 疑似标识符与关键字粘连"
                    f"（…{frag}…，缺少空格），请检查：{sql[:120]}")
            if scanned.lstrip()[:6].lower() == "select" and not re.search(r"\bfrom\b", scanned, re.I):
                raise ValueError(
                    f"节点 {node_id} 后置提取「{name}」的 SELECT 缺少 FROM（可能列名与 FROM 粘连），请检查：{sql[:120]}")



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
    try:
        crud.delete_case_group(db, obj)
    except ValueError as e:
        # 组非空时阻止删除（有子分组/有用例），前端提示用户先移走
        raise HTTPException(400, str(e))
    crud.log_operation(db, user, "delete", "case_group", obj.id, obj.name)
    return {"message": "已删除"}


# ============ 用例 ============
@router.post("", response_model=schemas.TestCaseOut)
def create(data: schemas.TestCaseCreate, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    try:
        validate_post_extract_sql(getattr(data, "node_configs", None))
    except ValueError as e:
        raise HTTPException(400, str(e))
    obj = crud.create_testcase(db, data, user.id)
    # 变量池收集钩子：静态入参拆叶入池 + 清空转引用（失败不阻断保存，编排字面量仍在）
    from ..services.dataset_service import sync_case_variable_pool
    try:
        sync_case_variable_pool(db, obj, user.id)
    except Exception as e:
        print(f"[保存用例] 变量池收集失败（忽略）: {e}")
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
    # 执行中的用例禁止改编排：运行线程读库内配置，保存会串版本
    from ..crud.executions import ensure_case_not_running
    try:
        ensure_case_not_running(db, case_id, "保存用例")
    except ValueError as e:
        raise HTTPException(409, str(e))
    # 后置提取 SQL 基本校验（关键字粘连/缺失——静默坏 SQL 运行时只会在报告里表现为提取为空）
    try:
        validate_post_extract_sql(getattr(data, "node_configs", None))
    except ValueError as e:
        raise HTTPException(400, str(e))
    # 数据集绑定校验（显式传 dataset_id 时）：须存在且与用例同项目
    if "dataset_id" in data.model_fields_set:
        from ..services.dataset_service import validate_binding
        try:
            validate_binding(db, obj, data.dataset_id)
        except ValueError as e:
            raise HTTPException(400, str(e))
    obj = crud.update_testcase(db, obj, data, user.id)
    # 变量池收集钩子：静态入参拆叶入池 + 清空转引用（失败不阻断保存，编排字面量仍在）。
    # 显式解绑（dataset_id 显式传 null）时跳过自动复用绑定，保留用户解绑意图
    from ..services.dataset_service import sync_case_variable_pool
    try:
        sync_case_variable_pool(
            db, obj, user.id,
            unbind="dataset_id" in data.model_fields_set and data.dataset_id is None,
        )
    except Exception as e:
        print(f"[保存用例] 变量池收集失败（忽略）: {e}")
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


# ============ 套件成员（case_type=suite 专用） ============
def _member_out(db: Session, m: models.SuiteMember) -> schemas.SuiteMemberOut:
    """ORM 成员行 → 带 用例名/项目/环境名 的展示 DTO（引用悬空时名称置空不炸）"""
    out = schemas.SuiteMemberOut(
        id=m.id, member_case_id=m.member_case_id, env_id=m.env_id,
        sort_order=m.sort_order)
    mc = crud.get_testcase(db, m.member_case_id)
    if mc:
        out.case_name = mc.name
        out.project_id = mc.project_id
        assert mc.project_id is not None  # 用例必然属于某项目
        project = crud.get_project(db, mc.project_id)
        out.project_name = project.name if project else None
        out.member_case_type = getattr(mc, "case_type", "normal")
    env = crud.get_environment(db, m.env_id)
    out.env_name = env.name if env else None
    return out


@router.get("/{case_id}/members", response_model=list[schemas.SuiteMemberOut])
def list_members(case_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """套件成员列表（按执行顺序），带用例/项目/环境冗余名"""
    case = crud.get_testcase(db, case_id)
    if not case:
        raise HTTPException(404, "用例不存在")
    members = (db.query(models.SuiteMember)
               .filter(models.SuiteMember.suite_case_id == case_id)
               .order_by(models.SuiteMember.sort_order, models.SuiteMember.id).all())
    return [_member_out(db, m) for m in members]


@router.put("/{case_id}/members", response_model=list[schemas.SuiteMemberOut])
def replace_members(case_id: int, data: schemas.SuiteMembersUpdate,
                    db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """整体替换套件成员（编排保存语义）。校验：宿主是套件、成员存在且非套件（禁嵌套）、
    环境存在、不得引用自身；sort_order 按提交顺序重排（0 起）。"""
    case = crud.get_testcase(db, case_id)
    if not case:
        raise HTTPException(404, "用例不存在")
    if getattr(case, "case_type", "normal") != "suite":
        raise HTTPException(400, "只有套件类型的用例才能配置成员")
    for item in data.members:
        if item.member_case_id == case_id:
            raise HTTPException(400, "套件成员不能引用套件自身")
        mc = crud.get_testcase(db, item.member_case_id)
        if not mc:
            raise HTTPException(400, f"成员用例不存在: {item.member_case_id}")
        if getattr(mc, "case_type", "normal") == "suite":
            raise HTTPException(400, f"套件不能嵌套套件：{mc.name}")
        if not crud.get_environment(db, item.env_id):
            raise HTTPException(400, f"成员 {mc.name} 绑定的环境不存在: {item.env_id}")
    db.query(models.SuiteMember).filter(models.SuiteMember.suite_case_id == case_id).delete()
    for idx, item in enumerate(data.members):
        db.add(models.SuiteMember(suite_case_id=case_id, member_case_id=item.member_case_id,
                                  env_id=item.env_id, sort_order=idx))
    db.commit()
    crud.log_operation(db, user, "update", "testcase", case_id,
                       f"套件成员保存（{len(data.members)} 个）")
    members = (db.query(models.SuiteMember)
               .filter(models.SuiteMember.suite_case_id == case_id)
               .order_by(models.SuiteMember.sort_order, models.SuiteMember.id).all())
    return [_member_out(db, m) for m in members]


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

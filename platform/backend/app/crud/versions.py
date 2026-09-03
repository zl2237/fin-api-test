"""项目版本域：快照（snapshot）/ 对比（diff）/ 回滚（rollback）。

从 legacy.py 整族迁出（迁移策略见 crud/__init__.py）——回滚是高风险机制
（删当前全部接口/用例/分组后按快照重建，执行记录分离再重关联），独立成域
后本文件内自洽可读，可在此用假 Session 补测试。对外接口经 crud 包显式
re-export，旧引用 `crud.rollback_project_version` 等继续可用。
"""
from sqlalchemy.orm import Session

from .. import models
from .legacy import get_user_name_map

# ============ 快照构建 ============
def _snapshot_api_groups(db: Session, project_id: int) -> list[dict]:
    rows = db.query(models.ApiGroup).filter(models.ApiGroup.project_id == project_id)\
        .order_by(models.ApiGroup.sort_order, models.ApiGroup.id).all()
    return [{"id": g.id, "parent_id": g.parent_id, "name": g.name, "sort_order": g.sort_order} for g in rows]


def _snapshot_case_groups(db: Session, project_id: int) -> list[dict]:
    rows = db.query(models.CaseGroup).filter(models.CaseGroup.project_id == project_id)\
        .order_by(models.CaseGroup.sort_order, models.CaseGroup.id).all()
    return [{"id": g.id, "parent_id": g.parent_id, "name": g.name, "sort_order": g.sort_order} for g in rows]


def _snapshot_apis(db: Session, project_id: int) -> list[dict]:
    apis = db.query(models.ApiDefinition).filter(models.ApiDefinition.project_id == project_id)\
        .order_by(models.ApiDefinition.sort_order, models.ApiDefinition.id).all()
    result = []
    for a in apis:
        result.append({
            "id": a.id,
            "group_id": a.group_id,
            "name": a.name,
            "code": a.code,
            "category": a.category,
            "method": a.method,
            "path": a.path,
            "description": a.description,
            "request_template": a.request_template if a.request_template is not None else {},
            "headers_template": a.headers_template or {},
            "sort_order": a.sort_order,
            "fields": [
                {
                    "key": f.key, "label": f.label, "field_type": f.field_type,
                    "required": f.required, "default_value": f.default_value,
                    "remark": f.remark, "sort_order": f.sort_order,
                } for f in (a.fields or [])
            ],
        })
    return result


def _snapshot_cases(db: Session, project_id: int) -> list[dict]:
    cases = db.query(models.TestCase).filter(models.TestCase.project_id == project_id)\
        .order_by(models.TestCase.sort_order, models.TestCase.id).all()
    result = []
    for c in cases:
        result.append({
            "id": c.id,
            "group_id": c.group_id,
            "name": c.name,
            "description": c.description,
            "dag_config": c.dag_config or {"nodes": [], "edges": []},
            "sort_order": c.sort_order,
            "node_configs": [
                {
                    "node_id": nc.node_id, "api_id": nc.api_id,
                    "pre_process": nc.pre_process or [],
                    "post_extract": nc.post_extract or [],
                    "assertions": nc.assertions or [],
                    "wait_after_ms": nc.wait_after_ms or 0,
                } for nc in (c.node_configs or [])
            ],
        })
    return result


def _next_project_version_no(db: Session, project_id: int) -> int:
    latest = (
        db.query(models.ProjectVersion.version_no)
        .filter(models.ProjectVersion.project_id == project_id)
        .order_by(models.ProjectVersion.version_no.desc())
        .first()
    )
    return (latest[0] + 1) if latest else 1


def build_project_snapshot(db: Session, project_id: int) -> dict:
    """构建项目完整快照（接口分组/用例分组/接口+字段/用例+节点配置），不含环境"""
    return {
        "api_groups": _snapshot_api_groups(db, project_id),
        "case_groups": _snapshot_case_groups(db, project_id),
        "apis": _snapshot_apis(db, project_id),
        "cases": _snapshot_cases(db, project_id),
    }


def create_project_version(
    db: Session,
    project_id: int,
    name: str,
    description: str | None,
    user_id: int | None = None,
) -> models.ProjectVersion:
    """手动生成项目版本快照（version_no 自增）"""
    v = models.ProjectVersion(
        project_id=project_id,
        version_no=_next_project_version_no(db, project_id),
        name=name,
        description=description,
        snapshot=build_project_snapshot(db, project_id),
        created_by=user_id,
    )
    db.add(v)
    db.commit()
    db.refresh(v)
    return v


def list_project_versions(db: Session, project_id: int) -> list[models.ProjectVersion]:
    return (
        db.query(models.ProjectVersion)
        .filter(models.ProjectVersion.project_id == project_id)
        .order_by(models.ProjectVersion.version_no.desc())
        .all()
    )


def get_project_version(db: Session, version_id: int) -> models.ProjectVersion | None:
    return db.query(models.ProjectVersion).filter(models.ProjectVersion.id == version_id).first()


def fill_version_audit_names(db: Session, versions: list) -> None:
    """批量给 ProjectVersion 填充 created_by_name"""
    if not versions:
        return
    ids = {v.created_by for v in versions if v.created_by is not None}
    name_map = get_user_name_map(db, ids)
    for v in versions:
        v.created_by_name = name_map.get(v.created_by)


# ============ 版本对比 ============
def _diff_collection(base: list[dict], target: list[dict], key: str) -> dict:
    """对比两组快照列表，返回 added/removed/modified。
    匹配键：apis 用 code，cases/groups 用 name。modified 项附带字段级 diff。"""
    base_map = {item[key]: item for item in base}
    target_map = {item[key]: item for item in target}
    added = []
    removed = []
    modified = []
    for k, t in target_map.items():
        if k not in base_map:
            added.append({"key": k, "target": t})
        else:
            b = base_map[k]
            # 排除 id/group_id 等不稳定字段后对比内容
            b_cmp = {kk: vv for kk, vv in b.items() if kk != "id"}
            t_cmp = {kk: vv for kk, vv in t.items() if kk != "id"}
            if b_cmp != t_cmp:
                modified.append({"key": k, "base": b, "target": t})
    for k, b in base_map.items():
        if k not in target_map:
            removed.append({"key": k, "base": b})
    return {"added": added, "removed": removed, "modified": modified}


def diff_project_versions(base: models.ProjectVersion, target: models.ProjectVersion) -> dict:
    """对比两个项目版本快照，返回各类资源的 added/removed/modified"""
    b = base.snapshot or {}
    t = target.snapshot or {}
    return {
        "api_groups": _diff_collection(b.get("api_groups", []), t.get("api_groups", []), "name"),
        "case_groups": _diff_collection(b.get("case_groups", []), t.get("case_groups", []), "name"),
        "apis": _diff_collection(b.get("apis", []), t.get("apis", []), "code"),
        "cases": _diff_collection(b.get("cases", []), t.get("cases", []), "name"),
    }


# ============ 回滚（高风险：删当前全部接口/用例/分组后按快照重建） ============
def rollback_project_version(
    db: Session,
    project: models.Project,
    version: models.ProjectVersion,
    user_id: int | None = None,
) -> None:
    """硬回滚项目到指定版本：删当前所有接口/用例/分组，用快照重建。
    回滚前会自动打一个"回滚前快照"留痕，确保可恢复。"""
    # 1. 回滚前留痕
    create_project_version(
        db, project.id,
        name=f"回滚前自动快照 v{version.version_no}",
        description=f"回滚到 v{version.version_no} 前的自动留痕",
        user_id=user_id,
    )

    snap = version.snapshot or {}

    # 2. 分离执行记录（不删除，回滚后重新关联到新用例）+ 删除其他数据
    # 执行记录含 steps/assertions 子表，直接删除会导致回滚后历史执行记录丢失，
    # 改为：先分离（case_id 置空），重建用例后再按 old_case_id → new_case_id 重新关联
    case_ids = [c.id for c in db.query(models.TestCase).filter(models.TestCase.project_id == project.id).all()]
    exec_case_map: dict = {}  # exec_id → old_case_id
    if case_ids:
        execs = db.query(models.ExecutionRecord).filter(models.ExecutionRecord.case_id.in_(case_ids)).all()
        for e in execs:
            exec_case_map[e.id] = e.case_id
        # 分离执行记录，避免删除用例时外键约束冲突
        db.query(models.ExecutionRecord).filter(models.ExecutionRecord.case_id.in_(case_ids)).update(
            {models.ExecutionRecord.case_id: None}, synchronize_session=False
        )
        # CaseNodeConfig 属于用例配置，需随用例一起从快照重建
        db.query(models.CaseNodeConfig).filter(models.CaseNodeConfig.case_id.in_(case_ids)).delete(synchronize_session=False)

    api_ids = [a.id for a in db.query(models.ApiDefinition).filter(models.ApiDefinition.project_id == project.id).all()]
    if api_ids:
        db.query(models.ApiField).filter(models.ApiField.api_id.in_(api_ids)).delete(synchronize_session=False)

    db.query(models.TestCase).filter(models.TestCase.project_id == project.id).delete(synchronize_session=False)
    db.query(models.ApiDefinition).filter(models.ApiDefinition.project_id == project.id).delete(synchronize_session=False)
    # 分组有自引用外键(parent_id)，批量删除前先置空 parent_id 避免约束冲突
    db.query(models.CaseGroup).filter(models.CaseGroup.project_id == project.id).update({models.CaseGroup.parent_id: None}, synchronize_session=False)
    db.query(models.ApiGroup).filter(models.ApiGroup.project_id == project.id).update({models.ApiGroup.parent_id: None}, synchronize_session=False)
    db.query(models.CaseGroup).filter(models.CaseGroup.project_id == project.id).delete(synchronize_session=False)
    db.query(models.ApiGroup).filter(models.ApiGroup.project_id == project.id).delete(synchronize_session=False)
    # 不在此处 commit：让删除+重建+重新关联执行记录在同一事务中完成，
    # 若重建失败可整体回滚，避免执行记录 case_id 被永久置空

    # 3. 重建分组（建立 old_id -> new_id 映射；parent_id 在全部分组创建后回填）
    api_group_map: dict = {}
    api_group_rows: list = []
    for g in snap.get("api_groups", []):
        old_id = g.get("id")
        ng = models.ApiGroup(project_id=project.id, name=g["name"], sort_order=g.get("sort_order", 0))
        db.add(ng)
        db.flush()
        if old_id is not None:
            api_group_map[old_id] = ng.id
        api_group_rows.append((ng, g.get("parent_id")))

    # 回填 parent_id（old_parent_id → new_parent_id）
    for ng, old_parent_id in api_group_rows:
        if old_parent_id is not None and old_parent_id in api_group_map:
            ng.parent_id = api_group_map[old_parent_id]
    db.flush()

    case_group_map: dict = {}
    case_group_rows: list = []
    for g in snap.get("case_groups", []):
        old_id = g.get("id")
        ng = models.CaseGroup(project_id=project.id, name=g["name"], sort_order=g.get("sort_order", 0))
        db.add(ng)
        db.flush()
        if old_id is not None:
            case_group_map[old_id] = ng.id
        case_group_rows.append((ng, g.get("parent_id")))

    for ng, old_parent_id in case_group_rows:
        if old_parent_id is not None and old_parent_id in case_group_map:
            ng.parent_id = case_group_map[old_parent_id]
    db.flush()

    # 4. 重建接口（建立 old_api_id -> new_api_id 映射，转换 group_id）
    api_id_map: dict = {}
    for a in snap.get("apis", []):
        old_id = a.get("id")
        old_group_id = a.get("group_id")
        new_group_id = api_group_map.get(old_group_id) if old_group_id else None
        na = models.ApiDefinition(
            project_id=project.id,
            group_id=new_group_id,
            name=a["name"],
            code=a["code"],
            category=a.get("category"),
            method=a.get("method", "POST"),
            path=a["path"],
            description=a.get("description"),
            request_template=a.get("request_template", {}),
            headers_template=a.get("headers_template", {}),
            sort_order=a.get("sort_order", 0),
            created_by=user_id,
            updated_by=user_id,
        )
        db.add(na)
        db.flush()
        if old_id is not None:
            api_id_map[old_id] = na.id
        # 重建字段
        for f in a.get("fields", []):
            db.add(models.ApiField(
                api_id=na.id,
                key=f["key"],
                label=f.get("label"),
                field_type=f.get("field_type", "string"),
                required=f.get("required", False),
                default_value=f.get("default_value"),
                remark=f.get("remark"),
                sort_order=f.get("sort_order", 0),
            ))

    # 5. 重建用例（转换 group_id，node_configs 的 api_id 用映射转换）
    # 同时建立 old_case_id → new_case_id 映射，用于重新关联执行记录
    case_id_map: dict = {}
    for c in snap.get("cases", []):
        old_case_id = c.get("id")
        old_group_id = c.get("group_id")
        new_group_id = case_group_map.get(old_group_id) if old_group_id else None
        nc = models.TestCase(
            project_id=project.id,
            group_id=new_group_id,
            name=c["name"],
            description=c.get("description"),
            dag_config=c.get("dag_config", {"nodes": [], "edges": []}),
            sort_order=c.get("sort_order", 0),
            created_by=user_id,
            updated_by=user_id,
        )
        db.add(nc)
        db.flush()
        if old_case_id is not None:
            case_id_map[old_case_id] = nc.id
        for cfg in c.get("node_configs", []):
            old_api_id = cfg.get("api_id")
            new_api_id = api_id_map.get(old_api_id) if old_api_id else None
            db.add(models.CaseNodeConfig(
                case_id=nc.id,
                node_id=cfg["node_id"],
                api_id=new_api_id,
                pre_process=cfg.get("pre_process", []),
                post_extract=cfg.get("post_extract", []),
                assertions=cfg.get("assertions", []),
                wait_after_ms=cfg.get("wait_after_ms", 0) or 0,
            ))

    # 6. 重新关联执行记录到新用例
    # 快照中存在的用例：更新 case_id 到新 ID；不在快照中的用例（快照后新建）：删除其执行记录及子表
    for exec_id, old_cid in exec_case_map.items():
        new_cid = case_id_map.get(old_cid)
        if new_cid is not None:
            db.query(models.ExecutionRecord).filter(models.ExecutionRecord.id == exec_id).update(
                {models.ExecutionRecord.case_id: new_cid}, synchronize_session=False
            )
        else:
            # 用例不在快照中，清理其执行记录及子表
            step_ids = [s.id for s in db.query(models.StepRecord).filter(models.StepRecord.execution_id == exec_id).all()]
            if step_ids:
                db.query(models.AssertionRecord).filter(models.AssertionRecord.step_id.in_(step_ids)).delete(synchronize_session=False)
            db.query(models.StepRecord).filter(models.StepRecord.execution_id == exec_id).delete(synchronize_session=False)
            db.query(models.ExecutionRecord).filter(models.ExecutionRecord.id == exec_id).delete(synchronize_session=False)

    db.commit()


def delete_project_version(db: Session, version: models.ProjectVersion):
    db.delete(version)
    db.commit()

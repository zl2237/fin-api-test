"""数据库 CRUD 操作"""
from datetime import datetime
from typing import List, Optional, Type, TypeVar
from sqlalchemy.orm import Session

from . import models, schemas

T = TypeVar("T")


# ============ 用户名批量查询（审计字段填充） ============
def get_user_name_map(db: Session, user_ids: set) -> dict:
    """批量查询 user_id -> 显示名 映射，避免 N+1 查询"""
    if not user_ids:
        return {}
    ids = [i for i in user_ids if i is not None]
    if not ids:
        return {}
    rows = db.query(models.User.id, models.User.name, models.User.username).filter(models.User.id.in_(ids)).all()
    return {r[0]: (r[1] or r[2]) for r in rows}


def fill_audit_names(db: Session, obj) -> None:
    """给业务对象动态填充 created_by_name / updated_by_name（就地修改属性）"""
    ids = set()
    for f in ("created_by", "updated_by"):
        v = getattr(obj, f, None)
        if v is not None:
            ids.add(v)
    name_map = get_user_name_map(db, ids)
    setattr(obj, "created_by_name", name_map.get(getattr(obj, "created_by", None)))
    setattr(obj, "updated_by_name", name_map.get(getattr(obj, "updated_by", None)))


def fill_audit_names_batch(db: Session, objs: list) -> None:
    """批量填充审计名（一次查询）"""
    if not objs:
        return
    ids = set()
    for o in objs:
        for f in ("created_by", "updated_by"):
            v = getattr(o, f, None)
            if v is not None:
                ids.add(v)
    name_map = get_user_name_map(db, ids)
    for o in objs:
        setattr(o, "created_by_name", name_map.get(getattr(o, "created_by", None)))
        setattr(o, "updated_by_name", name_map.get(getattr(o, "updated_by", None)))


def fill_exec_names(db: Session, objs) -> None:
    """给 ExecutionRecord 填充 case_name / env_name / project_id / project_name（支持单个对象或列表）"""
    if not objs:
        return
    single = not isinstance(objs, list)
    obj_list = [objs] if single else objs
    case_ids = {o.case_id for o in obj_list if getattr(o, "case_id", None)}
    env_ids = {o.env_id for o in obj_list if getattr(o, "env_id", None)}
    case_map = {}
    env_map = {}
    project_map = {}  # case_id -> (project_id, project_name)
    if case_ids:
        # 一次联表查询拿到 case_name + project_id + project_name
        rows = db.query(
            models.TestCase.id, models.TestCase.name, models.TestCase.project_id, models.Project.name
        ).outerjoin(models.Project, models.TestCase.project_id == models.Project.id) \
         .filter(models.TestCase.id.in_(case_ids)).all()
        case_map = {r[0]: r[1] for r in rows}
        for r in rows:
            project_map[r[0]] = (r[2], r[3])
    if env_ids:
        rows = db.query(models.Environment.id, models.Environment.name).filter(models.Environment.id.in_(env_ids)).all()
        env_map = {r[0]: r[1] for r in rows}
    for o in obj_list:
        cid = getattr(o, "case_id", None)
        setattr(o, "case_name", case_map.get(cid))
        setattr(o, "env_name", env_map.get(getattr(o, "env_id", None)))
        proj_info = project_map.get(cid)
        setattr(o, "project_id", proj_info[0] if proj_info else None)
        setattr(o, "project_name", proj_info[1] if proj_info else None)


# ============ 操作日志 ============
def log_operation(
    db: Session,
    user,
    action: str,
    target_type: str,
    target_id: int | None = None,
    target_name: str | None = None,
    detail: str | None = None,
) -> None:
    """记录一条操作日志。失败不影响主业务，静默忽略。"""
    try:
        log = models.OperationLog(
            user_id=user.id if user else None,
            username=user.username if user else None,
            action=action,
            target_type=target_type,
            target_id=target_id,
            target_name=target_name,
            detail=detail,
        )
        db.add(log)
        db.commit()
    except Exception:
        db.rollback()


# ============ Project ============
def create_project(db: Session, data: schemas.ProjectCreate, user_id: Optional[int] = None) -> models.Project:
    obj = models.Project(name=data.name, description=data.description, created_by=user_id, updated_by=user_id)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def get_project(db: Session, project_id: int) -> Optional[models.Project]:
    return db.query(models.Project).filter(models.Project.id == project_id).first()


def list_projects(db: Session, created_by: Optional[int] = None, updated_by: Optional[int] = None) -> List[models.Project]:
    q = db.query(models.Project)
    if created_by is not None:
        q = q.filter(models.Project.created_by == created_by)
    if updated_by is not None:
        q = q.filter(models.Project.updated_by == updated_by)
    return q.order_by(models.Project.id.desc()).all()


def update_project(db: Session, project: models.Project, data: schemas.ProjectUpdate, user_id: Optional[int] = None) -> models.Project:
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(project, k, v)
    if user_id is not None:
        project.updated_by = user_id
    db.commit()
    db.refresh(project)
    return project


def delete_project(db: Session, project: models.Project):
    db.delete(project)
    db.commit()


# ============ Environment ============
def create_environment(db: Session, data: schemas.EnvironmentCreate, user_id: Optional[int] = None) -> models.Environment:
    payload = data.model_dump()
    payload["created_by"] = user_id
    payload["updated_by"] = user_id
    obj = models.Environment(**payload)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def get_environment(db: Session, env_id: int) -> Optional[models.Environment]:
    return db.query(models.Environment).filter(models.Environment.id == env_id).first()


def list_environments(db: Session, project_id: Optional[int] = None, created_by: Optional[int] = None, updated_by: Optional[int] = None) -> List[models.Environment]:
    q = db.query(models.Environment)
    if project_id is not None:
        q = q.filter(models.Environment.project_id == project_id)
    if created_by is not None:
        q = q.filter(models.Environment.created_by == created_by)
    if updated_by is not None:
        q = q.filter(models.Environment.updated_by == updated_by)
    return q.order_by(models.Environment.id.desc()).all()


def update_environment(db: Session, env: models.Environment, data: schemas.EnvironmentUpdate, user_id: Optional[int] = None) -> models.Environment:
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(env, k, v)
    if user_id is not None:
        env.updated_by = user_id
    db.commit()
    db.refresh(env)
    return env


def delete_environment(db: Session, env: models.Environment):
    db.delete(env)
    db.commit()


def copy_environment(db: Session, env: models.Environment) -> models.Environment:
    """复制环境，name 加 _copy 后缀，code 冲突时加数字"""
    base_name = env.name + "_copy"
    new_name = base_name
    n = 1
    while db.query(models.Environment).filter(
        models.Environment.project_id == env.project_id,
        models.Environment.name == new_name
    ).first():
        n += 1
        new_name = f"{base_name}_{n}"
    obj = models.Environment(
        project_id=env.project_id,
        name=new_name,
        base_url=env.base_url,
        db_config=env.db_config or {},
        login_config=env.login_config or {},
        notify_config=env.notify_config or {},
        variables=env.variables or {},
        common_headers=env.common_headers or {},
        is_default=False,
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


# ============ ApiGroup ============
def create_api_group(db: Session, data: schemas.ApiGroupCreate) -> models.ApiGroup:
    obj = models.ApiGroup(**data.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def get_api_group(db: Session, group_id: int) -> Optional[models.ApiGroup]:
    return db.query(models.ApiGroup).filter(models.ApiGroup.id == group_id).first()


def list_api_groups(db: Session, project_id: int) -> List[models.ApiGroup]:
    return db.query(models.ApiGroup).filter(
        models.ApiGroup.project_id == project_id
    ).order_by(models.ApiGroup.sort_order, models.ApiGroup.id).all()


def update_api_group(db: Session, group: models.ApiGroup, data: schemas.ApiGroupUpdate) -> models.ApiGroup:
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(group, k, v)
    db.commit()
    db.refresh(group)
    return group


def delete_api_group(db: Session, group: models.ApiGroup):
    # 阻止删除非空分组：组内仍有接口时拒绝，强制用户先移走
    if group.apis:
        raise ValueError(f"分组「{group.name}」下还有 {len(group.apis)} 个接口，请先移走后再删除")
    db.delete(group)
    db.commit()


def batch_move_apis(db: Session, api_ids: List[int], group_id: Optional[int]) -> int:
    """批量更新接口的 group_id，返回受影响行数"""
    if not api_ids:
        return 0
    updated = db.query(models.ApiDefinition).filter(
        models.ApiDefinition.id.in_(api_ids)
    ).update({models.ApiDefinition.group_id: group_id}, synchronize_session=False)
    db.commit()
    return updated


def reorder_apis(db: Session, items: List[dict]) -> int:
    """批量更新接口的 sort_order（组内拖拽排序）"""
    if not items:
        return 0
    updated = 0
    for it in items:
        updated += db.query(models.ApiDefinition).filter(
            models.ApiDefinition.id == it["id"]
        ).update({models.ApiDefinition.sort_order: it["sort_order"]}, synchronize_session=False)
    db.commit()
    return updated


# ============ CaseGroup ============
def create_case_group(db: Session, data: schemas.CaseGroupCreate) -> models.CaseGroup:
    obj = models.CaseGroup(**data.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def get_case_group(db: Session, group_id: int) -> Optional[models.CaseGroup]:
    return db.query(models.CaseGroup).filter(models.CaseGroup.id == group_id).first()


def list_case_groups(db: Session, project_id: int) -> List[models.CaseGroup]:
    return db.query(models.CaseGroup).filter(
        models.CaseGroup.project_id == project_id
    ).order_by(models.CaseGroup.sort_order, models.CaseGroup.id).all()


def update_case_group(db: Session, group: models.CaseGroup, data: schemas.CaseGroupUpdate) -> models.CaseGroup:
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(group, k, v)
    db.commit()
    db.refresh(group)
    return group


def delete_case_group(db: Session, group: models.CaseGroup):
    db.delete(group)
    db.commit()


# ============ ApiDefinition ============
def create_api(db: Session, data: schemas.ApiCreate, user_id: Optional[int] = None) -> models.ApiDefinition:
    payload = data.model_dump()
    fields = payload.pop("fields", [])
    payload["created_by"] = user_id
    payload["updated_by"] = user_id
    obj = models.ApiDefinition(**payload)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    _sync_api_fields(db, obj.id, fields)
    db.refresh(obj)
    return obj


def get_api(db: Session, api_id: int) -> Optional[models.ApiDefinition]:
    return db.query(models.ApiDefinition).filter(models.ApiDefinition.id == api_id).first()


def get_api_by_code(db: Session, code: str) -> Optional[models.ApiDefinition]:
    return db.query(models.ApiDefinition).filter(models.ApiDefinition.code == code).first()


def list_apis(db: Session, project_id: Optional[int] = None, created_by: Optional[int] = None, updated_by: Optional[int] = None) -> List[models.ApiDefinition]:
    q = db.query(models.ApiDefinition)
    if project_id is not None:
        q = q.filter(models.ApiDefinition.project_id == project_id)
    if created_by is not None:
        q = q.filter(models.ApiDefinition.created_by == created_by)
    if updated_by is not None:
        q = q.filter(models.ApiDefinition.updated_by == updated_by)
    # 组内按 sort_order 排序，未设置的（0/同值）再按 id 倒序保持稳定
    return q.order_by(models.ApiDefinition.sort_order, models.ApiDefinition.id.desc()).all()


def update_api(db: Session, api: models.ApiDefinition, data: schemas.ApiUpdate, user_id: Optional[int] = None) -> models.ApiDefinition:
    payload = data.model_dump(exclude_unset=True)
    fields = payload.pop("fields", None)
    for k, v in payload.items():
        setattr(api, k, v)
    if user_id is not None:
        api.updated_by = user_id
    db.commit()
    if fields is not None:
        _sync_api_fields(db, api.id, fields)
    db.refresh(api)
    return api


def delete_api(db: Session, api: models.ApiDefinition):
    # 阻止删除被用例引用的接口：CaseNodeConfig.api_id 指向该接口时拒绝
    ref_count = db.query(models.CaseNodeConfig).filter(models.CaseNodeConfig.api_id == api.id).count()
    if ref_count > 0:
        # 查出引用该接口的用例名称，便于定位
        case_ids = db.query(models.CaseNodeConfig.case_id).filter(
            models.CaseNodeConfig.api_id == api.id
        ).distinct().all()
        case_id_list = [c[0] for c in case_ids]
        cases = db.query(models.TestCase).filter(models.TestCase.id.in_(case_id_list)).all() if case_id_list else []
        case_names = "、".join(c.name for c in cases) if cases else f"用例ID: {case_id_list}"
        raise ValueError(f"接口「{api.name}」被 {len(case_id_list)} 个用例引用（{case_names}），请先移除用例中的该节点后再删除")
    db.delete(api)
    db.commit()


def copy_api(db: Session, api: models.ApiDefinition) -> models.ApiDefinition:
    """复制接口，code 加 _copy 后缀（冲突时加数字），同时复制字段"""
    base_code = api.code + "_copy"
    new_code = base_code
    n = 1
    while db.query(models.ApiDefinition).filter(models.ApiDefinition.code == new_code).first():
        n += 1
        new_code = f"{base_code}_{n}"
    obj = models.ApiDefinition(
        project_id=api.project_id,
        group_id=api.group_id,
        name=api.name + "_copy",
        code=new_code,
        category=api.category,
        method=api.method,
        path=api.path,
        description=api.description,
        request_template=api.request_template or {},
        headers_template=api.headers_template or {},
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    # 复制字段
    for f in (api.fields or []):
        nf = models.ApiField(
            api_id=obj.id,
            key=f.key,
            label=f.label,
            field_type=f.field_type,
            required=f.required,
            default_value=f.default_value,
            remark=f.remark,
            sort_order=f.sort_order,
        )
        db.add(nf)
    db.commit()
    db.refresh(obj)
    return obj


def _sync_api_fields(db: Session, api_id: int, fields: List[dict]):
    """全量覆盖接口的请求字段"""
    db.query(models.ApiField).filter(models.ApiField.api_id == api_id).delete()
    for idx, f in enumerate(fields):
        obj = models.ApiField(
            api_id=api_id,
            key=f["key"],
            label=f.get("label"),
            field_type=f.get("field_type", "string"),
            required=f.get("required", False),
            default_value=f.get("default_value"),
            remark=f.get("remark"),
            sort_order=f.get("sort_order", idx),
        )
        db.add(obj)
    db.commit()


# ============ TestCase + NodeConfig ============
def create_testcase(db: Session, data: schemas.TestCaseCreate, user_id: Optional[int] = None) -> models.TestCase:
    payload = data.model_dump()
    node_configs = payload.pop("node_configs", [])
    payload["created_by"] = user_id
    payload["updated_by"] = user_id
    case = models.TestCase(**payload)
    db.add(case)
    db.commit()
    db.refresh(case)
    _sync_node_configs(db, case.id, node_configs)
    db.refresh(case)
    return case


def get_testcase(db: Session, case_id: int) -> Optional[models.TestCase]:
    return db.query(models.TestCase).filter(models.TestCase.id == case_id).first()


def list_testcases(db: Session, project_id: Optional[int] = None, created_by: Optional[int] = None, updated_by: Optional[int] = None) -> List[models.TestCase]:
    q = db.query(models.TestCase)
    if project_id is not None:
        q = q.filter(models.TestCase.project_id == project_id)
    if created_by is not None:
        q = q.filter(models.TestCase.created_by == created_by)
    if updated_by is not None:
        q = q.filter(models.TestCase.updated_by == updated_by)
    # 组内按 sort_order 排序，未设置的（0/同值）再按 id 倒序保持稳定
    return q.order_by(models.TestCase.sort_order, models.TestCase.id.desc()).all()


def batch_move_testcases(db: Session, case_ids: List[int], group_id: Optional[int]) -> int:
    """批量更新用例的 group_id，返回受影响行数"""
    if not case_ids:
        return 0
    updated = db.query(models.TestCase).filter(
        models.TestCase.id.in_(case_ids)
    ).update({models.TestCase.group_id: group_id}, synchronize_session=False)
    db.commit()
    return updated


def reorder_testcases(db: Session, items: List[dict]) -> int:
    """批量更新用例的 sort_order（组内拖拽排序）"""
    if not items:
        return 0
    updated = 0
    for it in items:
        updated += db.query(models.TestCase).filter(
            models.TestCase.id == it["id"]
        ).update({models.TestCase.sort_order: it["sort_order"]}, synchronize_session=False)
    db.commit()
    return updated


def update_testcase(db: Session, case: models.TestCase, data: schemas.TestCaseUpdate, user_id: Optional[int] = None) -> models.TestCase:
    payload = data.model_dump(exclude_unset=True)
    node_configs = payload.pop("node_configs", None)
    for k, v in payload.items():
        setattr(case, k, v)
    if user_id is not None:
        case.updated_by = user_id
    # 显式刷新更新时间：MySQL 建表语句未必生成 ON UPDATE CURRENT_TIMESTAMP，
    # ORM 的 onupdate 也可能因字段未变而不触发，这里强制覆盖确保列表更新时间变化
    case.updated_at = datetime.now()
    db.commit()
    if node_configs is not None:
        _sync_node_configs(db, case.id, node_configs)
    db.refresh(case)
    return case


def delete_testcase(db: Session, case: models.TestCase):
    db.delete(case)
    db.commit()


def copy_testcase(db: Session, case: models.TestCase) -> models.TestCase:
    """复制用例，name 加 _copy 后缀（冲突时加数字），同时复制节点配置"""
    base_name = case.name + "_copy"
    new_name = base_name
    n = 1
    while db.query(models.TestCase).filter(
        models.TestCase.project_id == case.project_id,
        models.TestCase.name == new_name
    ).first():
        n += 1
        new_name = f"{base_name}_{n}"
    obj = models.TestCase(
        project_id=case.project_id,
        group_id=case.group_id,
        name=new_name,
        description=case.description,
        dag_config=case.dag_config or {"nodes": [], "edges": []},
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    # 复制节点配置
    for nc in (case.node_configs or []):
        nnc = models.CaseNodeConfig(
            case_id=obj.id,
            node_id=nc.node_id,
            api_id=nc.api_id,
            pre_process=nc.pre_process or [],
            post_extract=nc.post_extract or [],
            assertions=nc.assertions or [],
        )
        db.add(nnc)
    db.commit()
    db.refresh(obj)
    return obj


def _sync_node_configs(db: Session, case_id: int, node_configs: List[dict]):
    """全量覆盖用例的节点配置"""
    db.query(models.CaseNodeConfig).filter(models.CaseNodeConfig.case_id == case_id).delete()
    for nc in node_configs:
        obj = models.CaseNodeConfig(
            case_id=case_id,
            node_id=nc["node_id"],
            api_id=nc.get("api_id"),
            pre_process=nc.get("pre_process", []),
            post_extract=nc.get("post_extract", []),
            assertions=nc.get("assertions", []),
        )
        db.add(obj)
    db.commit()


# ============ ProjectVersion 项目版本快照 ============
def _snapshot_api_groups(db: Session, project_id: int) -> List[dict]:
    rows = db.query(models.ApiGroup).filter(models.ApiGroup.project_id == project_id)\
        .order_by(models.ApiGroup.sort_order, models.ApiGroup.id).all()
    return [{"id": g.id, "name": g.name, "sort_order": g.sort_order} for g in rows]


def _snapshot_case_groups(db: Session, project_id: int) -> List[dict]:
    rows = db.query(models.CaseGroup).filter(models.CaseGroup.project_id == project_id)\
        .order_by(models.CaseGroup.sort_order, models.CaseGroup.id).all()
    return [{"id": g.id, "name": g.name, "sort_order": g.sort_order} for g in rows]


def _snapshot_apis(db: Session, project_id: int) -> List[dict]:
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
            "request_template": a.request_template or {},
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


def _snapshot_cases(db: Session, project_id: int) -> List[dict]:
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
    description: Optional[str],
    user_id: Optional[int] = None,
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


def list_project_versions(db: Session, project_id: int) -> List[models.ProjectVersion]:
    return (
        db.query(models.ProjectVersion)
        .filter(models.ProjectVersion.project_id == project_id)
        .order_by(models.ProjectVersion.version_no.desc())
        .all()
    )


def get_project_version(db: Session, version_id: int) -> Optional[models.ProjectVersion]:
    return db.query(models.ProjectVersion).filter(models.ProjectVersion.id == version_id).first()


def fill_version_audit_names(db: Session, versions: list) -> None:
    """批量给 ProjectVersion 填充 created_by_name"""
    if not versions:
        return
    ids = {v.created_by for v in versions if v.created_by is not None}
    name_map = get_user_name_map(db, ids)
    for v in versions:
        setattr(v, "created_by_name", name_map.get(v.created_by))


def _diff_collection(base: List[dict], target: List[dict], key: str) -> dict:
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


def rollback_project_version(
    db: Session,
    project: models.Project,
    version: models.ProjectVersion,
    user_id: Optional[int] = None,
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

    # 2. 删除当前所有数据（级联删除 fields / node_configs）
    db.query(models.TestCase).filter(models.TestCase.project_id == project.id).delete(synchronize_session=False)
    db.query(models.ApiDefinition).filter(models.ApiDefinition.project_id == project.id).delete(synchronize_session=False)
    db.query(models.CaseGroup).filter(models.CaseGroup.project_id == project.id).delete(synchronize_session=False)
    db.query(models.ApiGroup).filter(models.ApiGroup.project_id == project.id).delete(synchronize_session=False)
    db.commit()

    # 3. 重建分组（建立 old_id -> new_id 映射）
    api_group_map: dict = {}
    for g in snap.get("api_groups", []):
        old_id = g.get("id")
        ng = models.ApiGroup(project_id=project.id, name=g["name"], sort_order=g.get("sort_order", 0))
        db.add(ng)
        db.flush()
        if old_id is not None:
            api_group_map[old_id] = ng.id

    case_group_map: dict = {}
    for g in snap.get("case_groups", []):
        old_id = g.get("id")
        ng = models.CaseGroup(project_id=project.id, name=g["name"], sort_order=g.get("sort_order", 0))
        db.add(ng)
        db.flush()
        if old_id is not None:
            case_group_map[old_id] = ng.id

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
    for c in snap.get("cases", []):
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
            ))

    db.commit()


def delete_project_version(db: Session, version: models.ProjectVersion):
    db.delete(version)
    db.commit()


# ============ Execution ============
def create_execution(db: Session, case_id: int, env_id: int, user_id: Optional[int] = None) -> models.ExecutionRecord:
    obj = models.ExecutionRecord(case_id=case_id, env_id=env_id, status="running", created_by=user_id)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def get_execution(db: Session, exec_id: int) -> Optional[models.ExecutionRecord]:
    return db.query(models.ExecutionRecord).filter(models.ExecutionRecord.id == exec_id).first()


def list_executions(db: Session, case_id: Optional[int] = None, project_id: Optional[int] = None, created_by: Optional[int] = None, limit: int = 50) -> List[models.ExecutionRecord]:
    """执行记录列表：支持按用例、项目（联表 case.project_id）、执行人过滤"""
    q = db.query(models.ExecutionRecord)
    if case_id is not None:
        q = q.filter(models.ExecutionRecord.case_id == case_id)
    if project_id is not None:
        # 联表 TestCase 过滤 project_id
        q = q.join(models.TestCase, models.ExecutionRecord.case_id == models.TestCase.id) \
             .filter(models.TestCase.project_id == project_id)
    if created_by is not None:
        q = q.filter(models.ExecutionRecord.created_by == created_by)
    return q.order_by(models.ExecutionRecord.id.desc()).limit(limit).all()


# ============ FieldDictionary 字段字典 ============
def create_field_dictionary(db: Session, data: schemas.FieldDictionaryCreate, user_id: Optional[int] = None) -> models.FieldDictionary:
    payload = data.model_dump()
    payload["created_by"] = user_id
    payload["updated_by"] = user_id
    obj = models.FieldDictionary(**payload)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def get_field_dictionary(db: Session, dict_id: int) -> Optional[models.FieldDictionary]:
    return db.query(models.FieldDictionary).filter(models.FieldDictionary.id == dict_id).first()


def get_field_dictionary_by_key(db: Session, project_id: int, key: str) -> Optional[models.FieldDictionary]:
    return db.query(models.FieldDictionary).filter(
        models.FieldDictionary.project_id == project_id,
        models.FieldDictionary.key == key,
    ).first()


def list_field_dictionaries(db: Session, project_id: int, keyword: Optional[str] = None) -> List[models.FieldDictionary]:
    q = db.query(models.FieldDictionary).filter(models.FieldDictionary.project_id == project_id)
    if keyword:
        kw = f"%{keyword}%"
        q = q.filter(
            (models.FieldDictionary.key.like(kw)) | (models.FieldDictionary.label.like(kw))
        )
    return q.order_by(models.FieldDictionary.key.asc()).all()


def update_field_dictionary(db: Session, obj: models.FieldDictionary, data: schemas.FieldDictionaryUpdate, user_id: Optional[int] = None) -> models.FieldDictionary:
    payload = data.model_dump(exclude_unset=True)
    for k, v in payload.items():
        setattr(obj, k, v)
    if user_id is not None:
        obj.updated_by = user_id
    db.commit()
    db.refresh(obj)
    return obj


def delete_field_dictionary(db: Session, obj: models.FieldDictionary):
    db.delete(obj)
    db.commit()


def batch_upsert_field_dictionaries(db: Session, project_id: int, items: List[schemas.FieldDictItemIn], user_id: Optional[int] = None) -> int:
    """批量覆盖式写入：同 key 更新 label，新 key 插入。返回 upsert 条数。"""
    count = 0
    for item in items:
        existing = get_field_dictionary_by_key(db, project_id, item.key)
        if existing:
            existing.label = item.label
            if user_id is not None:
                existing.updated_by = user_id
        else:
            obj = models.FieldDictionary(
                project_id=project_id,
                key=item.key,
                label=item.label,
                created_by=user_id,
                updated_by=user_id,
            )
            db.add(obj)
        count += 1
    db.commit()
    return count


def get_field_dict_map(db: Session, project_id: int) -> dict:
    """返回 {key: label} 映射，供前端运行时查询"""
    rows = db.query(models.FieldDictionary.key, models.FieldDictionary.label).filter(
        models.FieldDictionary.project_id == project_id
    ).all()
    return {r[0]: r[1] for r in rows}

"""数据库 CRUD 操作（遗留平铺实现，逐步迁移至各域子模块，勿在此新增内容）"""
from datetime import datetime
from typing import TypeVar

from sqlalchemy.orm import Session

from .. import models, schemas

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
    obj.created_by_name = name_map.get(getattr(obj, "created_by", None))
    obj.updated_by_name = name_map.get(getattr(obj, "updated_by", None))


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
        o.created_by_name = name_map.get(getattr(o, "created_by", None))
        o.updated_by_name = name_map.get(getattr(o, "updated_by", None))


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
        o.case_name = case_map.get(cid)
        o.env_name = env_map.get(getattr(o, "env_id", None))
        proj_info = project_map.get(cid)
        o.project_id = proj_info[0] if proj_info else None
        o.project_name = proj_info[1] if proj_info else None


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
def create_project(db: Session, data: schemas.ProjectCreate, user_id: int | None = None) -> models.Project:
    obj = models.Project(name=data.name, description=data.description, created_by=user_id, updated_by=user_id)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def get_project(db: Session, project_id: int) -> models.Project | None:
    return db.query(models.Project).filter(models.Project.id == project_id).first()


def list_projects(db: Session, created_by: int | None = None, updated_by: int | None = None) -> list[models.Project]:
    q = db.query(models.Project)
    if created_by is not None:
        q = q.filter(models.Project.created_by == created_by)
    if updated_by is not None:
        q = q.filter(models.Project.updated_by == updated_by)
    return q.order_by(models.Project.sort_order, models.Project.id.desc()).all()


def update_project(db: Session, project: models.Project, data: schemas.ProjectUpdate, user_id: int | None = None) -> models.Project:
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(project, k, v)
    if user_id is not None:
        project.updated_by = user_id
    db.commit()
    db.refresh(project)
    return project


def _clear_datasets(db: Session, project_id: int | None = None, case_id: int | None = None):
    """删除指定范围的数据集及行（外键安全顺序）：
    1) 解除用例 dataset_id 绑定（test_cases.dataset_id → data_sets）
    2) 删行（data_set_rows.dataset_id → data_sets）
    3) 删数据集本体"""
    q = db.query(models.DataSet)
    if project_id is not None:
        q = q.filter(models.DataSet.project_id == project_id)
    else:
        q = q.filter(models.DataSet.case_id == case_id)
    ds_ids = [i for (i,) in q.with_entities(models.DataSet.id).all()]
    if not ds_ids:
        return
    db.query(models.TestCase).filter(
        models.TestCase.dataset_id.in_(ds_ids)).update(
        {models.TestCase.dataset_id: None}, synchronize_session=False)
    db.query(models.DataSetRow).filter(
        models.DataSetRow.dataset_id.in_(ds_ids)).delete(synchronize_session=False)
    db.query(models.DataSet).filter(
        models.DataSet.id.in_(ds_ids)).delete(synchronize_session=False)


def delete_project(db: Session, project: models.Project):
    """删除项目：数据集为用例私有，不在 ORM 级联链上（case_id / dataset_id 双外键），
    先清项目名下数据集（含解绑）再走既有级联，防外键约束 500。"""
    _clear_datasets(db, project_id=project.id)
    # 执行记录 env_id → environments：项目环境删除前先解引用
    # （记录本身随用例级联删，此处仅断开外键，历史记录将随项目整体消失）
    env_ids = [i for (i,) in db.query(models.Environment.id).filter(
        models.Environment.project_id == project.id).all()]
    if env_ids:
        db.query(models.ExecutionRecord).filter(
            models.ExecutionRecord.env_id.in_(env_ids)).update(
            {models.ExecutionRecord.env_id: None}, synchronize_session=False)
    db.delete(project)
    db.commit()


def reorder_projects(db: Session, items: list[dict], user_id: int | None = None) -> int:
    """批量更新项目的 sort_order（拖拽排序），同步记录更新人"""
    if not items:
        return 0
    audit: dict = {}
    if user_id is not None:
        audit = {models.Project.updated_by: user_id, models.Project.updated_at: datetime.now()}
    updated = 0
    for it in items:
        updated += db.query(models.Project).filter(
            models.Project.id == it["id"]
        ).update({models.Project.sort_order: it["sort_order"], **audit}, synchronize_session=False)
    db.commit()
    return updated


# ============ Environment ============
def create_environment(db: Session, data: schemas.EnvironmentCreate, user_id: int | None = None) -> models.Environment:
    payload = data.model_dump()
    payload["created_by"] = user_id
    payload["updated_by"] = user_id
    obj = models.Environment(**payload)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def get_environment(db: Session, env_id: int) -> models.Environment | None:
    return db.query(models.Environment).filter(models.Environment.id == env_id).first()


def list_environments(db: Session, project_id: int | None = None, created_by: int | None = None, updated_by: int | None = None) -> list[models.Environment]:
    q = db.query(models.Environment)
    if project_id is not None:
        q = q.filter(models.Environment.project_id == project_id)
    if created_by is not None:
        q = q.filter(models.Environment.created_by == created_by)
    if updated_by is not None:
        q = q.filter(models.Environment.updated_by == updated_by)
    return q.order_by(models.Environment.sort_order, models.Environment.id.desc()).all()


def update_environment(db: Session, env: models.Environment, data: schemas.EnvironmentUpdate, user_id: int | None = None) -> models.Environment:
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


def reorder_environments(db: Session, items: list[dict], user_id: int | None = None) -> int:
    """批量更新环境的 sort_order（拖拽排序），同步记录更新人"""
    if not items:
        return 0
    audit: dict = {}
    if user_id is not None:
        audit = {models.Environment.updated_by: user_id, models.Environment.updated_at: datetime.now()}
    updated = 0
    for it in items:
        updated += db.query(models.Environment).filter(
            models.Environment.id == it["id"]
        ).update({models.Environment.sort_order: it["sort_order"], **audit}, synchronize_session=False)
    db.commit()
    return updated


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


def get_api_group(db: Session, group_id: int) -> models.ApiGroup | None:
    return db.query(models.ApiGroup).filter(models.ApiGroup.id == group_id).first()


def list_api_groups(db: Session, project_id: int) -> list[models.ApiGroup]:
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
    # 阻止删除非空分组：有子分组或有接口时拒绝，强制用户先移走
    if group.children:
        raise ValueError(f"分组「{group.name}」下还有 {len(group.children)} 个子分组，请先删除子分组")
    if group.apis:
        raise ValueError(f"分组「{group.name}」下还有 {len(group.apis)} 个接口，请先移走后再删除")
    db.delete(group)
    db.commit()


def batch_move_apis(db: Session, api_ids: list[int], group_id: int | None, user_id: int | None = None) -> int:
    """批量更新接口的 group_id，返回受影响行数。移动分组属于接口更新，须记录更新人"""
    if not api_ids:
        return 0
    values: dict = {models.ApiDefinition.group_id: group_id}
    if user_id is not None:
        values.update({models.ApiDefinition.updated_by: user_id, models.ApiDefinition.updated_at: datetime.now()})
    updated = db.query(models.ApiDefinition).filter(
        models.ApiDefinition.id.in_(api_ids)
    ).update(values, synchronize_session=False)
    db.commit()
    return updated


def reorder_apis(db: Session, items: list[dict], user_id: int | None = None) -> int:
    """批量更新接口的 sort_order（组内拖拽排序），同步记录更新人"""
    if not items:
        return 0
    audit: dict = {}
    if user_id is not None:
        audit = {models.ApiDefinition.updated_by: user_id, models.ApiDefinition.updated_at: datetime.now()}
    updated = 0
    for it in items:
        updated += db.query(models.ApiDefinition).filter(
            models.ApiDefinition.id == it["id"]
        ).update({models.ApiDefinition.sort_order: it["sort_order"], **audit}, synchronize_session=False)
    db.commit()
    return updated


# ============ CaseGroup ============
def create_case_group(db: Session, data: schemas.CaseGroupCreate) -> models.CaseGroup:
    obj = models.CaseGroup(**data.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def get_case_group(db: Session, group_id: int) -> models.CaseGroup | None:
    return db.query(models.CaseGroup).filter(models.CaseGroup.id == group_id).first()


def list_case_groups(db: Session, project_id: int) -> list[models.CaseGroup]:
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
    # 阻止删除非空分组：有子分组或有用例时拒绝，强制用户先移走
    if group.children:
        raise ValueError(f"分组「{group.name}」下还有 {len(group.children)} 个子分组，请先删除子分组")
    if group.cases:
        raise ValueError(f"分组「{group.name}」下还有 {len(group.cases)} 个用例，请先移走后再删除")
    db.delete(group)
    db.commit()


# ============ ApiDefinition ============
def create_api(db: Session, data: schemas.ApiCreate, user_id: int | None = None) -> models.ApiDefinition:
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


def get_api(db: Session, api_id: int) -> models.ApiDefinition | None:
    return db.query(models.ApiDefinition).filter(models.ApiDefinition.id == api_id).first()


def get_api_by_code(db: Session, code: str) -> models.ApiDefinition | None:
    return db.query(models.ApiDefinition).filter(models.ApiDefinition.code == code).first()


def list_apis(db: Session, project_id: int | None = None, created_by: int | None = None, updated_by: int | None = None) -> list[models.ApiDefinition]:
    q = db.query(models.ApiDefinition)
    if project_id is not None:
        q = q.filter(models.ApiDefinition.project_id == project_id)
    if created_by is not None:
        q = q.filter(models.ApiDefinition.created_by == created_by)
    if updated_by is not None:
        q = q.filter(models.ApiDefinition.updated_by == updated_by)
    # 组内按 sort_order 排序，未设置的（0/同值）再按 id 倒序保持稳定
    return q.order_by(models.ApiDefinition.sort_order, models.ApiDefinition.id.desc()).all()


def update_api(db: Session, api: models.ApiDefinition, data: schemas.ApiUpdate, user_id: int | None = None) -> models.ApiDefinition:
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


def _sync_api_fields(db: Session, api_id: int, fields: list[dict]):
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
def create_testcase(db: Session, data: schemas.TestCaseCreate, user_id: int | None = None) -> models.TestCase:
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


def get_testcase(db: Session, case_id: int) -> models.TestCase | None:
    return db.query(models.TestCase).filter(models.TestCase.id == case_id).first()


def list_testcases(db: Session, project_id: int | None = None, created_by: int | None = None, updated_by: int | None = None) -> list[models.TestCase]:
    q = db.query(models.TestCase)
    if project_id is not None:
        q = q.filter(models.TestCase.project_id == project_id)
    if created_by is not None:
        q = q.filter(models.TestCase.created_by == created_by)
    if updated_by is not None:
        q = q.filter(models.TestCase.updated_by == updated_by)
    # 组内按 sort_order 排序，未设置的（0/同值）再按 id 倒序保持稳定
    return q.order_by(models.TestCase.sort_order, models.TestCase.id.desc()).all()


def batch_move_testcases(db: Session, case_ids: list[int], group_id: int | None, user_id: int | None = None) -> int:
    """批量更新用例的 group_id，返回受影响行数。移动分组属于用例更新，须记录更新人"""
    if not case_ids:
        return 0
    values: dict = {models.TestCase.group_id: group_id}
    if user_id is not None:
        values.update({models.TestCase.updated_by: user_id, models.TestCase.updated_at: datetime.now()})
    updated = db.query(models.TestCase).filter(
        models.TestCase.id.in_(case_ids)
    ).update(values, synchronize_session=False)
    db.commit()
    return updated


def reorder_testcases(db: Session, items: list[dict], user_id: int | None = None) -> int:
    """批量更新用例的 sort_order（组内拖拽排序），同步记录更新人"""
    if not items:
        return 0
    audit: dict = {}
    if user_id is not None:
        audit = {models.TestCase.updated_by: user_id, models.TestCase.updated_at: datetime.now()}
    updated = 0
    for it in items:
        updated += db.query(models.TestCase).filter(
            models.TestCase.id == it["id"]
        ).update({models.TestCase.sort_order: it["sort_order"], **audit}, synchronize_session=False)
    db.commit()
    return updated


def update_testcase(db: Session, case: models.TestCase, data: schemas.TestCaseUpdate, user_id: int | None = None) -> models.TestCase:
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
    """删除用例：其私有数据集（场景包）随宿主级联删除（含行 + 解绑），防外键约束 500。"""
    _clear_datasets(db, case_id=case.id)
    db.delete(case)
    db.commit()


def copy_testcase(db: Session, case: models.TestCase) -> models.TestCase:
    """复制用例，name 加 _copy 后缀（冲突时加数字），同时复制节点配置；套件连带复制成员与白名单"""
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
        case_type=getattr(case, "case_type", "normal"),
        dag_config=case.dag_config or {"nodes": [], "edges": []},
        shared_vars=case.shared_vars,
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
            wait_after_ms=nc.wait_after_ms or 0,
        )
        db.add(nnc)
    # 套件：成员引用整表复制（成员用例与环境的引用关系保持）
    if getattr(case, "case_type", "normal") == "suite":
        for m in (case.members or []):
            db.add(models.SuiteMember(
                suite_case_id=obj.id, member_case_id=m.member_case_id,
                env_id=m.env_id, sort_order=m.sort_order))
    db.commit()
    db.refresh(obj)
    return obj


def _sync_node_configs(db: Session, case_id: int, node_configs: list[dict]):
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
            wait_after_ms=nc.get("wait_after_ms", 0) or 0,
        )
        db.add(obj)
    db.commit()


# ============ Execution ============
def get_execution(db: Session, exec_id: int) -> models.ExecutionRecord | None:
    return db.query(models.ExecutionRecord).filter(models.ExecutionRecord.id == exec_id).first()


def _execution_filter_query(db: Session, case_id: int | None = None, project_id: int | None = None,
                            created_by: int | None = None, case_name: str | None = None,
                            status: str | None = None, start_time: datetime | None = None,
                            end_time: datetime | None = None):
    """执行记录过滤查询管道：list / count 共用，保证总数与列表口径一致"""
    q = db.query(models.ExecutionRecord)
    if case_id is not None:
        q = q.filter(models.ExecutionRecord.case_id == case_id)
    if project_id is not None or case_name:
        # 联表 TestCase 过滤 project_id / 用例名模糊匹配
        q = q.join(models.TestCase, models.ExecutionRecord.case_id == models.TestCase.id)
        if project_id is not None:
            q = q.filter(models.TestCase.project_id == project_id)
        if case_name:
            q = q.filter(models.TestCase.name.like(f"%{case_name}%"))
    if created_by is not None:
        q = q.filter(models.ExecutionRecord.created_by == created_by)
    if status:
        q = q.filter(models.ExecutionRecord.status == status)
    if start_time is not None:
        q = q.filter(models.ExecutionRecord.started_at >= start_time)
    if end_time is not None:
        q = q.filter(models.ExecutionRecord.started_at <= end_time)
    return q


# 服务端排序白名单：防任意字段名拼进 order_by
EXECUTION_SORT_FIELDS = {"id": models.ExecutionRecord.id, "started_at": models.ExecutionRecord.started_at}


def list_executions(db: Session, case_id: int | None = None, project_id: int | None = None,
                    created_by: int | None = None, limit: int = 50, offset: int = 0,
                    case_name: str | None = None, status: str | None = None,
                    start_time: datetime | None = None, end_time: datetime | None = None,
                    sort_by: str = "id", order: str = "desc") -> list[models.ExecutionRecord]:
    """执行记录列表：支持按用例、项目（联表 case.project_id）、执行人、用例名（模糊）、状态、
    开始时间范围过滤（ExecutionRecord 无 created_at，时间口径用 started_at）；
    offset/limit 服务端翻页 + sort_by/order 服务端排序（分页组件的整页排序口径）"""
    q = _execution_filter_query(db, case_id, project_id, created_by, case_name, status, start_time, end_time)
    col = EXECUTION_SORT_FIELDS.get(sort_by, models.ExecutionRecord.id)
    q = q.order_by(col.asc() if order == "asc" else col.desc())
    return q.offset(offset).limit(limit).all()


def count_executions(db: Session, case_id: int | None = None, project_id: int | None = None,
                     created_by: int | None = None, case_name: str | None = None,
                     status: str | None = None, start_time: datetime | None = None,
                     end_time: datetime | None = None) -> int:
    """执行记录总数（与 list 同口径过滤）：分页组件 total 用"""
    return _execution_filter_query(db, case_id, project_id, created_by, case_name, status,
                                   start_time, end_time).count()


# ============ FieldDictionary 字段字典 ============
def create_field_dictionary(db: Session, data: schemas.FieldDictionaryCreate, user_id: int | None = None) -> models.FieldDictionary:
    payload = data.model_dump()
    payload["created_by"] = user_id
    payload["updated_by"] = user_id
    obj = models.FieldDictionary(**payload)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def get_field_dictionary(db: Session, dict_id: int) -> models.FieldDictionary | None:
    return db.query(models.FieldDictionary).filter(models.FieldDictionary.id == dict_id).first()


def get_field_dictionary_by_key(db: Session, project_id: int, key: str) -> models.FieldDictionary | None:
    return db.query(models.FieldDictionary).filter(
        models.FieldDictionary.project_id == project_id,
        models.FieldDictionary.key == key,
    ).first()


def list_field_dictionaries(db: Session, project_id: int, keyword: str | None = None) -> list[models.FieldDictionary]:
    q = db.query(models.FieldDictionary).filter(models.FieldDictionary.project_id == project_id)
    if keyword:
        kw = f"%{keyword}%"
        q = q.filter(
            (models.FieldDictionary.key.like(kw)) | (models.FieldDictionary.label.like(kw))
        )
    return q.order_by(models.FieldDictionary.key.asc()).all()


def update_field_dictionary(db: Session, obj: models.FieldDictionary, data: schemas.FieldDictionaryUpdate, user_id: int | None = None) -> models.FieldDictionary:
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


def batch_upsert_field_dictionaries(db: Session, project_id: int, items: list[schemas.FieldDictItemIn], user_id: int | None = None) -> int:
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


# ============ FileCategory 文件分类 ============
def create_file_category(db: Session, data: schemas.FileCategoryCreate, user_id: int | None = None) -> models.FileCategory:
    obj = models.FileCategory(
        project_id=data.project_id,
        parent_id=data.parent_id,
        name=data.name,
        sort_order=data.sort_order,
        created_by=user_id,
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def list_file_categories(db: Session, project_id: int) -> list[models.FileCategory]:
    return db.query(models.FileCategory).filter(
        models.FileCategory.project_id == project_id
    ).order_by(models.FileCategory.sort_order, models.FileCategory.id).all()


def update_file_category(db: Session, obj: models.FileCategory, data: schemas.FileCategoryUpdate) -> models.FileCategory:
    payload = data.model_dump(exclude_unset=True)
    for k, v in payload.items():
        setattr(obj, k, v)
    db.commit()
    db.refresh(obj)
    return obj


def delete_file_category(db: Session, obj: models.FileCategory):
    """删除分类：子分类和文件由 cascade=all,delete-orphan 级联处理"""
    db.delete(obj)
    db.commit()


def get_file_category(db: Session, category_id: int) -> models.FileCategory | None:
    return db.query(models.FileCategory).filter(models.FileCategory.id == category_id).first()


# ============ TestFile 测试文件 ============
def get_file(db: Session, file_id: int) -> models.TestFile | None:
    return db.query(models.TestFile).filter(models.TestFile.id == file_id).first()


def get_file_by_sha256(db: Session, project_id: int, sha256: str) -> models.TestFile | None:
    """按项目 + sha256 查找文件（项目内去重）"""
    return db.query(models.TestFile).filter(
        models.TestFile.project_id == project_id,
        models.TestFile.sha256 == sha256,
    ).first()


def list_files(
    db: Session,
    project_id: int,
    category_id: int | None = None,
    keyword: str | None = None,
) -> list[models.TestFile]:
    """列出项目下的文件，支持按分类/名称过滤。"""
    q = db.query(models.TestFile).filter(models.TestFile.project_id == project_id)
    if category_id is not None:
        if category_id == 0:
            # 哨兵值 0 表示"未分类"（category_id IS NULL）
            q = q.filter(models.TestFile.category_id.is_(None))
        else:
            q = q.filter(models.TestFile.category_id == category_id)
    if keyword:
        q = q.filter(models.TestFile.name.like(f"%{keyword}%"))
    return q.order_by(models.TestFile.created_at.desc()).all()


def create_file_record(
    db: Session,
    project_id: int,
    name: str,
    original_name: str,
    content_type: str,
    size: int,
    sha256: str,
    storage_path: str,
    category_id: int | None,
    user_id: int | None,
) -> models.TestFile:
    obj = models.TestFile(
        project_id=project_id,
        category_id=category_id,
        name=name,
        original_name=original_name,
        content_type=content_type,
        size=size,
        sha256=sha256,
        storage_path=storage_path,
        ref_count=1,
        created_by=user_id,
        updated_by=user_id,
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def update_file(db: Session, obj: models.TestFile, data: schemas.FileUpdateRequest, user_id: int | None = None) -> models.TestFile:
    """更新文件元数据：重命名 / 改分类。

    category_id 通过 model_fields_set 区分两种情况：
    - 请求未携带该字段 → 跳过更新（保持原分类）
    - 显式传 null → 更新为未分类（category_id IS NULL）
    因为 Optional[int]=None 下，未传与传 null 反序列化后都是 None，无法用 is not None 区分。
    """
    if data.name is not None:
        obj.name = data.name
    if "category_id" in data.model_fields_set:
        obj.category_id = data.category_id
    if user_id is not None:
        obj.updated_by = user_id
    db.commit()
    db.refresh(obj)
    return obj


def delete_file(db: Session, obj: models.TestFile) -> bool:
    """删除文件记录：ref_count - 1，归零时删除物理文件。返回是否删除了物理文件。"""
    obj.ref_count -= 1
    delete_physical = obj.ref_count <= 0
    db.delete(obj)
    db.commit()
    return delete_physical

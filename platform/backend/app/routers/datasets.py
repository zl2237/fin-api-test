"""数据集路由：入参配置中心（2026-09-30 入参收敛定案）。

每个数据集 = 各节点入参配置的一套完整取值（多数据集 = 多场景）：
- GET /{id}/params-view：按用例 DAG 节点组织（节点 tab 数据源）
- PUT /{id}/node-config：保存单节点 params（整体替换，含静态校验）
- DELETE /{id}/node-config/{node_id}：清理悬空节点配置（画布节点已删）

服务层校验（dataset_service）抛 ValueError → 400 直给前端；
权限与项目内资源一致：登录即可管理，project_id 隔离由查询参数保证。
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import crud, models, schemas
from ..auth import get_current_user
from ..database import get_db
from ..engine.validation import validate_case_configs
from ..services import dataset_service as svc

router = APIRouter(prefix="/api/datasets", tags=["数据集"])


def _fill_extra(db: Session, obj: models.DataSet) -> models.DataSet:
    """补齐列表/详情展示字段：审计名 + 被引用用例数"""
    crud.fill_audit_names(db, obj)
    setattr(obj, "case_bound_count", crud.count_cases_bound_to_dataset(db, obj.id))
    return obj


def _svc_call(fn, *args, **kwargs):
    """服务层 ValueError → 400（错误文案已面向用户）"""
    try:
        return fn(*args, **kwargs)
    except ValueError as e:
        raise HTTPException(400, str(e))


def _get_or_404(db: Session, dataset_id: int) -> models.DataSet:
    obj = crud.get_dataset(db, dataset_id)
    if not obj:
        raise HTTPException(404, f"数据集不存在: {dataset_id}")
    return obj


def _owner_case(db: Session, obj: models.DataSet) -> models.TestCase:
    case = crud.get_testcase(db, obj.case_id)
    if not case:
        raise HTTPException(404, f"归属用例不存在: {obj.case_id}")
    return case


def _ensure_owner_not_running(db: Session, obj: models.DataSet, what: str) -> None:
    """归属用例执行中 → 禁止改数据集（运行线程读的是库内值，保存会串版本）。"""
    if obj.case_id:
        from ..crud.executions import ensure_case_not_running
        _svc_call(ensure_case_not_running, db, obj.case_id, what)


def _dag_nodes(dag: dict | None) -> list[dict]:
    return [n for n in (dag or {}).get("nodes", []) if isinstance(n, dict) and n.get("id")]


def _build_validation_payload(db: Session, case, ds: models.DataSet,
                              override: dict | None = None) -> list[dict]:
    """组装静态校验载荷：行内 per-node params（可含本次保存覆盖）
    × 节点配置的 post_extract/assertions（产出集与断言校验需要）。"""
    nodes_cfg = svc.node_configs(svc.row_data(ds))
    if override:
        nodes_cfg = {**nodes_cfg, **override}
    struct = {c.node_id: c for c in db.query(models.CaseNodeConfig)
              .filter(models.CaseNodeConfig.case_id == case.id).all()}
    out = []
    for n in _dag_nodes(case.dag_config):
        nid = n["id"]
        rc = nodes_cfg.get(nid) or {}
        c = struct.get(nid)
        out.append({
            "node_id": nid,
            "params": rc.get("params") or {},
            "post_extract": (c.post_extract if c else None) or [],
            "assertions": (c.assertions if c else None) or [],
        })
    return out


@router.get("", response_model=list[schemas.DataSetOut])
def list_datasets(case_id: int | None = None, project_id: int | None = None, with_rows: bool = False,
                  db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """列表：按用例维度（case_id 必传语义，用例间隔离）；with_rows=1 时带行（详情页复用）"""
    q = db.query(models.DataSet)
    if case_id:
        q = q.filter(models.DataSet.case_id == case_id)
    if project_id:
        q = q.filter(models.DataSet.project_id == project_id)
    objs = q.order_by(models.DataSet.id.desc()).all()
    out = []
    for o in objs:
        if not with_rows:
            o.rows = []
        out.append(_fill_extra(db, o))
    return out


@router.post("", response_model=schemas.DataSetOut)
def create(data: schemas.DataSetCreate, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    case = crud.get_testcase(db, data.case_id)
    if not case:
        raise HTTPException(404, f"用例不存在: {data.case_id}")
    if case.project_id != data.project_id:
        raise HTTPException(400, "project_id 与用例所属项目不一致")
    obj = _svc_call(svc.create_dataset, db, project_id=data.project_id, case_id=data.case_id,
                    name=data.name, user_id=user.id, description=data.description)
    crud.log_operation(db, user, "create", "dataset", obj.id, obj.name)
    return _fill_extra(db, obj)


@router.post("/{dataset_id}/copy", response_model=schemas.DataSetOut)
def copy(dataset_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """复制数据集：行内全部节点入参配置深拷贝，归属同用例（多场景复用方式）"""
    obj = _svc_call(svc.copy_dataset, db, dataset_id, user_id=user.id)
    crud.log_operation(db, user, "create", "dataset", obj.id, f"copy from #{dataset_id}")
    return _fill_extra(db, obj)


@router.get("/{dataset_id}", response_model=schemas.DataSetOut)
def get(dataset_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    return _fill_extra(db, _get_or_404(db, dataset_id))


@router.put("/{dataset_id}", response_model=schemas.DataSetOut)
def update(dataset_id: int, data: schemas.DataSetUpdate, db: Session = Depends(get_db),
           user: models.User = Depends(get_current_user)):
    obj = _get_or_404(db, dataset_id)
    obj = _svc_call(svc.update_dataset, db, dataset_id, name=data.name, description=data.description)
    obj.updated_by = user.id
    db.commit()
    crud.log_operation(db, user, "update", "dataset", obj.id, obj.name)
    return _fill_extra(db, obj)


@router.delete("/{dataset_id}")
def delete(dataset_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    obj = _get_or_404(db, dataset_id)
    _svc_call(svc.delete_dataset, db, dataset_id)
    crud.log_operation(db, user, "delete", "dataset", obj.id, obj.name)
    return {"message": "已删除"}


@router.get("/{dataset_id}/params-view", response_model=schemas.DatasetParamsViewOut)
def params_view(dataset_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """参数视图：按归属用例 DAG 节点组织（数据集页节点 tab 数据源）。

    - nodes：画布节点 × 接口字段定义（fields）× 行内现值（params）
      × 静态产出（productions：参数路径 ∪ 末段别名 ∪ 提取名——引用下拉数据源）
    - edges：画布连线（前端计算各节点上游引用分组）
    - orphan_node_ids：行内已配置但画布已删的节点（提示清理）
    """
    from ..engine.validation import _productions

    ds = _get_or_404(db, dataset_id)
    case = _owner_case(db, ds)
    # 节点 tab 顺序 = 画布阅读序（从上到下、同行从左到右）：dag_config.nodes 数组序是
    # 创建序，与画布视觉不一致（用例 177 实测），数据集页按 y 主序 x 次序展示
    def _read_pos(n: dict) -> tuple[float, float]:
        p = n.get("position")
        if not isinstance(p, dict):
            return (0.0, 0.0)
        return (float(p.get("y") or 0), float(p.get("x") or 0))

    dag_nodes = sorted(_dag_nodes(case.dag_config), key=_read_pos)
    dag_node_ids = {n["id"] for n in dag_nodes}

    struct = {c.node_id: c for c in db.query(models.CaseNodeConfig)
              .filter(models.CaseNodeConfig.case_id == case.id).all()}
    api_ids = {c.api_id for c in struct.values() if c.api_id}
    apis = {a.id: a for a in db.query(models.ApiDefinition)
            .filter(models.ApiDefinition.id.in_(api_ids)).all()} if api_ids else {}
    nodes_cfg = svc.node_configs(svc.row_data(ds))

    nodes_out: list[schemas.DatasetNodeView] = []
    for n in dag_nodes:
        nid = n["id"]
        c = struct.get(nid)
        rc = nodes_cfg.get(nid) or {}
        api = apis.get(c.api_id) if (c and c.api_id) else None
        # ORM ApiField → dict（fields 声明为 list[dict]，直接传 ORM 对象序列化会 500）
        api_fields = [schemas.ApiFieldOut.model_validate(f).model_dump()
                      for f in (api.fields or [])] if api else []
        prods = _productions({"params": rc.get("params") or {},
                              "post_extract": (c.post_extract if c else None) or []})
        label = nid
        if isinstance(n.get("data"), dict) and n["data"].get("label"):
            label = str(n["data"]["label"])
        nodes_out.append(schemas.DatasetNodeView(
            node_id=nid, label=label,
            api_id=(c.api_id if c else None),
            api_name=(f"{api.method} {api.path}" if api else ""),
            fields=api_fields,
            params=rc.get("params") or {},
            productions=sorted(prods),
        ))

    edges = [{"source": e.get("source"), "target": e.get("target")}
             for e in (case.dag_config or {}).get("edges", []) if isinstance(e, dict)]
    orphan = sorted(nid for nid in nodes_cfg if nid not in dag_node_ids)
    return schemas.DatasetParamsViewOut(
        dataset_id=ds.id, case_id=case.id, nodes=nodes_out, edges=edges,
        orphan_node_ids=orphan,
    )


@router.put("/{dataset_id}/node-config", response_model=schemas.DataSetOut)
def save_node_config(dataset_id: int, data: schemas.DataSetNodeConfigSave,
                     db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """保存单节点入参配置（整体替换该节点的 params，含静态校验）。"""
    ds = _get_or_404(db, dataset_id)
    _ensure_owner_not_running(db, ds, "保存节点入参配置")
    case = _owner_case(db, ds)
    dag_node_ids = {n["id"] for n in _dag_nodes(case.dag_config)}
    if data.node_id not in dag_node_ids:
        raise HTTPException(400, f"节点 {data.node_id} 不在用例编排中（可能已被删除，请刷新页面）")
    # 静态校验：行内其他节点现值 + 本节点新值 组装全量载荷（引用拓扑/悬空/依赖环）
    payload = _build_validation_payload(db, case, ds,
                                        override={data.node_id: {"params": data.params}})
    errs = validate_case_configs(case.dag_config, payload)
    if errs:
        raise HTTPException(400, "；".join(errs[:20]))
    obj = _svc_call(svc.save_node_config, db, dataset_id, data.node_id,
                    data.params, user_id=user.id)
    crud.log_operation(db, user, "update", "dataset", dataset_id,
                       f"node-config {data.node_id} ({len(data.params.get('body') or {})} 参数)")
    return _fill_extra(db, obj)


@router.delete("/{dataset_id}/node-config/{node_id}", response_model=schemas.DataSetOut)
def remove_node_config(dataset_id: int, node_id: str,
                       db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """清理悬空节点配置（画布节点已删，行内配置不再被执行）。"""
    ds = _get_or_404(db, dataset_id)
    _ensure_owner_not_running(db, ds, "清理节点入参配置")
    obj = _svc_call(svc.remove_node_config, db, dataset_id, node_id, user_id=user.id)
    crud.log_operation(db, user, "update", "dataset", dataset_id, f"remove node-config {node_id}")
    return _fill_extra(db, obj)

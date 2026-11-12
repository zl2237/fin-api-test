"""用例导入服务：消费导出 v2 迁移包（export_service.export_cases_json），无损重建用例。

匹配策略（尽量复用目标项目已有资产，缺什么补什么）：
- 接口：项目内 (method, path) 匹配 → 复用；未命中用节点 api_snapshot 重建（code 自动生成避撞，
  字段表全量回放）
- 环境：不导出（含密钥）；导入时统一 env_id 覆盖绑定（不传则不绑定，执行前需手动配置）
- 数据集：全量重建（行含节点入参配置集），按导出时绑定名回绑 dataset_id
- 契约模板绑定不随迁移（模板属项目级资产，跨项目 id 无意义）：导入后为 NULL（隐式全量字段），
  逐节点出警告提示重绑

v1 导出文件（无 version 字段）缺环境绑定与接口快照，明确拒绝并提示重新导出。
dry_run=True 只做匹配统计（只读不落库），前端先预览再确认导入。
整批单事务：任一用例失败全部回滚，不留半批脏数据。
（与 fin-ui-test 同构，裁剪了 UI 元素/自定义动作/页面域标签部分。）
"""
import re

from sqlalchemy.orm import Session

from .. import models


class ImportPayloadError(ValueError):
    """载荷不合法（非本平台导出 / v1 旧版 / 结构残缺）——路由转 400。"""


def _validate_payload(payload) -> dict:
    if not isinstance(payload, dict):
        raise ImportPayloadError("导入内容需为 JSON 对象（平台导出的用例 JSON 文件）")
    if payload.get("type") != "cases":
        raise ImportPayloadError("仅支持「用例导出 JSON」文件（type=cases），当前文件不是用例导出件")
    version = payload.get("version")
    if version != 2:
        if version is None:
            raise ImportPayloadError(
                "这是旧版（v1）导出文件：缺少环境绑定与接口定义快照，"
                "无法无损导入。请在源平台升级后重新导出，再导入此文件")
        raise ImportPayloadError(f"不支持的导出版本 v{version}（当前支持 v2）")
    items = payload.get("items")
    if not isinstance(items, list) or not items:
        raise ImportPayloadError("导出文件中没有用例（items 为空）")
    return payload


def _gen_api_code(db: Session, method: str, path: str) -> str:
    """为快照重建的接口生成全局唯一 code：imported_{method}_{path slug}，撞码加序号。"""
    slug = re.sub(r"[^0-9a-zA-Z]+", "_", path or "api").strip("_")[:60] or "api"
    base = f"imported_{method.lower()}_{slug}"[:100]
    code, n = base, 1
    while db.query(models.ApiDefinition).filter(models.ApiDefinition.code == code).first():
        n += 1
        code = f"{base}_{n}"
    return code


def _plan_apis(db: Session, payload: dict, project_id: int) -> tuple[dict, list[str]]:
    """接口匹配预演（只读）：{(method, path): (snapshot, target_id_or_None)} + 警告。"""
    warnings: list[str] = []
    api_by_mp = {(a.method.upper(), a.path): a.id
                 for a in db.query(models.ApiDefinition)
                 .filter(models.ApiDefinition.project_id == project_id).all()}
    apis: dict = {}
    for item in payload["items"]:
        for n in item.get("nodes") or []:
            snap = n.get("api_snapshot")
            src_api_id = n.get("api_id")
            if not snap:
                if src_api_id:
                    warnings.append(
                        f"用例「{item.get('name')}」节点 {n.get('id')} 引用的接口（源 id={src_api_id}）"
                        "在导出文件中无快照，导入后该节点不绑定接口")
                continue
            mp = ((snap.get("method") or "POST").upper(), snap.get("path"))
            if not mp[1]:
                warnings.append(f"接口快照残缺（path 缺失），已跳过：{snap.get('name')}")
                continue
            if mp not in apis:
                apis[mp] = (snap, api_by_mp.get(mp))
    return apis, warnings


def import_cases(db: Session, payload: dict, project_id: int, user_id: int | None = None, *,
                 group_id: int | None = None, env_id: int | None = None,
                 dry_run: bool = False) -> dict:
    """导入导出 v2 用例迁移包。dry_run=True 只统计不落库；否则整批单事务重建。

    group_id：导入用例统一分组（None=未分组）；env_id：统一环境绑定（None=不绑定）。
    """
    _validate_payload(payload)
    if not db.query(models.Project).get(project_id):
        raise ImportPayloadError(f"目标项目不存在: {project_id}")
    if group_id is not None and not db.query(models.CaseGroup).get(group_id):
        raise ImportPayloadError(f"目标分组不存在: {group_id}")
    if env_id is not None and not db.query(models.Environment).get(env_id):
        raise ImportPayloadError(f"指定环境不存在: {env_id}")

    apis, warnings = _plan_apis(db, payload, project_id)

    if dry_run:
        existing_names = {name for (name,) in db.query(models.TestCase.name)
                          .filter(models.TestCase.project_id == project_id).all()}
        case_rows = []
        for item in payload["items"]:
            name = item.get("name") or "（无名）"
            if name in existing_names:
                warnings.append(f"目标项目已存在同名用例「{name}」，导入会创建同名副本")
            nodes = item.get("nodes") or []
            case_rows.append({
                "name": name, "nodes": len(nodes), "ui_nodes": 0,
                "datasets": len(item.get("datasets") or []),
                "rows": sum(len(d.get("rows") or []) for d in (item.get("datasets") or [])),
            })
        return {
            "dry_run": True,
            "case_count": len(case_rows),
            "cases": case_rows,
            "reuse_apis": [f"{m} {p}" for (m, p), (_, tid) in apis.items() if tid],
            "create_apis": [f"{m} {p}" for (m, p), (_, tid) in apis.items() if not tid],
            "reuse_elements": [], "create_elements": [],
            "reuse_actions": [], "create_actions": [],
            "create_scope_labels": [],
            "warnings": warnings,
        }

    # ---- 接口先行：按快照重建缺失项（复用目标项目已有 (method, path)） ----
    api_id_by_mp: dict = {}
    created_apis = 0
    for (method, path), (snap, target_id) in apis.items():
        if target_id:
            api_id_by_mp[(method, path)] = target_id
            continue
        api_obj = models.ApiDefinition(
            project_id=project_id, name=snap.get("name") or path,
            code=_gen_api_code(db, method, path),
            method=method, path=path, description=snap.get("description"),
            request_template={}, headers_template={},
            created_by=user_id, updated_by=user_id)
        db.add(api_obj)
        db.flush()
        for f in snap.get("fields") or []:
            db.add(models.ApiField(
                api_id=api_obj.id, key=f["key"], label=f.get("label"),
                field_type=f.get("field_type", "string"), required=f.get("required", False),
                default_value=f.get("default_value"), remark=f.get("remark"),
                sort_order=f.get("sort_order", 0)))
        api_id_by_mp[(method, path)] = api_obj.id
        created_apis += 1

    # ---- 用例主体：TestCase + node_configs + datasets（单事务，最后统一 commit） ----
    case_ids: list[int] = []
    created_rows = 0
    dataset_total = 0
    for item in payload["items"]:
        case = models.TestCase(
            project_id=project_id, group_id=group_id,
            name=item.get("name") or "导入用例",
            description=item.get("description"),
            dag_config={"nodes": item.get("nodes") or [], "edges": item.get("edges") or []},
            env_id=env_id, created_by=user_id, updated_by=user_id)
        db.add(case)
        db.flush()
        case_ids.append(case.id)

        for n in item.get("nodes") or []:
            cfg = n.get("config")
            if not cfg:
                continue  # 源库该节点无配置行，保持一致
            snap = n.get("api_snapshot")
            api_id = None
            if snap and snap.get("path"):
                api_id = api_id_by_mp.get(((snap.get("method") or "POST").upper(), snap["path"]))
            if cfg.get("contract_template_id"):
                warnings.append(
                    f"用例「{item.get('name')}」节点 {n.get('id')} 的契约模板绑定不随迁移"
                    "（已置为隐式全量字段），请在导入后按目标项目模板重绑")
            db.add(models.CaseNodeConfig(
                case_id=case.id, node_id=n.get("id") or "", api_id=api_id,
                post_extract=cfg.get("post_extract") or [],
                assertions=cfg.get("assertions") or [],
                wait_after_ms=cfg.get("wait_after_ms") or 0))

        dataset_ids: dict[str, models.DataSet] = {}
        first_ds: models.DataSet | None = None
        for d in item.get("datasets") or []:
            ds = models.DataSet(
                project_id=project_id, case_id=case.id, name=d.get("name") or "导入数据集",
                description=d.get("description"), created_by=user_id, updated_by=user_id)
            db.add(ds)
            db.flush()
            dataset_ids[ds.name] = ds
            dataset_total += 1
            if first_ds is None:
                first_ds = ds
            for r in d.get("rows") or []:
                db.add(models.DataSetRow(
                    dataset_id=ds.id, row_index=r.get("row_index") or 0,
                    data=r.get("data") or {}))
                created_rows += 1
        # 绑定回放：导出的 bound_dataset_names 名单优先；旧包单名 dataset_name 兼容；
        # 都缺失时绑第一个（旧导出包无绑定信息的保底口径）
        bound_names: list[str] = list(item.get("bound_dataset_names") or [])
        legacy = item.get("dataset_name")
        if legacy and legacy not in bound_names:
            bound_names.append(legacy)
        bounds = [dataset_ids[n] for n in bound_names if n in dataset_ids]
        if not bounds and first_ds:
            bounds = [first_ds]
        for b in bounds:
            b.bound = True

    db.commit()
    return {
        "dry_run": False,
        "case_count": len(case_ids),
        "case_ids": case_ids,
        "created": {
            "cases": len(case_ids), "apis": created_apis,
            "elements": 0, "custom_actions": 0, "page_scope_labels": 0,
            "datasets": dataset_total, "rows": created_rows,
        },
        "reused": {
            "apis": sum(1 for _, (_, tid) in apis.items() if tid),
            "elements": 0, "custom_actions": 0,
        },
        "warnings": warnings,
    }

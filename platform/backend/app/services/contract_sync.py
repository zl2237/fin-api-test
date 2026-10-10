"""契约同步服务：数据集节点参数 与 接口字段 契约的一致性（2026-10-10 定案）。

契约唯一权威是接口管理（ApiField：key / field_type / default_value 示例值）；
参数侧是数据集行 nodes[节点ID].params.body 的参数路径集。两类出入：

- missing：接口字段存在，但参数侧无任何覆盖路径（自身或以其为前缀的参数
  皆无）→ 执行时按空值占位发送（「未配置即常量空」），同步则补 constant
- extra：参数路径的契约前缀链（自身/去尾前缀/子字段父级）均未命中接口
  字段 → 请求携带接口不认识的字段

同步红线（用户拍板 Q8）：非 constant 来源（ref/func/sql）参数一律不动——
extra 的动态参数只标注跳过，绝不删除。

示例值升格为元素/字段契约源（Q1/Q9-B）：同步补值时 object/array 字段按
示例值 JSON 结构拆叶子路径逐字段 constant（array 取首元素），标量示例值
还原原生类型（"5"→5）；无示例值按引擎空占位语义（string/file→""、
array→[]、其余→None）。

触发点（Q4 收窄两处）：接口更新保存 / 数据集节点保存，弹窗预览 + 用户
许可后同步所有引用数据集；执行时只检测标注不阻断（Q3），聚合进
record.summary.contract_gaps 供报告黄条展示。
"""
import json
from typing import Any

from sqlalchemy.orm import Session

from .. import models
from . import dataset_service


def _const(v: Any) -> dict:
    return {"source": "constant", "value": v}


def _scalar_from_text(text: Any) -> Any:
    """标量示例值文本 → 原生单值（"5"→5、"true"→true；容器/非法 JSON 保持文本）。"""
    if text is None:
        return ""
    if not isinstance(text, str):
        return text
    s = text.strip()
    if s == "":
        return ""
    try:
        v = json.loads(s)
    except (json.JSONDecodeError, TypeError):
        return text
    return text if isinstance(v, (dict, list)) else v


def _structure_leaves(obj: dict, prefix: str) -> dict[str, Any]:
    """dict 结构 → 叶子路径映射（嵌套 dict 递归；list 值整体保留原生 list——
    constant 支持容器值）。"""
    out: dict[str, Any] = {}
    for k, v in obj.items():
        p = f"{prefix}.{k}"
        if isinstance(v, dict):
            out.update(_structure_leaves(v, p))
        else:
            out[p] = v
    return out


def field_param_specs(field: Any) -> dict[str, dict]:
    """单个接口字段 → 初始参数 spec 集 {参数路径: constant spec}。

    - object / array（首元素为 dict）：示例值按结构拆叶子路径（array 取
      首元素并垫下标 0，Q9-B）
    - array 标量数组（有示例）：整字段 constant JSON 文本（引擎
      coerce_json_strings 会转回 list）；无示例 → 显式 []
    - string/file/int/bool：示例值还原原生类型；无示例按空占位语义
      （string/file → ""，int/bool → None）
    """
    key = getattr(field, "key", None)
    if not key:
        return {}
    ft = getattr(field, "field_type", None) or "string"
    dv = getattr(field, "default_value", None)

    struct: dict | None = None
    prefix = key
    if isinstance(dv, str) and dv.strip():
        try:
            parsed = json.loads(dv)
        except (json.JSONDecodeError, TypeError):
            parsed = None
        if ft == "object" and isinstance(parsed, dict):
            struct = parsed
        elif ft == "array" and isinstance(parsed, list):
            if parsed and isinstance(parsed[0], dict):
                struct = parsed[0]
                prefix = f"{key}.0"  # 元素参数垫首下标（Q9-B）
            elif parsed:
                return {key: _const(dv.strip())}  # 标量数组：整字段 JSON 文本
    if struct is not None:
        return {p: _const(v) for p, v in _structure_leaves(struct, prefix).items()}
    if ft == "array":
        return {key: _const([])}
    if ft in ("string", "file"):
        return {key: _const(_scalar_from_text(dv))}
    return {key: _const(None)}


def _fields(api_fields: Any) -> list[Any]:
    return [f for f in (api_fields or []) if getattr(f, "key", None)]


def _path_in_contract(path: str, field_keys: set[str]) -> bool:
    """参数路径是否落在契约内：自身/任意去尾前缀命中字段，或它是某字段
    路径的父级（嵌套字段 key 如 to_customer.put_amount 时，父级整体参数
    容器常量是合法写法）。"""
    segs = path.split(".")
    if any(".".join(segs[:i]) in field_keys for i in range(1, len(segs) + 1)):
        return True
    return any(k.startswith(path + ".") for k in field_keys)


def _covers_field(params: dict, field_key: str) -> bool:
    """字段是否已被参数覆盖：参数路径与字段 key 互为前缀即算（字段自身 /
    其叶子路径 / 嵌套字段 key 的父级整体容器常量均合法）。"""
    return any(p == field_key or p.startswith(field_key + ".")
               or field_key.startswith(p + ".") for p in params)


def node_contract_gaps(api_fields: Any, params_body: dict | None) -> dict:
    """单节点契约出入（执行黄条与同步预览/套用共用口径）。

    返回 {} 表示一致；有出入时 {"missing": [字段key...],
    "extra": [{"path", "source", "dynamic"}...]}。
    """
    fields = _fields(api_fields)
    if not fields:
        return {}  # 无字段契约（模板接口）：参数对齐 request_template，不比对
    field_keys = {f.key for f in fields}
    params = params_body or {}
    out: dict[str, Any] = {}
    missing = [f.key for f in fields
               if not _covers_field(params, f.key)]
    if missing:
        out["missing"] = missing
    extra = []
    for p in params:
        if _path_in_contract(p, field_keys):
            continue
        src = (params[p] or {}).get("source") if isinstance(params[p], dict) else None
        extra.append({"path": p, "source": src or "constant",
                      "dynamic": src in ("ref", "func", "sql")})
    if extra:
        out["extra"] = extra
    return out


def apply_node_sync(params_body: dict | None, api_fields: Any) -> tuple[dict, dict]:
    """按契约同步单节点 params.body，返回 (新 body, 统计)。

    missing 字段补 field_param_specs（示例值/空占位）；extra 参数仅
    constant 来源删除，动态来源（ref/func/sql）保留并计入 skipped_dynamic
    （红线 Q8：绝不改变动态来源参数）。
    """
    body = dict(params_body or {})
    fields = _fields(api_fields)
    stats = {"added": 0, "removed": 0, "skipped_dynamic": 0}
    if not fields:
        return body, stats  # 无字段契约（模板接口）：参数不动
    field_keys = {f.key for f in fields}
    for f in fields:
        if _covers_field(body, f.key):
            continue  # 已配置（字段粒度：部分叶子已配不重复补，元素补空由引擎兜底）
        for p, spec in field_param_specs(f).items():
            body[p] = spec
            stats["added"] += 1
    for p in list(body):
        if _path_in_contract(p, field_keys):
            continue
        src = (body[p] or {}).get("source") if isinstance(body[p], dict) else None
        if src == "constant":
            del body[p]
            stats["removed"] += 1
        else:
            stats["skipped_dynamic"] += 1
    return body, stats


# ============ 影响面与全量同步（接口 → 引用数据集节点） ============

def _node_label(dag_config: Any, node_id: str) -> str:
    dag = dag_config if isinstance(dag_config, dict) else {}
    for n in dag.get("nodes") or []:
        if isinstance(n, dict) and n.get("id") == node_id:
            return ((n.get("data") or {}).get("label") or node_id)
    return node_id


def _api_bindings(db: Session, api_id: int):
    """遍历接口的全部引用点：(case, dataset, node_id, params)。

    只走用例已绑定数据集的链路（未绑定无法执行，也无参数可同步）。
    """
    api = db.query(models.ApiDefinition).filter(models.ApiDefinition.id == api_id).first()
    if api is None:
        return
    binds = db.query(models.CaseNodeConfig).filter(
        models.CaseNodeConfig.api_id == api_id).all()
    if not binds:
        return
    case_ids = {b.case_id for b in binds}
    cases = {c.id: c for c in db.query(models.TestCase)
             .filter(models.TestCase.id.in_(case_ids)).all()}
    ds_ids = {c.dataset_id for c in cases.values() if getattr(c, "dataset_id", None)}
    dss = {}
    if ds_ids:
        for d in db.query(models.DataSet).filter(models.DataSet.id.in_(ds_ids)).all():
            dss[d.id] = d
    for b in binds:
        case = cases.get(b.case_id)
        ds = dss.get(getattr(case, "dataset_id", None)) if case else None
        if ds is None:
            continue
        nodes = dataset_service.node_configs(dataset_service.row_data(ds))
        rc = nodes.get(b.node_id) or {}
        yield api, case, ds, b.node_id, (rc.get("params") or {})


def api_contract_impact(db: Session, api_id: int) -> list[dict]:
    """接口契约变更影响面：所有引用该接口的（数据集, 节点）及各自出入
    （仅含有出入的引用点；无出入不列）。"""
    out = []
    for api, case, ds, node_id, params in _api_bindings(db, api_id):
        gaps = node_contract_gaps(api.fields, params.get("body"))
        if not gaps:
            continue
        out.append({
            "dataset_id": ds.id, "dataset_name": ds.name,
            "case_id": case.id, "case_name": case.name,
            "node_id": node_id, "node_label": _node_label(case.dag_config, node_id),
            "gaps": gaps,
        })
    return out


def sync_api_contract(db: Session, api_id: int, user_id: int | None = None) -> dict:
    """同步接口契约到所有引用数据集（逐节点 apply + 落库，幂等可重跑）。"""
    total = {"nodes": 0, "added": 0, "removed": 0, "skipped_dynamic": 0}
    details = []
    for api, case, ds, node_id, params in _api_bindings(db, api_id):
        new_body, stats = apply_node_sync(params.get("body"), api.fields)
        if new_body == dict(params.get("body") or {}):
            continue  # 实际无变化（如出入全是动态参数跳过）不落库不计数
        dataset_service.save_node_config(
            db, ds.id, node_id, {"body": new_body, **{k: v for k, v in params.items() if k != "body"}},
            user_id=user_id)
        total["nodes"] += 1
        total["added"] += stats["added"]
        total["removed"] += stats["removed"]
        total["skipped_dynamic"] += stats["skipped_dynamic"]
        details.append({"dataset_id": ds.id, "dataset_name": ds.name,
                        "node_id": node_id, **stats})
    return {"total": total, "details": details}

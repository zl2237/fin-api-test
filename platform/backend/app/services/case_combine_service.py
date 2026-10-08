"""用例组合（拼接）与拆分（抽离）服务。

组合（复制式）：
- 按给定顺序把多个源用例的 DAG 拼成一个新用例：节点 ID 加前缀重映射防冲突，
  节点结构配置整体复制；段间补 sink→entry 串接边强制先后（DAG 调度器对无依赖子图并行）。
- 数据集入参配置合并：各源绑定数据集行的 per-node 配置按节点 ID 重映射后
  合入新用例数据集（前缀保证节点不冲突）。

拆分（选节点抽离）：
- 前置扫描：找跨界引用（被抽离节点产出、留驻节点引用的变量，及反向），
  调用方拿扫描结果先让用户确认处置，再执行拆分。
- 执行：抽离节点 + 相关边 + 节点结构配置搬进新用例；原用例删节点删跨界边；
  数据集行内 per-node 配置按节点归属分流（各自只留自己的节点）。
"""
import re
from copy import deepcopy

from sqlalchemy.orm import Session

from .. import crud, models
from ..engine.variables import PLACEHOLDER_RE, extract_refs


def _spec_node_refs(obj) -> set[str]:
    """递归收集四来源 spec 内引用的节点 ID（ref/func arg + sql 占位 {{节点.变量}}；
    constant 容器值内嵌 spec 深扫——与 validation/引擎 iter_spec_refs 口径一致）。"""
    from ..engine.variables import iter_spec_refs
    return {str(node_id) for node_id, _vp in iter_spec_refs(obj) if node_id}


def _remap_spec_refs(obj, id_map: dict[str, str]):
    """递归重映射 spec 内引用的节点 ID（ref/func arg + sql 占位），返回新结构。"""
    if isinstance(obj, dict):
        src = obj.get("source")
        if src == "ref":
            nid = obj.get("node_id")
            if nid in id_map:
                return {**obj, "node_id": id_map[nid]}
            return obj
        if src == "func":
            args = [
                ({**a, "node_id": id_map[a["node_id"]]}
                 if isinstance(a, dict) and a.get("kind") == "ref" and a.get("node_id") in id_map else a)
                for a in (obj.get("args") or [])
            ]
            return {**obj, "args": args}
        if src == "sql":
            def _sub(m: "re.Match[str]") -> str:
                full = m.group(0)
                node_id, _, rest = full[2:-2].partition(".")
                return "{{" + id_map.get(node_id, node_id) + "." + rest + "}}" if rest else full
            return {**obj, "sql": PLACEHOLDER_RE.sub(_sub, obj.get("sql") or "")}
        if src == "constant":
            # 容器常量值内嵌 spec 同样重映射（与 _spec_node_refs 深扫口径一致）
            return {**obj, "value": _remap_spec_refs(obj.get("value"), id_map)}
        return {k: _remap_spec_refs(v, id_map) for k, v in obj.items()}  # 容器 dict
    if isinstance(obj, (list, tuple)):
        return type(obj)(_remap_spec_refs(v, id_map) for v in obj)
    return obj


def _remap_node_refs(nodes_cfg: dict, id_map: dict[str, str]) -> dict:
    """数据集行 per-node 配置整体重映射：外层节点键 + spec 内引用节点 ID。"""
    return {new_id: _remap_spec_refs(cfg, id_map)
            for new_id, cfg in nodes_cfg.items()}


def _entry_exit_ids(dag_config: dict) -> tuple[set, set]:
    """返回（入口节点集 = 无入边，出口节点集 = 无出边）"""
    nodes = [n["id"] for n in dag_config.get("nodes", [])]
    edges = dag_config.get("edges", [])
    has_in = {e["target"] for e in edges}
    has_out = {e["source"] for e in edges}
    entries = {n for n in nodes if n not in has_in}
    exits = {n for n in nodes if n not in has_out}
    return entries, exits

def combine_cases(db: Session, case_ids: list[int], name: str, group_id: int | None, user_id: int) -> models.TestCase:
    """按 case_ids 顺序拼接为新用例（复制式），返回已落库的新用例。"""
    if len(case_ids) < 2:
        raise ValueError("组合至少需要 2 个用例")
    if len(set(case_ids)) != len(case_ids):
        raise ValueError("组合的用例存在重复，请去重后再试")

    new_nodes: list[dict] = []
    new_edges: list[dict] = []
    # node_configs 载荷：[{node_id, api_id, post_extract, assertions, wait_after_ms}]
    config_payloads: list[dict] = []
    # 各源绑定数据集行的 per-node 入参配置（按 id_map 重映射后的键）
    remapped_nodes: list[dict] = []
    prev_exits: set[str] | None = None
    x_offset = 0  # 段间距：每段右移 420px，视觉分段
    project_id: int | None = None

    for idx, cid in enumerate(case_ids):
        case = crud.get_testcase(db, cid)
        if not case:
            raise ValueError(f"用例不存在: {cid}")
        if project_id is None:
            project_id = case.project_id
        elif case.project_id != project_id:
            raise ValueError(f"用例 #{cid} 与其他用例不属于同一项目，无法组合")
        cfg = case.dag_config or {"nodes": [], "edges": []}
        prefix = f"c{cid}_"
        id_map: dict[str, str] = {}
        seg_nodes: list[dict] = []
        for n in cfg.get("nodes", []):
            new_id = prefix + str(n["id"])
            id_map[n["id"]] = new_id
            pos = deepcopy(n.get("position") or {"x": 0, "y": 0})
            pos["x"] = (pos.get("x") or 0) + x_offset
            data = deepcopy(n.get("data") or {})
            seg_nodes.append({"id": new_id, "position": pos, "data": data})
        new_nodes.extend(seg_nodes)

        for e in cfg.get("edges", []):
            new_edges.append({
                "id": f"e_{id_map[e['source']]}_{id_map[e['target']]}",
                "source": id_map[e["source"]], "target": id_map[e["target"]],
            })

        cfg_map = {nc.node_id: nc for nc in (case.node_configs or [])}
        for old_id, new_id in id_map.items():
            nc = cfg_map.get(old_id)
            if nc:
                config_payloads.append({
                    "node_id": new_id, "api_id": nc.api_id,
                    "post_extract": deepcopy(nc.post_extract or []),
                    "assertions": deepcopy(nc.assertions or []),
                    "wait_after_ms": nc.wait_after_ms or 0,
                })

        # 源绑定数据集行的 per-node 入参配置：节点 ID 重映射（段间引用可跨段成立）
        if case.dataset_id:
            from . import dataset_service
            src_ds = crud.get_dataset(db, case.dataset_id)
            if src_ds:
                src_nodes = dataset_service.node_configs(dataset_service.row_data(src_ds))
                remapped = {id_map[k]: deepcopy(v) for k, v in src_nodes.items() if k in id_map}
                # 段内引用的节点 ID 同步重映射（spec ref / func arg / sql 占位）
                remapped = _remap_node_refs(remapped, id_map)
                remapped_nodes.append(remapped)

        # 段间串接：上一段所有出口 → 本段所有入口
        if prev_exits is not None:
            entries, _ = _entry_exit_ids(cfg)
            mapped_entries = {id_map[e] for e in entries if e in id_map}
            for s in prev_exits:
                for t in mapped_entries:
                    new_edges.append({"id": f"e_join_{s}_{t}", "source": s, "target": t})

        _, exits = _entry_exit_ids(cfg)
        prev_exits = {id_map[e] for e in exits if e in id_map}
        x_offset += 420

    data = {
        "project_id": project_id,
        "name": name,
        "group_id": group_id,
        "description": f"组合自用例 {' + '.join(str(c) for c in case_ids)}",
        "dag_config": {"nodes": new_nodes, "edges": new_edges},
        "node_configs": config_payloads,
    }
    obj = crud.create_testcase(db, crud.schemas.TestCaseCreate(**data), user_id)
    # 数据集合并：各源绑定数据集行的 per-node 入参配置（已重映射）合入新用例数据集
    # 并绑定（执行强绑定）；段前缀保证节点 ID 不冲突
    if remapped_nodes:
        from .dataset_service import create_dataset
        merged_nodes: dict = {}
        for seg in remapped_nodes:
            merged_nodes.update(seg)
        ds = create_dataset(db, project_id=project_id, case_id=obj.id,
                            name=f"{name}-数据", user_id=user_id,
                            rows_data=[{"nodes": merged_nodes}])
        obj.dataset_id = ds.id
        db.commit()
        db.refresh(obj)
    crud.fill_audit_names(db, obj)
    return obj


# ============ 拆分 ============

def _sql_ref_nodes(text) -> set[str]:
    """SQL/文本 {{节点.变量}} 占位引用的节点 ID 集"""
    if not isinstance(text, str):
        return set()
    return {node_id for node_id, _vp in extract_refs(text)}


def _rules_sql_ref_nodes(rules) -> set[str]:
    """断言/提取规则列表内 SQL 占位引用的节点 ID 集（与 validation 逐规则取 sql 同口径）"""
    out: set[str] = set()
    for rule in rules or []:
        if isinstance(rule, dict):
            out |= _sql_ref_nodes(rule.get("sql") or "")
    return out


def _extracted_vars(nc) -> set[str]:
    """节点配置 post_extract 里声明的变量名"""
    names: set[str] = set()
    for rule in (nc.post_extract or []):
        if isinstance(rule, dict):
            for key in ("as", "var", "name", "variable"):
                if rule.get(key):
                    names.add(str(rule[key]))
                    break
    return names


def scan_split_boundary(db: Session, case_id: int, node_ids: list[str]) -> dict:
    """拆分前置扫描：返回跨界引用清单，供用户确认处置。

    - outgoing：被抽离节点产出、留驻节点引用（不迁走则留驻方引用悬空）
    - incoming：留驻节点产出、被抽离节点引用
    每条含：变量名、产出节点（归属侧）、引用节点列表（另一侧）。

    引用收集口径（四来源参数模型）：数据集行内该节点 params 的
    spec 引用（ref/func arg/sql 占位）+ 节点结构配置（提取/断言）SQL 占位；
    产出集 = 提取名 ∪ 参数路径 ∪ 参数末段别名（与 validation._productions 一致）。
    """
    case = crud.get_testcase(db, case_id)
    if not case:
        raise ValueError(f"用例不存在: {case_id}")
    move_set = set(node_ids)
    cfg_map = {nc.node_id: nc for nc in (case.node_configs or [])}
    all_ids = {n["id"] for n in (case.dag_config or {}).get("nodes", [])}
    stay_set = all_ids - move_set

    # 数据集行内 per-node 入参配置（引用与产出都算）
    from . import dataset_service
    ds_nodes: dict[str, dict] = {}
    if case.dataset_id:
        ds = crud.get_dataset(db, case.dataset_id)
        if ds:
            ds_nodes = dataset_service.node_configs(dataset_service.row_data(ds))

    def _productions_of(nid: str) -> set[str]:
        out = _extracted_vars(cfg_map[nid]) if nid in cfg_map else set()
        rc = ds_nodes.get(nid) or {}
        for path in ((rc.get("params") or {}).get("body") or {}):
            out.add(path)
            if "*" not in path:
                out.add(path.rsplit(".", 1)[-1])
        return out

    # 每个节点的引用集合（引用了哪些节点）与产出集合
    refs_of: dict[str, set[str]] = {}
    ext_of: dict[str, set[str]] = {}
    for nid in all_ids:
        refs: set[str] = set()
        rc = ds_nodes.get(nid) or {}
        refs |= _spec_node_refs(rc.get("params"))
        nc = cfg_map.get(nid)
        if nc:
            refs |= _rules_sql_ref_nodes(getattr(nc, "assertions", None))
            refs |= _rules_sql_ref_nodes(getattr(nc, "post_extract", None))
        refs_of[nid] = refs & all_ids  # 只看画布内节点（伪命名空间无跨界概念）
        ext_of[nid] = _productions_of(nid)

    outgoing, incoming = [], []
    for nid in move_set:
        for ref_node in refs_of.get(nid, set()):
            # 引用的产出由留驻节点提供 → incoming（拆后引用悬空）
            if ref_node in stay_set:
                incoming.append({"var": ref_node, "providers": [ref_node], "consumer": nid})
    for nid in stay_set:
        for ref_node in refs_of.get(nid, set()):
            if ref_node in move_set:
                outgoing.append({"var": ref_node, "providers": [ref_node], "consumer": nid})

    return {"outgoing": outgoing, "incoming": incoming}


def split_case(
    db: Session, case_id: int, node_ids: list[str],
    new_name: str, new_group_id: int | None, user_id: int,
) -> tuple[models.TestCase, models.TestCase]:
    """执行拆分：抽离节点成新用例，原用例同步收缩。返回 (新用例, 更新后的原用例)。

    变量处置在调用方确认后已无动作可做（配置是纯 JSON 复制，引用原样保留）——
    所谓“随迁/留置”只是让用户知情：两边引用都会保留，断裂的由用户事后在编排页补。
    """
    case = crud.get_testcase(db, case_id)
    if not case:
        raise ValueError(f"用例不存在: {case_id}")
    cfg = case.dag_config or {"nodes": [], "edges": []}
    all_ids = {n["id"] for n in cfg.get("nodes", [])}
    # 传入的 node_ids 与实际节点取交集：全非法时拆不出任何东西，直接拒绝
    move_set = set(node_ids) & all_ids
    if not move_set:
        raise ValueError("选中节点均不存在于该用例")
    if move_set >= all_ids:
        raise ValueError("至少要保留一个节点在原用例")

    old_nodes = [n for n in cfg.get("nodes", []) if n["id"] not in move_set]
    new_nodes = [deepcopy(n) for n in cfg.get("nodes", []) if n["id"] in move_set]
    # 新用例节点位置归零（从原画布坐标平移到独立画布）
    if new_nodes:
        min_x = min((n.get("position") or {}).get("x", 0) for n in new_nodes)
        min_y = min((n.get("position") or {}).get("y", 0) for n in new_nodes)
        for n in new_nodes:
            pos = n.setdefault("position", {"x": 0, "y": 0})
            pos["x"] = (pos.get("x", 0) or 0) - min_x
            pos["y"] = (pos.get("y", 0) or 0) - min_y
    # 边按两端归属分流：跨界边丢弃
    old_edges, new_edges = [], []
    for e in cfg.get("edges", []):
        s, t = e["source"], e["target"]
        if s in move_set and t in move_set:
            new_edges.append(deepcopy(e))
        elif s not in move_set and t not in move_set:
            old_edges.append(e)

    cfg_map = {nc.node_id: nc for nc in (case.node_configs or [])}
    new_cfg_payloads: list[crud.schemas.NodeConfigIn] = []
    for n in new_nodes:
        nc = cfg_map.get(n["id"])
        if nc:
            new_cfg_payloads.append(crud.schemas.NodeConfigIn(
                node_id=n["id"], api_id=nc.api_id,
                post_extract=deepcopy(nc.post_extract or []),
                assertions=deepcopy(nc.assertions or []),
                wait_after_ms=nc.wait_after_ms or 0,
            ))

    assert case.project_id is not None  # 用例必然属于某项目
    new_case = crud.create_testcase(db, crud.schemas.TestCaseCreate(
        project_id=case.project_id,
        name=new_name, group_id=new_group_id,
        description=f"拆分自用例 #{case_id}",
        dag_config={"nodes": new_nodes, "edges": new_edges},
        node_configs=new_cfg_payloads,
    ), user_id)

    # 拆分是一致性操作：新用例已建（create_testcase 内部已 commit），
    # 原用例收缩失败时回滚删除新用例，避免两边各留一份节点
    try:
        updated = crud.update_testcase(db, case, crud.schemas.TestCaseUpdate(
            dag_config={"nodes": old_nodes, "edges": old_edges},
            node_configs=[crud.schemas.NodeConfigIn(
                node_id=nc.node_id, api_id=nc.api_id,
                post_extract=nc.post_extract or [],
                assertions=nc.assertions or [], wait_after_ms=nc.wait_after_ms or 0,
            ) for nc in (case.node_configs or []) if nc.node_id not in move_set],
        ), user_id)
    except Exception:
        db.query(models.TestCase).filter(models.TestCase.id == new_case.id).delete()
        db.commit()
        raise

    crud.fill_audit_names(db, new_case)
    crud.fill_audit_names(db, updated)
    # 数据资产分流：绑定数据集行内 per-node 入参配置按节点归属拆开——
    # 新用例克隆数据集（只留抽离节点配置）并绑定；原用例数据集删抽离节点配置。
    # 跨界引用两边都会保留原样，断裂的由用户事后在数据集页补（扫描已提示）。
    if case.dataset_id:
        from . import dataset_service
        src_ds = crud.get_dataset(db, case.dataset_id)
        if src_ds:
            src_nodes = dataset_service.node_configs(dataset_service.row_data(src_ds))
            move_cfg = {nid: deepcopy(cfg) for nid, cfg in src_nodes.items() if nid in move_set}
            if move_cfg:
                new_case.dataset_id = dataset_service.create_dataset(
                    db, project_id=case.project_id, case_id=new_case.id,
                    name=new_name, user_id=user_id,
                    rows_data=[{"nodes": move_cfg}]).id
                db.commit()
                db.refresh(new_case)
            for nid in move_set:
                if nid in src_nodes:
                    dataset_service.remove_node_config(db, case.dataset_id, nid, user_id=user_id)
    return new_case, updated

"""用例组合（拼接）与拆分（抽离）服务。

组合（复制式）：
- 按给定顺序把多个源用例的 DAG 拼成一个新用例：节点 ID 加前缀重映射防冲突，
  节点配置整体复制；段间补 sink→entry 串接边强制先后（DAG 调度器对无依赖子图并行）。
- 变量不做映射：执行器变量池是执行级共享（ExecutionContext.extracted），
  前段提取的变量后段天然可引用。

拆分（选节点抽离）：
- 前置扫描：找跨界变量（被抽离节点提取、留驻节点引用的变量，及反向），
  调用方拿扫描结果先让用户确认处置，再执行拆分。
- 执行：抽离节点 + 相关边 + 节点配置搬进新用例；原用例删节点删跨界边。
"""
import re
from copy import deepcopy

from sqlalchemy.orm import Session

from .. import crud, models

# 占位符 ${var} —— 与 engine/expression.py 的正则保持一致
_VAR_RE = re.compile(r"\$\{([^}]+)\}")


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
    # node_configs 载荷：[{node_id, api_id, pre_process, post_extract, assertions, wait_after_ms}]
    config_payloads: list[dict] = []
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
                    "pre_process": deepcopy(nc.pre_process or []),
                    "post_extract": deepcopy(nc.post_extract or []),
                    "assertions": deepcopy(nc.assertions or []),
                    "wait_after_ms": nc.wait_after_ms or 0,
                })

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
    crud.fill_audit_names(db, obj)
    return obj


# ============ 拆分 ============

def _collect_refs(value) -> set[str]:
    """递归收集 dict/list/str 里的 ${var} 引用（排除 ${uuid()} 等函数调用——带括号）"""
    refs: set[str] = set()
    if isinstance(value, str):
        for m in _VAR_RE.finditer(value):
            expr = m.group(1).strip()
            # context.x 兼容写法与函数调用不算变量引用
            if "(" not in expr and not expr.startswith("context."):
                refs.add(expr)
    elif isinstance(value, dict):
        for v in value.values():
            refs |= _collect_refs(v)
    elif isinstance(value, list):
        for v in value:
            refs |= _collect_refs(v)
    return refs


def _extracted_vars(nc) -> set[str]:
    """节点配置 post_extract 里声明的变量名（json_path 提取器的 as 键）"""
    names: set[str] = set()
    for rule in (nc.post_extract or []):
        if isinstance(rule, dict):
            for key in ("as", "var", "name", "variable"):
                if rule.get(key):
                    names.add(str(rule[key]))
                    break
    return names


def scan_split_boundary(db: Session, case_id: int, node_ids: list[str]) -> dict:
    """拆分前置扫描：返回跨界变量清单，供用户确认处置。

    - outgoing：被抽离节点提取、留驻节点引用（不迁走则留驻方引用悬空）
    - incoming：留驻节点提取、被抽离节点引用
    每条含：变量名、提取节点（归属侧）、引用节点列表（另一侧）。
    """
    case = crud.get_testcase(db, case_id)
    if not case:
        raise ValueError(f"用例不存在: {case_id}")
    move_set = set(node_ids)
    cfg_map = {nc.node_id: nc for nc in (case.node_configs or [])}
    all_ids = {n["id"] for n in (case.dag_config or {}).get("nodes", [])}
    stay_set = all_ids - move_set

    # 每个节点的引用集合与提取集合
    refs_of: dict[str, set[str]] = {}
    ext_of: dict[str, set[str]] = {}
    for nid in all_ids:
        nc = cfg_map.get(nid)
        if not nc:
            refs_of[nid], ext_of[nid] = set(), set()
            continue
        refs = set()
        refs |= _collect_refs(nc.pre_process)
        refs |= _collect_refs(nc.assertions)
        # post_extract 的 expected/value 里也可能引用既有变量
        refs |= _collect_refs(nc.post_extract)
        refs_of[nid] = refs
        ext_of[nid] = _extracted_vars(nc)

    outgoing, incoming = [], []
    for nid in move_set:
        for var in refs_of.get(nid, set()):
            # 引用的变量由留驻节点提取 → incoming
            providers = [s for s in stay_set if var in ext_of.get(s, set())]
            if providers:
                incoming.append({"var": var, "providers": providers, "consumer": nid})
    for nid in stay_set:
        for var in refs_of.get(nid, set()):
            providers = [m for m in move_set if var in ext_of.get(m, set())]
            if providers:
                outgoing.append({"var": var, "providers": providers, "consumer": nid})

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
    new_cfg_payloads = []
    for n in new_nodes:
        nc = cfg_map.get(n["id"])
        if nc:
            new_cfg_payloads.append({
                "node_id": n["id"], "api_id": nc.api_id,
                "pre_process": deepcopy(nc.pre_process or []),
                "post_extract": deepcopy(nc.post_extract or []),
                "assertions": deepcopy(nc.assertions or []),
                "wait_after_ms": nc.wait_after_ms or 0,
            })

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
            node_configs=[{
                "node_id": nc.node_id, "api_id": nc.api_id,
                "pre_process": nc.pre_process or [], "post_extract": nc.post_extract or [],
                "assertions": nc.assertions or [], "wait_after_ms": nc.wait_after_ms or 0,
            } for nc in (case.node_configs or []) if nc.node_id not in move_set],
        ), user_id)
    except Exception:
        db.query(models.TestCase).filter(models.TestCase.id == new_case.id).delete()
        db.commit()
        raise

    crud.fill_audit_names(db, new_case)
    crud.fill_audit_names(db, updated)
    return new_case, updated

"""编排结构指纹：续跑安全性的结构级锁定（断点续跑设计定稿）。

只锁「结构」：DAG 节点集合、边、节点-接口绑定（含 UI 节点占位）。
刻意不含参数配置（pre_process / post_extract / assertions / wait_after_ms）——
改参数后续跑用当前配置重新组装请求，正是「改完参数不用整个重跑」的
核心场景；锁了参数就等于把痛点原样保留。

结构变了（加删节点/改连线/换接口绑定）则时间线与上下文对不上，续跑拒绝。
"""
import hashlib
import json

from typing import Any


def compute_structure_fingerprint(dag_config: dict[str, Any] | None,
                                  node_bindings: list[tuple[str, Any]]) -> str:
    """计算编排结构指纹（sha256 前 32 hex）。

    :param dag_config: 用例 dag_config：{"nodes": [{"id": ...}], "edges": [...]}
    :param node_bindings: 各节点的结构级绑定 [(node_id, api_id_or_None), ...]，
                          UI 节点 api_id 为 None（仅以 node_id 参与结构）
    """
    dag = dag_config or {}
    nodes = sorted(str(n.get("id")) for n in dag.get("nodes", []) if isinstance(n, dict))
    edges = sorted(
        f"{e.get('source')}->{e.get('target')}"
        for e in dag.get("edges", []) if isinstance(e, dict)
    )
    bindings = sorted(f"{nid}:{'ui' if api is None else api}" for nid, api in node_bindings)
    payload = json.dumps({"nodes": nodes, "edges": edges, "bindings": bindings},
                         ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


def collect_node_bindings(db, case_id: int) -> list[tuple[str, Any]]:
    """收集用例各节点的结构级绑定（node_id, api_id）；无配置节点 api_id=None。

    与执行器 _resolve_node_config 同源（CaseNodeConfig 为编排唯一来源），
    供执行时算指纹与续跑前重算共用。
    """
    from .. import models

    rows = (db.query(models.CaseNodeConfig)
            .filter(models.CaseNodeConfig.case_id == case_id)
            .all())
    return [(r.node_id, r.api_id) for r in rows]

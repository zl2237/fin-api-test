"""DAG 拓扑序的唯一实现：Kahn 算法 + 节点 id 字典序入队。

执行顺序（dag_executor 按序执行节点）与收集口径（dataset_service 同名异值列
取业务链路源头节点的值）都依赖此序——入队稳定性若改变，两边同时生效，
不允许再出现平行第二份实现。
"""


def topo_order(dag: dict) -> tuple[list[str], list[str]]:
    """返回 (拓扑序, 未入序节点)。

    未入序节点 = 环上节点或入边指向不存在节点的节点（引擎不执行它们，
    收集侧扫一遍兜底）；边指向不存在节点时该边被忽略，不报错。
    """
    nodes = (dag or {}).get("nodes", [])
    edges = (dag or {}).get("edges", [])
    ids = [n["id"] for n in nodes]
    in_degree = {nid: 0 for nid in ids}
    adj: dict[str, list[str]] = {nid: [] for nid in ids}
    for e in edges:
        src, tgt = e.get("source"), e.get("target")
        if src in adj and tgt in in_degree:
            adj[src].append(tgt)
            in_degree[tgt] += 1
    # 保持稳定顺序：按节点 id 字典序入队
    queue = sorted([nid for nid, d in in_degree.items() if d == 0])
    order: list[str] = []
    while queue:
        nid = queue.pop(0)
        order.append(nid)
        for nxt in adj[nid]:
            in_degree[nxt] -= 1
            if in_degree[nxt] == 0:
                queue.append(nxt)
        queue.sort()
    leftover = [nid for nid in ids if nid not in order]
    return order, leftover

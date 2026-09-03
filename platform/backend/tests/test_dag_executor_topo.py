"""topo_order 单测：DAG 拓扑排序（engine 唯一实现，执行序与收集口径共用）。"""
from app.engine.topo import topo_order


def _dag(nodes, edges):
    """构造 DAG 字典"""
    return {
        "nodes": [{"id": n} for n in nodes],
        "edges": [{"source": s, "target": t} for s, t in edges],
    }


class TestTopoOrder:
    def test_empty_dag(self):
        order, leftover = topo_order({"nodes": [], "edges": []})
        assert order == []
        assert leftover == []

    def test_single_node(self):
        order, leftover = topo_order(_dag(["a"], []))
        assert order == ["a"]
        assert leftover == []

    def test_linear_chain(self):
        order, leftover = topo_order(_dag(["a", "b", "c"], [("a", "b"), ("b", "c")]))
        assert order == ["a", "b", "c"]
        assert leftover == []

    def test_parallel_branches(self):
        order, leftover = topo_order(_dag(["a", "b", "c"], [("a", "b"), ("a", "c")]))
        assert order == ["a", "b", "c"]
        assert leftover == []

    def test_diamond(self):
        order, leftover = topo_order(
            _dag(["a", "b", "c", "d"], [("a", "b"), ("a", "c"), ("b", "d"), ("c", "d")])
        )
        assert order == ["a", "b", "c", "d"]
        assert leftover == []

    def test_disconnected_nodes(self):
        order, leftover = topo_order(_dag(["a", "b"], []))
        assert order == ["a", "b"]
        assert leftover == []

    def test_cycle_detected(self):
        # a→b→a 环形，无法拓扑排序
        order, leftover = topo_order(_dag(["a", "b"], [("a", "b"), ("b", "a")]))
        assert order == []
        assert set(leftover) == {"a", "b"}

    def test_self_loop(self):
        order, leftover = topo_order(_dag(["a"], [("a", "a")]))
        assert order == []
        assert leftover == ["a"]

    def test_partial_cycle(self):
        # a→b→c→b 形成部分环，a 可执行，b/c 不可
        order, leftover = topo_order(
            _dag(["a", "b", "c"], [("a", "b"), ("b", "c"), ("c", "b")])
        )
        assert order == ["a"]
        assert set(leftover) == {"b", "c"}

    def test_stable_order(self):
        # 多个入度为0的节点，按 id 字典序入队
        order, leftover = topo_order(_dag(["c", "a", "b"], []))
        assert order == ["a", "b", "c"]

    def test_edge_to_unknown_node_ignored(self):
        # 边指向不存在的节点，应被忽略不报错
        order, leftover = topo_order(_dag(["a"], [("a", "ghost")]))
        assert order == ["a"]
        assert leftover == []

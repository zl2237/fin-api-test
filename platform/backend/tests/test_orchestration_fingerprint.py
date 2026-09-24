# -*- coding: utf-8 -*-
"""编排结构指纹测试：只锁结构（节点/边/接口绑定），参数配置不入指纹。"""
from app.engine.orchestration import compute_structure_fingerprint

DAG = {
    "nodes": [{"id": "n1"}, {"id": "n2"}, {"id": "n3"}],
    "edges": [{"source": "n1", "target": "n2"}, {"source": "n2", "target": "n3"}],
}
BINDINGS = [("n1", 10), ("n2", 20), ("n3", None)]  # n3 为 UI 节点


class TestStructureFingerprint:
    def test_stable_for_same_structure(self):
        """相同结构（含节点/边顺序打乱）指纹一致：排序归一"""
        a = compute_structure_fingerprint(DAG, BINDINGS)
        shuffled = {
            "nodes": [{"id": "n3"}, {"id": "n1"}, {"id": "n2"}],
            "edges": [{"source": "n2", "target": "n3"}, {"source": "n1", "target": "n2"}],
        }
        b = compute_structure_fingerprint(shuffled, list(reversed(BINDINGS)))
        assert a == b

    def test_adding_node_changes_fingerprint(self):
        """加节点（结构变更）→ 指纹变 → 续跑应拒绝"""
        dag2 = {"nodes": DAG["nodes"] + [{"id": "n4"}], "edges": DAG["edges"]}
        assert compute_structure_fingerprint(dag2, BINDINGS) != compute_structure_fingerprint(DAG, BINDINGS)

    def test_edge_change_changes_fingerprint(self):
        """改连线（结构变更）→ 指纹变"""
        dag2 = {"nodes": DAG["nodes"],
                "edges": [{"source": "n1", "target": "n3"}, {"source": "n3", "target": "n2"}]}
        assert compute_structure_fingerprint(dag2, BINDINGS) != compute_structure_fingerprint(DAG, BINDINGS)

    def test_api_rebind_changes_fingerprint(self):
        """换接口绑定（结构变更）→ 指纹变"""
        b2 = [("n1", 10), ("n2", 99), ("n3", None)]
        assert compute_structure_fingerprint(DAG, b2) != compute_structure_fingerprint(DAG, BINDINGS)

    def test_ui_node_none_vs_api_id_distinct(self):
        """UI 节点（None）与 api_id 存在的节点绑定可区分"""
        b2 = [("n1", 10), ("n2", 20), ("n3", 999)]
        assert compute_structure_fingerprint(DAG, b2) != compute_structure_fingerprint(DAG, BINDINGS)

    def test_empty_dag_fingerprint_defined(self):
        """空编排也有确定指纹（空用例执行写指纹，续跑无意义但不崩溃）"""
        fp = compute_structure_fingerprint(None, [])
        assert isinstance(fp, str) and len(fp) == 32

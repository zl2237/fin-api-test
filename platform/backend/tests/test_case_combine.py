"""case_combine_service 单测：组合（拼接）与拆分（抽离）。

用 SimpleNamespace 构造 ORM 替身 + mock crud 落库函数，不触真实数据库。
覆盖：ID 前缀重映射、段间串接边、配置复制、拒绝条件（重复/跨项目/全量/非法）、
跨界变量扫描（outgoing/incoming、函数调用与 context.x 排除）、失败回滚。
"""
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.services import case_combine_service as svc


def _node(id, x=0, y=0, label="n"):
    return {"id": id, "position": {"x": x, "y": y}, "data": {"label": label, "api_id": 1}}


def _edge(s, t):
    return {"id": f"e_{s}_{t}", "source": s, "target": t}


def _nc(node_id, api_id=1, pre=None, extract=None, asserts=None, wait=0):
    return SimpleNamespace(
        node_id=node_id, api_id=api_id,
        pre_process=pre or [], post_extract=extract or [],
        assertions=asserts or [], wait_after_ms=wait,
    )


def _case(cid, pid=1, nodes=None, edges=None, configs=None, name=None):
    return SimpleNamespace(
        id=cid, project_id=pid, name=name or f"用例{cid}", group_id=None,
        dag_config={"nodes": nodes or [], "edges": edges or []},
        node_configs=configs or [],
    )


def _fake_db():
    return SimpleNamespace()


class TestEntryExitIds:
    def test_linear(self):
        entries, exits = svc._entry_exit_ids({"nodes": [{"id": "a"}, {"id": "b"}], "edges": [{"source": "a", "target": "b"}]})
        assert entries == {"a"}
        assert exits == {"b"}

    def test_disconnected(self):
        entries, exits = svc._entry_exit_ids({"nodes": [{"id": "a"}, {"id": "b"}], "edges": []})
        assert entries == {"a", "b"}
        assert exits == {"a", "b"}


class TestCombineCases:
    def _run(self, cases, case_ids=None):
        """mock 掉 crud.get_testcase / create_testcase / fill_audit_names，跑组合并返回 (新用例载荷, 落库入参)"""
        cases_by_id = {c.id: c for c in cases}
        captured = {}

        def fake_get_testcase(db, cid):
            return cases_by_id.get(cid)

        def fake_create(db, data, user_id):
            payload = data.model_dump()  # data 是 TestCaseCreate schema，转 dict 便于断言
            captured["data"] = payload
            return SimpleNamespace(id=999, **payload)

        with patch.object(svc.crud, "get_testcase", side_effect=fake_get_testcase), \
             patch.object(svc.crud, "create_testcase", side_effect=fake_create), \
             patch.object(svc.crud, "fill_audit_names"):
            obj = svc.combine_cases(_fake_db(), case_ids or [c.id for c in cases], "组合", None, 1)
        return obj, captured["data"]

    def test_too_few_rejected(self):
        with pytest.raises(ValueError, match="至少需要 2 个"):
            svc.combine_cases(_fake_db(), [1], "x", None, 1)

    def test_duplicate_ids_rejected(self):
        with pytest.raises(ValueError, match="重复"):
            svc.combine_cases(_fake_db(), [7, 7], "x", None, 1)

    def test_missing_case_rejected(self):
        with patch.object(svc.crud, "get_testcase", return_value=None):
            with pytest.raises(ValueError, match="不存在"):
                svc.combine_cases(_fake_db(), [1, 2], "x", None, 1)

    def test_cross_project_rejected(self):
        c1 = _case(1, pid=1, nodes=[_node("a")])
        c2 = _case(2, pid=2, nodes=[_node("b")])
        cases = {1: c1, 2: c2}
        with patch.object(svc.crud, "get_testcase", side_effect=lambda db, cid: cases.get(cid)):
            with pytest.raises(ValueError, match="不属于同一项目"):
                svc.combine_cases(_fake_db(), [1, 2], "x", None, 1)

    def test_prefix_remapping_and_join_edge(self):
        """节点 ID 加前缀防冲突 + 段间出口→入口串接边"""
        c1 = _case(1, nodes=[_node("a"), _node("b")], edges=[_edge("a", "b")])
        c2 = _case(2, nodes=[_node("c"), _node("d")], edges=[_edge("c", "d")])
        _, data = self._run([c1, c2])

        ids = [n["id"] for n in data["dag_config"]["nodes"]]
        assert ids == ["c1_a", "c1_b", "c2_c", "c2_d"]
        # 段内边重映射 + 段间串接 b→c
        join = [e for e in data["dag_config"]["edges"] if e["id"].startswith("e_join_")]
        assert len(join) == 1
        assert join[0]["source"] == "c1_b" and join[0]["target"] == "c2_c"

    def test_configs_copied_with_new_ids(self):
        c1 = _case(1, nodes=[_node("a")], configs=[_nc("a", api_id=5, pre=[{"k": "v"}])])
        c2 = _case(2, nodes=[_node("b")], configs=[_nc("b", api_id=6)])
        _, data = self._run([c1, c2])
        by_node = {nc["node_id"]: nc for nc in data["node_configs"]}
        assert by_node["c1_a"]["api_id"] == 5
        assert by_node["c1_a"]["pre_process"] == [{"k": "v"}]
        assert by_node["c2_b"]["api_id"] == 6

    def test_positions_shifted_per_segment(self):
        """每段右移 420px 视觉分段"""
        c1 = _case(1, nodes=[_node("a", x=10)])
        c2 = _case(2, nodes=[_node("b", x=10)])
        _, data = self._run([c1, c2])
        pos = {n["id"]: n["position"]["x"] for n in data["dag_config"]["nodes"]}
        assert pos["c1_a"] == 10
        assert pos["c2_b"] == 10 + 420

    def test_project_id_from_first_source(self):
        c1 = _case(1, pid=3, nodes=[_node("a")])
        c2 = _case(2, pid=3, nodes=[_node("b")])
        _, data = self._run([c1, c2])
        assert data["project_id"] == 3


class TestCollectRefs:
    def test_plain_var(self):
        assert svc._collect_refs("prefix-${order_id}-suffix") == {"order_id"}

    def test_function_call_excluded(self):
        assert svc._collect_refs("${uuid()}") == set()

    def test_context_prefix_excluded(self):
        assert svc._collect_refs("${context.foo}") == set()

    def test_nested_structures(self):
        v = {"a": "${x}", "b": ["${y}", {"c": "${z}"}], "d": 123}
        assert svc._collect_refs(v) == {"x", "y", "z"}


class TestScanSplitBoundary:
    def _run(self, case, node_ids):
        with patch.object(svc.crud, "get_testcase", return_value=case):
            return svc.scan_split_boundary(_fake_db(), case.id, node_ids)

    def test_outgoing_and_incoming(self):
        """move 节点提取 order_id 被 stay 节点引用 → outgoing；
        stay 节点提取 token 被 move 节点引用 → incoming"""
        move_nc = _nc("m1", extract=[{"json_path": "$.id", "as": "order_id"}], pre=["${token}"])
        stay_nc = _nc("s1", extract=[{"json_path": "$.t", "as": "token"}], asserts=[{"expected": "${order_id}"}])
        case = _case(
            1,
            nodes=[_node("m1"), _node("s1")],
            configs=[move_nc, stay_nc],
        )
        result = self._run(case, ["m1"])
        assert {"var": "order_id", "providers": ["m1"], "consumer": "s1"} in result["outgoing"]
        assert {"var": "token", "providers": ["s1"], "consumer": "m1"} in result["incoming"]

    def test_no_boundary_when_clean(self):
        nc1 = _nc("m1", extract=[{"as": "x"}], pre=["${x}"])  # 自产自用
        nc2 = _nc("s1", extract=[{"as": "y"}], pre=["${y}"])
        case = _case(1, nodes=[_node("m1"), _node("s1")], configs=[nc1, nc2])
        result = self._run(case, ["m1"])
        assert result["outgoing"] == [] and result["incoming"] == []


class TestSplitCase:
    def _run(self, case, node_ids, fail_update=False):
        """mock 掉 crud 落库函数与 db 回滚删除，返回 (捕获载荷, 新用例)。fail_update=True 时断言抛错并返回。"""
        new_case = SimpleNamespace(id=888)
        updated_case = SimpleNamespace(id=case.id)
        captured = {}

        def fake_create(db, data, user_id):
            captured["create"] = data
            return new_case

        def fake_update(db, obj, data, user_id):
            if fail_update:
                raise RuntimeError("收缩失败")
            captured["update"] = data
            return updated_case

        class FakeQuery:
            def filter(self, *a, **k):
                def delete():
                    captured["deleted_new"] = True
                return SimpleNamespace(delete=delete)

        db = SimpleNamespace(query=lambda *a, **k: FakeQuery(), commit=lambda: None)

        with patch.object(svc.crud, "get_testcase", return_value=case), \
             patch.object(svc.crud, "create_testcase", side_effect=fake_create), \
             patch.object(svc.crud, "update_testcase", side_effect=fake_update), \
             patch.object(svc.crud, "fill_audit_names"):
            if fail_update:
                with pytest.raises(RuntimeError):
                    svc.split_case(db, case.id, node_ids, "新", None, 1)
                return captured, new_case
            new, origin = svc.split_case(db, case.id, node_ids, "新", None, 1)
            return captured, new, origin

    def _full_case(self):
        return _case(
            1,
            nodes=[_node("a", x=100, y=50), _node("b", x=300, y=150), _node("c", x=500, y=80)],
            edges=[_edge("a", "b"), _edge("b", "c")],
            configs=[_nc("a"), _nc("b", api_id=9), _nc("c")],
        )

    def test_all_invalid_ids_rejected(self):
        with patch.object(svc.crud, "get_testcase", return_value=self._full_case()):
            with pytest.raises(ValueError, match="均不存在"):
                svc.split_case(_fake_db(), 1, ["ghost"], "x", None, 1)

    def test_full_extract_rejected(self):
        case = self._full_case()
        with patch.object(svc.crud, "get_testcase", return_value=case):
            with pytest.raises(ValueError, match="至少要保留一个节点"):
                svc.split_case(_fake_db(), 1, ["a", "b", "c"], "x", None, 1)

    def test_split_partition_and_position_reset(self):
        """抽 a,b 留 c：新用例含 a/b+内部边+配置，位置归零；原用例收缩为 c"""
        case = self._full_case()
        captured, new, origin = self._run(case, ["a", "b"])

        create = captured["create"].model_dump()  # TestCaseCreate schema → dict
        assert [n["id"] for n in create["dag_config"]["nodes"]] == ["a", "b"]
        assert create["dag_config"]["edges"] == [{"id": "e_a_b", "source": "a", "target": "b"}]
        # 位置平移到 (0,0) 起点
        positions = [n["position"] for n in create["dag_config"]["nodes"]]
        assert positions[0] == {"x": 0, "y": 0}
        assert positions[1] == {"x": 200, "y": 100}
        assert {nc["node_id"] for nc in create["node_configs"]} == {"a", "b"}
        assert create["project_id"] == 1

        update = captured["update"]
        assert [n["id"] for n in update.dag_config["nodes"]] == ["c"]
        assert update.dag_config["edges"] == []  # 跨界边 a→b→c 均丢弃
        assert {nc.node_id for nc in update.node_configs} == {"c"}

    def test_update_failure_rolls_back_new_case(self):
        """原用例收缩失败 → 新用例被删除（不留双份节点）"""
        case = self._full_case()
        captured, new_case = self._run(case, ["a", "b"], fail_update=True)
        assert captured.get("deleted_new") is True
        assert captured.get("create") is not None  # 新用例确实建过

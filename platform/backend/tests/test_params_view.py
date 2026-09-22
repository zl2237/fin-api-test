"""build_params_view 单测：变量池界面数据源（按节点分组的入参清单）。

单套语义：数据集 = 一套数据；视图 = 归属用例当前编排 × 接口字段 × 池值，
manual 标记节点手动覆盖（编排非空值，池值不生效）。
"""
from types import SimpleNamespace
from unittest.mock import patch

from app import models
from app.services import dataset_service as svc


class _Query:
    def __init__(self, items):
        self._items = items

    def filter(self, *a, **k):
        return self

    def all(self):
        return list(self._items)


def _db(cfgs=(), apis=()):
    def query(model):
        if model is models.CaseNodeConfig:
            return _Query(cfgs)
        if model is models.ApiDefinition:
            return _Query(apis)
        return _Query([])

    return SimpleNamespace(query=query)


def _field(key, ftype="string"):
    return SimpleNamespace(key=key, field_type=ftype, default_value=None)


def _cfg(node_id, api_id, pre=None):
    return SimpleNamespace(node_id=node_id, api_id=api_id, pre_process=list(pre or []))


def _case(dataset_id=7):
    return SimpleNamespace(id=11, dataset_id=dataset_id, name="下单用例",
                           dag_config={"nodes": [{"id": "n1", "label": "下单"},
                                                 {"id": "n2", "label": "审单"}],
                                       "edges": [{"source": "n1", "target": "n2"}]})


def _ds(columns=None, row_data=None):
    return SimpleNamespace(id=7, case_id=11, columns=columns or [], node_configs=[],
                           rows=[SimpleNamespace(row_index=1, data=row_data or {})])


class TestBuildParamsView:

    def test_params_from_fields_refs_and_manual(self):
        """参数清单 = 接口字段 ∪ 空占位路径 ∪ 动态绑定 ∪ 手动覆盖（去重保序）"""
        cfg = _cfg("n1", 7, pre=[
            {"type": "set_field", "path": "ref_key", "value": ""},          # 自动引用占位
            {"type": "set_field", "path": "dyn_key", "value": "${gen()}"},  # 动态绑定
            {"type": "set_field", "path": "manual_key", "value": "X"},      # 手动覆盖
        ])
        api = SimpleNamespace(id=7, name="下单", fields=[_field("bl_no"), _field("voy")])
        ds = _ds(row_data={"bl_no": "BL001"})
        db = _db([cfg], [api])
        with patch.object(svc.crud, "get_dataset", return_value=ds), \
             patch.object(svc.crud, "get_testcase", return_value=_case()), \
             patch.object(svc.crud, "list_rows", return_value=ds.rows):
            view = svc.build_params_view(db, 7)

        assert [n["node_id"] for n in view["nodes"]] == ["n1"]
        node = view["nodes"][0]
        assert node["label"] == "下单" and node["api_name"] == "下单"
        keys = [p["key"] for p in node["params"]]
        assert keys == ["bl_no", "voy", "ref_key", "dyn_key", "manual_key"]
        by_key = {p["key"]: p for p in node["params"]}
        assert by_key["bl_no"]["value"] == "BL001"          # 池值
        assert by_key["voy"]["value"] == ""                  # 池无值 = 空态
        assert by_key["ref_key"]["manual"] is False          # 空占位 = 自动引用
        assert by_key["dyn_key"]["dynamic"] is True          # ${} = 动态绑定（非手动覆盖）
        assert by_key["dyn_key"]["manual"] is False
        assert by_key["dyn_key"]["manual_value"] == "${gen()}"
        assert by_key["manual_key"]["manual"] is True        # 字面量 = 手动覆盖
        assert by_key["manual_key"]["dynamic"] is False
        assert by_key["manual_key"]["manual_value"] == "X"

    def test_all_params_deduped_across_nodes(self):
        """用例级单池：跨节点同名键合并一份，状态取最强（手动覆盖 > 动态配置）"""
        cfg1 = _cfg("n1", 7, pre=[{"type": "set_field", "path": "k", "value": "${x}"}])
        cfg2 = _cfg("n2", 8, pre=[{"type": "set_field", "path": "k", "value": "MANUAL"},
                                  {"type": "set_field", "path": "only_n2", "value": "1"}])
        api7 = SimpleNamespace(id=7, name="下单", fields=[_field("k")])
        api8 = SimpleNamespace(id=8, name="审单", fields=[_field("k")])
        ds = _ds()
        db = _db([cfg1, cfg2], [api7, api8])
        with patch.object(svc.crud, "get_dataset", return_value=ds), \
             patch.object(svc.crud, "get_testcase", return_value=_case()), \
             patch.object(svc.crud, "list_rows", return_value=ds.rows):
            view = svc.build_params_view(db, 7)
        allp = {p["key"]: p for p in view["all_params"]}
        assert set(allp) == {"k", "only_n2"}  # 跨节点同名 k 只一份
        assert allp["k"]["manual"] is True
        assert allp["k"]["manual_value"] == "MANUAL"  # 手动覆盖压过动态绑定

    def test_field_type_and_inferred_type(self):
        """类型：接口字段类型优先；非字段参数回退列定义/推断"""
        cfg = _cfg("n1", 7, pre=[{"type": "set_field", "path": "extra", "value": ""}])
        api = SimpleNamespace(id=7, name="下单", fields=[_field("amount", "int")])
        ds = _ds(columns=[{"key": "extra", "type": "bool"}], row_data={"extra": True})
        db = _db([cfg], [api])
        with patch.object(svc.crud, "get_dataset", return_value=ds), \
             patch.object(svc.crud, "get_testcase", return_value=_case()), \
             patch.object(svc.crud, "list_rows", return_value=ds.rows):
            view = svc.build_params_view(db, 7)
        by_key = {p["key"]: p for p in view["nodes"][0]["params"]}
        assert by_key["amount"]["type"] == "int"
        assert by_key["extra"]["type"] == "bool"

    def test_required_flag_removed(self):
        """必填概念已取消：参数不再携带 required 字段"""
        cfg = _cfg("n1", 7)
        api = SimpleNamespace(id=7, name="下单", fields=[_field("bl_no")])
        ds = _ds()
        db = _db([cfg], [api])
        with patch.object(svc.crud, "get_dataset", return_value=ds), \
             patch.object(svc.crud, "get_testcase", return_value=_case()), \
             patch.object(svc.crud, "list_rows", return_value=ds.rows):
            view = svc.build_params_view(db, 7)
        assert "required" not in view["nodes"][0]["params"][0]
        assert "required" not in view["all_params"][0]

    def test_topo_order_and_labels(self):
        """节点按拓扑执行序排列，label 取 dag 节点 label"""
        cfg1 = _cfg("n1", 7)
        cfg2 = _cfg("n2", 8)
        api7 = SimpleNamespace(id=7, name="下单", fields=[_field("bl_no")])
        api8 = SimpleNamespace(id=8, name="审单", fields=[_field("audit_no")])
        ds = _ds()
        db = _db([cfg2, cfg1], [api7, api8])  # cfg 乱序，拓扑序仍 n1 → n2
        with patch.object(svc.crud, "get_dataset", return_value=ds), \
             patch.object(svc.crud, "get_testcase", return_value=_case()), \
             patch.object(svc.crud, "list_rows", return_value=ds.rows):
            view = svc.build_params_view(db, 7)
        assert [(n["node_id"], n["label"], n["api_name"]) for n in view["nodes"]] == [
            ("n1", "下单", "下单"), ("n2", "审单", "审单")]

    def test_orphan_keys_reported(self):
        """真悬空键才报告；前缀关联键（拆叶子键/整对象列）不算悬空——
        运行时按名前缀展开消费"""
        cfg = _cfg("n1", 7, pre=[{"type": "set_field", "path": "audit_msg", "value": ""}])
        api = SimpleNamespace(id=7, name="下单", fields=[_field("bl_no")])
        # 池值：真悬空 stale_key；拆叶子键 audit_msg.code 关联编排占位键 audit_msg
        ds = _ds(row_data={"bl_no": "BL1", "stale_key": "old", "audit_msg.code": "E1"})
        db = _db([cfg], [api])
        with patch.object(svc.crud, "get_dataset", return_value=ds), \
             patch.object(svc.crud, "get_testcase", return_value=_case()), \
             patch.object(svc.crud, "list_rows", return_value=ds.rows):
            view = svc.build_params_view(db, 7)
        assert view["orphan_keys"] == ["stale_key"]

    def test_dot_path_param_and_shared_key_across_nodes(self):
        """点路径字段成参数；跨节点同名键共享同一池值（各节点组都展示）"""
        cfg1 = _cfg("n1", 7)
        cfg2 = _cfg("n2", 8)
        api7 = SimpleNamespace(id=7, name="下单", fields=[_field("to_customer.put_amount", "int")])
        api8 = SimpleNamespace(id=8, name="审单", fields=[_field("to_customer.put_amount", "int"),
                                                          _field("bl_no")])
        ds = _ds(row_data={"to_customer.put_amount": 9, "bl_no": "BL9"})
        db = _db([cfg1, cfg2], [api7, api8])
        with patch.object(svc.crud, "get_dataset", return_value=ds), \
             patch.object(svc.crud, "get_testcase", return_value=_case()), \
             patch.object(svc.crud, "list_rows", return_value=ds.rows):
            view = svc.build_params_view(db, 7)
        n1 = view["nodes"][0]
        n2 = view["nodes"][1]
        assert n1["params"][0]["key"] == "to_customer.put_amount"
        assert n1["params"][0]["value"] == 9
        assert {p["key"]: p["value"] for p in n2["params"]}["bl_no"] == "BL9"

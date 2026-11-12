# -*- coding: utf-8 -*-
"""用例生命周期与数据集资产随迁单测：复制随迁 / 拆分分流 / 组合合并。

数据资产 = 数据集行内 per-node 入参配置（{"nodes": {...}}）；派生用例
（复制/拆分/组合产出）不同步数据集则节点引用解析不到值（执行报错）。
这里验证三条链路的资产流转（绑定 = DataSet.bound 标志，B3 多选定案）。
"""
from types import SimpleNamespace
from unittest.mock import patch

from app.services import case_combine_service as svc
from app.services import dataset_service as ds_svc
from app.crud import legacy


def _ds(did, data, name="池", bound=True):
    return SimpleNamespace(id=did, case_id=1, project_id=1, name=name,
                           description=None, bound=bound,
                           rows=[SimpleNamespace(row_index=1, data=data)])


class FakeDb:
    """最小 ORM 替身：按模型分流 query；add/commit/refresh 计数即可。"""

    def __init__(self, datasets=()):
        self._datasets = list(datasets)
        self._by_id = {d.id: d for d in self._datasets}
        self.added, self.commits = [], 0

    def query(self, model):
        parent = self

        class Q:
            def filter(self, *a, **k):
                return self

            def order_by(self, *a):
                return self

            def first(self):
                return None  # 用例重名查询恒无冲突

            def all(self):
                return parent._datasets

            def get(self, oid):
                return parent._by_id.get(oid)

        return Q()

    def add(self, obj):
        self.added.append(obj)

    def delete(self, obj):
        self.added = [a for a in self.added if a is not obj]

    def commit(self):
        self.commits += 1

    def refresh(self, obj):
        obj.id = getattr(obj, "id", None) or 777


def _node_cfg(node_id, api_id=1, extract=None, asserts=None, wait=0):
    """CaseNodeConfig 替身（结构层：入参配置收敛到数据集行，节点配置无 params）"""
    return SimpleNamespace(node_id=node_id, api_id=api_id,
                           post_extract=extract or [], assertions=asserts or [],
                           wait_after_ms=wait)


class TestCombineMergesDatasetConfigs:
    def test_sources_merged_and_bound(self):
        """组合：各源 bound 数据集行的 per-node 配置按节点 ID 重映射后
        并入新用例数据集（命名「组合名-数据」）并置 bound（执行强绑定）"""
        c1 = SimpleNamespace(id=1, project_id=1,
                             dag_config={"nodes": [{"id": "a"}], "edges": []}, node_configs=[])
        c2 = SimpleNamespace(id=2, project_id=1,
                             dag_config={"nodes": [{"id": "b"}], "edges": []}, node_configs=[])
        c3 = SimpleNamespace(id=3, project_id=1,  # 无 bound 数据集的源跳过
                             dag_config={"nodes": [{"id": "c"}], "edges": []}, node_configs=[])
        pools = {
            1: [_ds(11, {"nodes": {"a": {
                "params": {"body": {"x": {"source": "ref", "node_id": "a", "var_path": "x"}}}}}})],
            2: [_ds(22, {"nodes": {"b": {"params": {"body": {}}}}})],
            3: [],
        }
        new_case = SimpleNamespace(id=999)

        with patch.object(svc.crud, "get_testcase",
                          side_effect=lambda db, cid: {1: c1, 2: c2, 3: c3}.get(cid)), \
             patch.object(svc.crud, "list_bound_datasets",
                          side_effect=lambda db, cid: pools.get(cid, [])), \
             patch.object(svc.crud, "create_testcase", return_value=new_case), \
             patch.object(svc.crud, "fill_audit_names"), \
             patch.object(ds_svc, "create_dataset") as fake_create:
            fake_create.return_value = SimpleNamespace(id=501, bound=False)
            svc.combine_cases(FakeDb(), [1, 2, 3], "组合", None, 1)

        kw = fake_create.call_args.kwargs
        assert kw["case_id"] == 999 and kw["name"] == "组合-数据"
        nodes = kw["rows_data"][0]["nodes"]
        assert set(nodes) == {"c1_a", "c2_b"}  # 节点键按段前缀重映射
        # 段内 spec 引用的节点 ID 同步重映射（跨段引用链保持完整）
        assert nodes["c1_a"]["params"]["body"]["x"]["node_id"] == "c1_a"
        assert fake_create.return_value.bound is True  # 新数据集置 bound

    def test_multi_scene_sources_merge_by_scene_index(self):
        """多场景源组合：各源第 j 个 bound 数据集合并成新用例第 j 个（场景数取最大）"""
        c1 = SimpleNamespace(id=1, project_id=1,
                             dag_config={"nodes": [{"id": "a"}], "edges": []}, node_configs=[])
        pools = {1: [
            _ds(11, {"nodes": {"a": {"params": {"body": {"s": {"source": "constant", "value": 1}}}}}}, name="场景1"),
            _ds(12, {"nodes": {"a": {"params": {"body": {"s": {"source": "constant", "value": 2}}}}}}, name="场景2"),
        ]}
        created = []

        def fake_create(db, **kw):
            nd = SimpleNamespace(id=600 + len(created), bound=False)
            created.append((kw["name"], kw))
            return nd

        with patch.object(svc.crud, "get_testcase", return_value=c1), \
             patch.object(svc.crud, "list_bound_datasets", side_effect=lambda db, cid: pools[1]), \
             patch.object(svc.crud, "create_testcase",
                          return_value=SimpleNamespace(id=999)), \
             patch.object(svc.crud, "fill_audit_names"), \
             patch.object(ds_svc, "create_dataset", side_effect=fake_create):
            svc.combine_cases(FakeDb(), [1, 1 + 1], "组合", None, 1)

        assert [name for name, _ in created] == ["组合-数据", "组合-数据2"]
        assert created[0][1]["rows_data"][0]["nodes"]["c1_a"]["params"]["body"]["s"]["value"] == 1
        assert created[1][1]["rows_data"][0]["nodes"]["c2_a"]["params"]["body"]["s"]["value"] == 2


class TestSplitCarriesNodeConfigs:
    def test_new_case_gets_moved_configs_and_source_cleaned(self):
        """拆分：抽离节点的行内配置克隆进新用例数据集（保持原名）并置 bound；
        原用例各 bound 数据集删去抽离节点的配置（跨界断裂由用户事后在数据集页补）"""
        case = SimpleNamespace(
            id=5, project_id=1,
            dag_config={"nodes": [{"id": "a"}, {"id": "b"}],
                        "edges": [{"id": "e", "source": "a", "target": "b"}]},
            node_configs=[_node_cfg("a"), _node_cfg("b", api_id=9)],
        )
        cfg_a = {"params": {"body": {}}}
        cfg_b = {"params": {"body": {"x": {"source": "ref", "node_id": "a", "var_path": "v"}}}}
        pool = _ds(33, {"nodes": {"a": cfg_a, "b": cfg_b}}, name="源场景")
        new_case, updated = SimpleNamespace(id=888), SimpleNamespace(id=5)

        with patch.object(svc.crud, "get_testcase", return_value=case), \
             patch.object(svc.crud, "list_bound_datasets", return_value=[pool]), \
             patch.object(svc.crud, "create_testcase", return_value=new_case), \
             patch.object(svc.crud, "update_testcase", return_value=updated), \
             patch.object(svc.crud, "fill_audit_names"), \
             patch.object(ds_svc, "create_dataset") as fake_create, \
             patch.object(ds_svc, "remove_node_config") as fake_remove:
            fake_create.return_value = SimpleNamespace(id=502, bound=False)
            svc.split_case(FakeDb(), 5, ["b"], "拆出", None, 1)

        kw = fake_create.call_args.kwargs
        assert kw["case_id"] == 888 and kw["name"] == "源场景"  # 场景名随迁
        # 新用例数据集只含抽离节点的配置（值克隆）
        assert kw["rows_data"] == [{"nodes": {"b": cfg_b}}]
        assert fake_create.return_value.bound is True
        # 原用例数据集清理抽离节点配置
        fake_remove.assert_called_once()
        assert fake_remove.call_args.args[1:] == (33, "b")


class TestCopyCarriesDatasets:
    def test_all_pools_cloned_and_bound_flag_follows(self):
        """复制：名下全部数据集深拷贝（保持原名），bound 标志照搬（未绑定的保持未绑）"""
        case = SimpleNamespace(
            id=1, project_id=1, group_id=None, name="源", description=None,
            case_type="normal", dag_config={"nodes": [], "edges": []},
            shared_vars=None, node_configs=[],
        )
        ds_a, ds_b = _ds(65, {"nodes": {}}, name="场景A", bound=False), \
            _ds(66, {"nodes": {}}, name="场景B", bound=True)
        fake_db = FakeDb(datasets=[ds_a, ds_b])
        new_ids = iter(range(900, 910))

        def fake_clone(db, src, target_case_id, user_id=None):
            nd = SimpleNamespace(id=next(new_ids), bound=False)
            fake_db._by_id[nd.id] = nd
            return nd

        with patch.object(ds_svc, "clone_dataset_to_case", side_effect=fake_clone):
            legacy.copy_testcase(fake_db, case)

        assert fake_db._by_id[900].bound is False  # 源未绑定 → 克隆保持未绑
        assert fake_db._by_id[901].bound is True  # 源 bound → 克隆置 bound
        assert fake_db.commits >= 1


class TestDeleteDatasetGuard:
    """删除守卫：bound 数据集拒绝删除（先在「绑定数据集」取消勾选）；未绑定自由增删"""

    def _db_with(self, count):
        db = FakeDb(datasets=[SimpleNamespace(id=i) for i in range(count)])

        class Q:
            def filter(self, *a, **k):
                return self

            def count(self):
                return count

            def delete(self):
                pass

        db.query = lambda model: Q()
        return db

    def test_unbound_dataset_deletion_allowed(self):
        """未被勾选绑定的数据集（含名下仅剩一个）→ 照常删除"""
        pool = _ds(9, {"nodes": {}}, bound=False)
        pool.case_id = 5
        db = self._db_with(1)
        with patch.object(ds_svc, "get_dataset", return_value=pool):
            ds_svc.delete_dataset(db, 9)  # 不抛即放行
        assert db.commits == 1

    def test_bound_dataset_deletion_rejected(self):
        """bound 数据集 → 删除拒绝（提示先取消勾选）"""
        pool = _ds(9, {"nodes": {}}, bound=True)
        pool.case_id = 5
        db = self._db_with(3)
        with patch.object(ds_svc, "get_dataset", return_value=pool):
            try:
                ds_svc.delete_dataset(db, 9)
                raised = False
            except ValueError as e:
                raised = True
                assert "绑定" in str(e)
        assert raised and db.commits == 0

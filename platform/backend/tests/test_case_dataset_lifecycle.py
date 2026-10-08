"""用例生命周期与数据集资产随迁单测：复制随迁 / 拆分分流 / 组合合并。

数据资产 = 数据集行内 per-node 入参配置（{"nodes": {...}}）；派生用例
（复制/拆分/组合产出）不同步数据集则节点引用解析不到值（执行报错）。
这里验证三条链路的资产流转。

注：merge_datasets_for_case（变量池按列合并 + 冲突保首个）已随变量池概念
移除——组合合并改为行内 per-node 配置按节点 ID 重映射后并入新用例数据集
（见 TestCombineMergesDatasetConfigs），旧合并冲突语义用例已删除。
"""
from types import SimpleNamespace
from unittest.mock import patch

from app.services import case_combine_service as svc
from app.services import dataset_service as ds_svc
from app.crud import legacy


def _ds(did, data, name="池"):
    return SimpleNamespace(id=did, case_id=1, project_id=1, name=name,
                           description=None,
                           rows=[SimpleNamespace(row_index=1, data=data)])


class FakeDb:
    """最小 ORM 替身：按模型分流 query；add/commit/refresh 计数即可。"""

    def __init__(self, datasets=()):
        self._datasets = list(datasets)
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
        """组合：各源绑定数据集行的 per-node 配置按节点 ID 重映射后并入新用例
        数据集（命名「组合名-数据」）并绑定（执行强绑定）"""
        c1 = SimpleNamespace(id=1, project_id=1, dataset_id=11,
                             dag_config={"nodes": [{"id": "a"}], "edges": []}, node_configs=[])
        c2 = SimpleNamespace(id=2, project_id=1, dataset_id=22,
                             dag_config={"nodes": [{"id": "b"}], "edges": []}, node_configs=[])
        c3 = SimpleNamespace(id=3, project_id=1, dataset_id=None,  # 未绑定源跳过
                             dag_config={"nodes": [{"id": "c"}], "edges": []}, node_configs=[])
        pools = {
            11: _ds(11, {"nodes": {"a": {
                "params": {"body": {"x": {"source": "ref", "node_id": "a", "var_path": "x"}}}}}}),
            22: _ds(22, {"nodes": {"b": {"params": {"body": {}}}}}),
        }
        new_case = SimpleNamespace(id=999)

        with patch.object(svc.crud, "get_testcase",
                          side_effect=lambda db, cid: {1: c1, 2: c2, 3: c3}.get(cid)), \
             patch.object(svc.crud, "get_dataset", side_effect=lambda db, did: pools.get(did)), \
             patch.object(svc.crud, "create_testcase", return_value=new_case), \
             patch.object(svc.crud, "fill_audit_names"), \
             patch.object(ds_svc, "create_dataset") as fake_create:
            fake_create.return_value = SimpleNamespace(id=501)
            svc.combine_cases(FakeDb(), [1, 2, 3], "组合", None, 1)

        kw = fake_create.call_args.kwargs
        assert kw["case_id"] == 999 and kw["name"] == "组合-数据"
        nodes = kw["rows_data"][0]["nodes"]
        assert set(nodes) == {"c1_a", "c2_b"}  # 节点键按段前缀重映射
        # 段内 spec 引用的节点 ID 同步重映射（跨段引用链保持完整）
        assert nodes["c1_a"]["params"]["body"]["x"]["node_id"] == "c1_a"
        assert new_case.dataset_id == 501


class TestSplitCarriesNodeConfigs:
    def test_new_case_gets_moved_configs_and_source_cleaned(self):
        """拆分：抽离节点的行内配置克隆进新用例数据集并绑定；
        原用例数据集删去抽离节点的配置（跨界断裂由用户事后在数据集页补）"""
        case = SimpleNamespace(
            id=5, project_id=1, dataset_id=33,
            dag_config={"nodes": [{"id": "a"}, {"id": "b"}],
                        "edges": [{"id": "e", "source": "a", "target": "b"}]},
            node_configs=[_node_cfg("a"), _node_cfg("b", api_id=9)],
        )
        cfg_a = {"params": {"body": {}}}
        cfg_b = {"params": {"body": {"x": {"source": "ref", "node_id": "a", "var_path": "v"}}}}
        pool = _ds(33, {"nodes": {"a": cfg_a, "b": cfg_b}})
        new_case, updated = SimpleNamespace(id=888), SimpleNamespace(id=5)

        with patch.object(svc.crud, "get_testcase", return_value=case), \
             patch.object(svc.crud, "get_dataset", return_value=pool), \
             patch.object(svc.crud, "create_testcase", return_value=new_case), \
             patch.object(svc.crud, "update_testcase", return_value=updated), \
             patch.object(svc.crud, "fill_audit_names"), \
             patch.object(ds_svc, "create_dataset") as fake_create, \
             patch.object(ds_svc, "remove_node_config") as fake_remove:
            fake_create.return_value = SimpleNamespace(id=502)
            svc.split_case(FakeDb(), 5, ["b"], "拆出", None, 1)

        kw = fake_create.call_args.kwargs
        assert kw["case_id"] == 888 and kw["name"] == "拆出"
        # 新用例数据集只含抽离节点的配置（值克隆）
        assert kw["rows_data"] == [{"nodes": {"b": cfg_b}}]
        assert new_case.dataset_id == 502
        # 原用例数据集清理抽离节点配置
        fake_remove.assert_called_once()
        assert fake_remove.call_args.args[1:] == (33, "b")


class TestCopyCarriesDatasets:
    def test_all_pools_cloned_and_binding_follows(self):
        case = SimpleNamespace(
            id=1, project_id=1, group_id=None, name="源", description=None,
            case_type="normal", dag_config={"nodes": [], "edges": []},
            shared_vars=None, dataset_id=66,
            node_configs=[],
        )
        ds_a, ds_b = _ds(65, {"nodes": {}}), _ds(66, {"nodes": {}}, name="场景B")
        fake_db = FakeDb(datasets=[ds_a, ds_b])
        new_ids = iter(range(900, 910))

        def fake_clone(db, src, target_case_id, user_id=None):
            return SimpleNamespace(id=next(new_ids))

        with patch.object(ds_svc, "clone_dataset_to_case", side_effect=fake_clone):
            obj = legacy.copy_testcase(fake_db, case)

        assert obj.dataset_id == 901  # 绑定关系照搬：源绑 66（第二个）→ 克隆到 901
        assert fake_db.commits >= 1


class TestDeleteDatasetGuard:
    """删除守卫只剩「被用例绑定」拦截（名下最后一个数据集也可删——多数据集=多场景，自由增删）"""

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

    def test_last_dataset_deletion_allowed(self):
        """「至少保留一个数据集」守卫已废止：名下仅剩一个且未被绑定 → 照常删除"""
        pool = _ds(9, {"nodes": {}})
        pool.case_id = 5
        db = self._db_with(1)
        with patch.object(ds_svc, "get_dataset", return_value=pool), \
             patch.object(ds_svc.crud, "count_cases_bound_to_dataset", return_value=0):
            ds_svc.delete_dataset(db, 9)  # 不抛即放行
        assert db.commits == 1

    def test_multiple_datasets_allowed(self):
        pool = _ds(9, {"nodes": {}})
        pool.case_id = 5
        db = self._db_with(3)
        with patch.object(ds_svc, "get_dataset", return_value=pool), \
             patch.object(ds_svc.crud, "count_cases_bound_to_dataset", return_value=0):
            ds_svc.delete_dataset(db, 9)  # 名下 3 个，删除放行
        assert db.commits == 1

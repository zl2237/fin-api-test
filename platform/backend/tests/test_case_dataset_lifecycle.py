"""用例生命周期与数据集同步单测：复制随迁 / 拆分克隆 / 组合合并 / 合并函数语义。

静态值已收口进数据集变量池，派生用例（复制/拆分/组合产出）不同步池则
节点引用解析不到值（执行 400）。这里验证三条链路 + merge 函数的冲突语义。
"""
from types import SimpleNamespace
from unittest.mock import patch

from app.services import case_combine_service as svc
from app.services import dataset_service as ds_svc
from app.crud import legacy


def _ds(did, cols, data, name="池"):
    return SimpleNamespace(id=did, case_id=1, project_id=1, name=name,
                           description=None, columns=cols,
                           rows=[SimpleNamespace(data=data)])


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


class TestMergeDatasetsForCase:
    def _run(self, sources):
        captured = {}

        def fake_create(db, **kw):
            captured.update(kw)
            return SimpleNamespace(id=501, columns=kw.get("columns"),
                                   description=kw.get("description"),
                                   case_id=kw.get("case_id"))

        with patch.object(ds_svc, "create_dataset", side_effect=fake_create):
            merged = ds_svc.merge_datasets_for_case(FakeDb(), sources, 99, 1, name="组合-变量池")
        return merged, captured

    def test_union_keys_same_value_merged_conflict_keeps_first(self):
        s1 = _ds(1, [{"key": "a", "type": "string"}, {"key": "b", "type": "string"}],
                 {"a": "1", "b": "x"})
        s2 = _ds(2, [{"key": "b", "type": "string"}, {"key": "c", "type": "int"}],
                 {"b": "x", "c": 3})
        s3 = _ds(3, [{"key": "a", "type": "string"}], {"a": "9"})  # a 异值

        merged, kw = self._run([s1, s2, s3])

        assert [c["key"] for c in merged.columns] == ["a", "b", "c"]  # 首现顺序并集
        assert merged.case_id == 99
        assert kw["rows_data"] == [{"a": "1", "b": "x", "c": 3}]  # 同值合并/异值保首个
        assert "'9'" in merged.description  # 冲突清单可见

    def test_no_conflict_no_description(self):
        s1 = _ds(1, [{"key": "a", "type": "string"}], {"a": "1"})
        s2 = _ds(2, [{"key": "b", "type": "string"}], {"b": "2"})
        merged, kw = self._run([s1, s2])
        assert kw["rows_data"] == [{"a": "1", "b": "2"}]
        assert merged.description is None

    def test_all_sources_empty_returns_none(self):
        s = _ds(1, [], {})
        s.rows = []
        assert ds_svc.merge_datasets_for_case(FakeDb(), [s], 9, 1, name="x") is None


class TestCombineBindsMergedPool:
    def test_sources_merged_and_bound(self):
        c1 = SimpleNamespace(id=1, project_id=1, dataset_id=11,
                             dag_config={"nodes": [], "edges": []}, node_configs=[])
        c2 = SimpleNamespace(id=2, project_id=1, dataset_id=22,
                             dag_config={"nodes": [], "edges": []}, node_configs=[])
        c3 = SimpleNamespace(id=3, project_id=1, dataset_id=None,  # 无池源跳过
                             dag_config={"nodes": [], "edges": []}, node_configs=[])
        pools = {11: _ds(11, [{"key": "a", "type": "string"}], {"a": "1"}),
                 22: _ds(22, [{"key": "b", "type": "string"}], {"b": "2"})}
        new_case = SimpleNamespace(id=999)
        calls = {}

        def fake_merge(db, sources, target_case_id, project_id, name, user_id=None):
            calls["merge"] = ([s.id for s in sources], target_case_id, name)
            return SimpleNamespace(id=501)

        with patch.object(svc.crud, "get_testcase",
                          side_effect=lambda db, cid: {1: c1, 2: c2, 3: c3}.get(cid)), \
             patch.object(svc.crud, "get_dataset", side_effect=lambda db, did: pools.get(did)), \
             patch.object(svc.crud, "create_testcase", return_value=new_case), \
             patch.object(svc.crud, "fill_audit_names"), \
             patch.object(ds_svc, "merge_datasets_for_case", side_effect=fake_merge):
            svc.combine_cases(FakeDb(), [1, 2, 3], "组合", None, 1)

        assert calls["merge"] == ([11, 22], 999, "组合-变量池")
        assert new_case.dataset_id == 501


class TestSplitClonesBoundPool:
    def test_new_case_gets_clone_and_original_cleaned(self):
        case = SimpleNamespace(
            id=5, project_id=1, dataset_id=33,
            dag_config={"nodes": [{"id": "a"}, {"id": "b"}],
                        "edges": [{"id": "e", "source": "a", "target": "b"}]},
            node_configs=[SimpleNamespace(node_id="a", api_id=1, pre_process=[], post_extract=[],
                                          assertions=[], wait_after_ms=0),
                          SimpleNamespace(node_id="b", api_id=1, pre_process=[], post_extract=[],
                                          assertions=[], wait_after_ms=0)],
        )
        pool = _ds(33, [{"key": "a", "type": "string"}], {"a": "1"})
        new_case, updated = SimpleNamespace(id=888), SimpleNamespace(id=5)
        calls = {}

        def fake_clone(db, src, target_case_id, user_id=None):
            calls["clone"] = (src.id, target_case_id)
            return SimpleNamespace(id=502)

        with patch.object(svc.crud, "get_testcase", return_value=case), \
             patch.object(svc.crud, "get_dataset", return_value=pool), \
             patch.object(svc.crud, "create_testcase", return_value=new_case), \
             patch.object(svc.crud, "update_testcase", return_value=updated), \
             patch.object(svc.crud, "fill_audit_names"), \
             patch.object(ds_svc, "clone_dataset_to_case", side_effect=fake_clone), \
             patch.object(ds_svc, "sync_case_variable_pool") as fake_sync:
            svc.split_case(FakeDb(), 5, ["b"], "拆出", None, 1)

        assert calls["clone"] == (33, 888)
        assert new_case.dataset_id == 502
        fake_sync.assert_called_once()  # 原用例悬空清理被触发


class TestCopyCarriesDatasets:
    def test_all_pools_cloned_and_binding_follows(self):
        case = SimpleNamespace(
            id=1, project_id=1, group_id=None, name="源", description=None,
            case_type="normal", dag_config={"nodes": [], "edges": []},
            shared_vars=None, dataset_id=66,
            node_configs=[],
        )
        ds_a, ds_b = _ds(65, [{"key": "x", "type": "string"}], {"x": "1"}), _ds(66, [], {})
        fake_db = FakeDb(datasets=[ds_a, ds_b])
        new_ids = iter(range(900, 910))

        def fake_clone(db, src, target_case_id, user_id=None):
            return SimpleNamespace(id=next(new_ids))

        with patch.object(ds_svc, "clone_dataset_to_case", side_effect=fake_clone):
            obj = legacy.copy_testcase(fake_db, case)

        assert obj.dataset_id == 901  # 绑定关系照搬：源绑 66（第二个）→ 克隆到 901
        assert fake_db.commits >= 1


class TestDeleteLastDatasetGuard:
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

    def test_last_dataset_rejected(self):
        import pytest
        pool = _ds(9, [{"key": "a", "type": "string"}], {"a": "1"})
        pool.case_id = 5
        with patch.object(ds_svc, "get_dataset", return_value=pool), \
             patch.object(ds_svc.crud, "count_cases_bound_to_dataset", return_value=0):
            with pytest.raises(ValueError, match="至少需保留一个"):
                ds_svc.delete_dataset(self._db_with(1), 9)

    def test_multiple_datasets_allowed(self):
        pool = _ds(9, [{"key": "a", "type": "string"}], {"a": "1"})
        pool.case_id = 5
        db = self._db_with(3)
        with patch.object(ds_svc, "get_dataset", return_value=pool), \
             patch.object(ds_svc.crud, "count_cases_bound_to_dataset", return_value=0):
            ds_svc.delete_dataset(db, 9)  # 名下 3 个，删除放行
        assert db.commits == 1

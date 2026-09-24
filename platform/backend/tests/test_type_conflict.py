"""同名异型参数的变量池行为：池值清空（列保留），只允许节点手动覆盖。"""
from types import SimpleNamespace
from unittest.mock import patch

from app import models
from app.services import dataset_service as svc


class _Query:
    def __init__(self, items):
        self._items = items

    def filter(self, *a, **k):
        return self

    def order_by(self, *a, **k):
        return self

    def first(self):
        return self._items[0] if self._items else None

    def all(self):
        return list(self._items)


def _db(cfgs=(), apis=()):
    def query(model):
        if model is models.CaseNodeConfig:
            return _Query(cfgs)
        if model is models.ApiDefinition:
            return _Query(apis)
        return _Query([])

    added = []
    return SimpleNamespace(query=query, add=added.append, commit=lambda: None,
                           refresh=lambda o: None, flush=lambda: None), added


def _case(dataset_id=None, nodes=("n1", "n2")):
    return SimpleNamespace(id=11, project_id=1, dataset_id=dataset_id, name="下单",
                           dag_config={"nodes": [{"id": n} for n in nodes], "edges": [
                               {"source": "n1", "target": "n2"}]})


def _cfg(node_id, api_id, pre=None):
    return SimpleNamespace(node_id=node_id, api_id=api_id, pre_process=list(pre or []))


def _field(key, ftype="string", default=None):
    return SimpleNamespace(key=key, field_type=ftype, default_value=default)


def _api(api_id, fields=(), name="api"):
    return SimpleNamespace(id=api_id, name=name, fields=list(fields))


class TestTypeConflict:

    def test_string_vs_array_pool_emptied_literal_kept(self):
        """用户场景：A 节点 id=string 字面量 '1'，B 节点 id=array 字面量 [1]
        → 池不收 id；字面量两侧都保留为手动覆盖（不清空转引用）"""
        c1 = _cfg("n1", 7, pre=[{"type": "set_field", "path": "id", "value": "1"}])
        c2 = _cfg("n2", 8, pre=[{"type": "set_field", "path": "id", "value": [1]}])
        case = _case()
        db, added = _db([c1, c2], [
            _api(7, [_field("id", "string")]),
            _api(8, [_field("id", "array")]),
        ])

        stats = svc.sync_case_variable_pool(db, case, user_id=1)

        assert stats["type_conflicts"] == ["id"]
        assert not added  # 无新池（id 不入池，也无其他可收集值）
        assert c1.pre_process[0]["value"] == "1"   # 字面量保留
        assert c2.pre_process[0]["value"] == [1]   # 字面量保留

    def test_existing_pool_value_cleared_column_kept(self):
        """池已有 id 值（历史收集）→ 保存后行值清空、列保留"""
        c1 = _cfg("n1", 7)
        c2 = _cfg("n2", 8)
        case = _case(dataset_id=99)
        pool = SimpleNamespace(id=99, case_id=11,
                               columns=[{"key": "id", "type": "array"},
                                        {"key": "bl_no", "type": "string"}],
                               rows=[SimpleNamespace(row_index=1,
                                                     data={"id": ["1"], "bl_no": "B1"})])
        db, _ = _db([c1, c2], [
            _api(7, [_field("id", "string"), _field("bl_no")]),
            _api(8, [_field("id", "array")]),
        ])
        with patch.object(svc.crud, "get_dataset", return_value=pool):
            svc.sync_case_variable_pool(db, case, user_id=1)

        assert pool.rows[0].data == {"bl_no": "B1"}          # id 值清空
        assert {c["key"] for c in pool.columns} == {"id", "bl_no"}  # 列保留

    def test_default_values_not_collected_on_conflict(self):
        """接口默认值也不入池（string 默认 '1' / array 默认 ['1']）"""
        c1 = _cfg("n1", 7)
        c2 = _cfg("n2", 8)
        case = _case()
        db, added = _db([c1, c2], [
            _api(7, [_field("id", "string", "1")]),
            _api(8, [_field("id", "array", '["1"]'), _field("bl_no", "string", "B1")]),
        ])
        stats = svc.sync_case_variable_pool(db, case, user_id=1)

        pool = added[0]
        rows = [o for o in added if isinstance(o, models.DataSetRow)]
        assert {c["key"] for c in pool.columns} == {"bl_no"}  # id 不建列
        assert rows[0].data == {"bl_no": "B1"}
        assert stats["type_conflicts"] == ["id"]

    def test_same_type_across_nodes_still_collected(self):
        """两节点同类型（都是 string）不冲突，照常收集"""
        c1 = _cfg("n1", 7)
        c2 = _cfg("n2", 8)
        case = _case()
        db, added = _db([c1, c2], [
            _api(7, [_field("id", "string", "1")]),
            _api(8, [_field("id", "string")]),
        ])
        stats = svc.sync_case_variable_pool(db, case, user_id=1)

        rows = [o for o in added if isinstance(o, models.DataSetRow)]
        assert rows[0].data == {"id": "1"}
        assert stats["type_conflicts"] == []


class TestValueConflict:
    """同名不同值：不入池（各节点手动覆盖），池存量值清空、列保留"""

    def test_same_type_different_values_not_collected(self):
        """用户场景：A 节点 id='1'、B 节点 id='2'（同类型不同值）→ 都不入池，
        字面量两侧保留为手动覆盖（防经池串值）"""
        c1 = _cfg("n1", 7, pre=[{"type": "set_field", "path": "id", "value": "1"}])
        c2 = _cfg("n2", 8, pre=[{"type": "set_field", "path": "id", "value": "2"}])
        case = _case()
        db, added = _db([c1, c2], [
            _api(7, [_field("id", "string"), _field("bl_no", "string")]),
            _api(8, [_field("id", "string")]),
        ])
        c1.pre_process.append({"type": "set_field", "path": "bl_no", "value": "B1"})

        stats = svc.sync_case_variable_pool(db, case, user_id=1)

        assert stats["value_conflicts"] == ["id"]
        pool = added[0]
        rows = [o for o in added if isinstance(o, models.DataSetRow)]
        # id 不入池；bl_no（单值不冲突）正常收集建池
        assert {c["key"] for c in pool.columns} == {"bl_no"}
        assert rows[0].data == {"bl_no": "B1"}
        assert c1.pre_process[0]["value"] == "1"  # 字面量保留
        assert c2.pre_process[0]["value"] == "2"

    def test_existing_pool_value_cleared_on_value_conflict(self):
        """池已有值与字面量不同（非 force）→ 池值清空（列保留）"""
        cfg = _cfg("n1", 7, pre=[{"type": "set_field", "path": "id", "value": "9"}])
        case = _case(dataset_id=99)
        pool = SimpleNamespace(id=99, case_id=11,
                               columns=[{"key": "id", "type": "string"},
                                        {"key": "bl_no", "type": "string"}],
                               rows=[SimpleNamespace(row_index=1, data={"id": "1", "bl_no": "B1"})])
        db, _ = _db([cfg], [_api(7, [_field("id", "string"), _field("bl_no")])])
        with patch.object(svc.crud, "get_dataset", return_value=pool):
            stats = svc.sync_case_variable_pool(db, case, user_id=1)

        assert stats["value_conflicts"] == ["id"]
        assert pool.rows[0].data == {"bl_no": "B1"}  # id 清空
        assert {c["key"] for c in pool.columns} == {"id", "bl_no"}  # 列保留
        assert cfg.pre_process[0]["value"] == "9"  # 字面量保留

    def test_equal_values_across_nodes_still_collected(self):
        """两节点同值 → 不冲突（值相等收编语义保留），正常入池"""
        c1 = _cfg("n1", 7, pre=[{"type": "set_field", "path": "bl_no", "value": "B1"}])
        c2 = _cfg("n2", 8, pre=[{"type": "set_field", "path": "bl_no", "value": "B1"}])
        case = _case()
        db, added = _db([c1, c2], [
            _api(7, [_field("bl_no")]),
            _api(8, [_field("bl_no")]),
        ])
        stats = svc.sync_case_variable_pool(db, case, user_id=1)

        rows = [o for o in added if isinstance(o, models.DataSetRow)]
        assert rows[0].data == {"bl_no": "B1"}
        assert stats["value_conflicts"] == []

    def test_force_single_node_still_refreshes_pool(self):
        """force 收口（单节点池旧值刷新）不受值冲突拦截：池旧值是待刷新对象，
        不算'另一处取值'"""
        cfg = _cfg("n1", 7)
        case = _case(dataset_id=99)
        pool = SimpleNamespace(id=99, case_id=11,
                               columns=[{"key": "entrust_status", "type": "int"}],
                               rows=[SimpleNamespace(row_index=1, data={"entrust_status": 1})])
        db, _ = _db([cfg], [_api(7, [_field("entrust_status", "int", "2")])])
        with patch.object(svc.crud, "get_dataset", return_value=pool):
            stats = svc.sync_case_variable_pool(db, case, user_id=1, force=True)

        assert stats["value_conflicts"] == []
        assert pool.rows[0].data == {"entrust_status": 2}  # 收口刷新生效

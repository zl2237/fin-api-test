"""空集合默认值不入池 + array 空占位发 [] 的行为测试。"""
from types import SimpleNamespace

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


def _case(dataset_id=None):
    return SimpleNamespace(id=11, project_id=1, dataset_id=dataset_id, name="下单",
                           dag_config={"nodes": [{"id": "n1"}], "edges": []})


def _cfg(node_id="n1", api_id=7, pre=None):
    return SimpleNamespace(node_id=node_id, api_id=api_id, pre_process=list(pre or []))


def _field(key, ftype="string", default=None):
    return SimpleNamespace(key=key, field_type=ftype, default_value=default)


def _api(api_id=7, fields=(), name="下单"):
    return SimpleNamespace(id=api_id, name=name, fields=list(fields))


class TestEmptyCollectionDefaultNotCollected:
    def test_empty_array_default_skipped(self):
        """curl 抓包的空数组默认（audit: []）视为未配置，不入池（case 194 根因）"""
        cfg = _cfg()
        case = _case()
        db, added = _db([cfg], [_api(fields=[_field("audit", "array", "[]"),
                                             _field("bl_no", "string", "BL001")])])
        stats = svc.sync_case_variable_pool(db, case, user_id=1)
        pool = added[0]
        keys = {c["key"] for c in pool.columns}
        rows = [o for o in added if isinstance(o, models.DataSetRow)]
        assert keys == {"bl_no"}
        assert rows[0].data == {"bl_no": "BL001"}
        assert stats["columns"] == 1

    def test_empty_object_default_skipped(self):
        """空对象默认（{}）同样视为未配置"""
        cfg = _cfg()
        case = _case()
        db, added = _db([cfg], [_api(fields=[_field("extra", "object", "{}"),
                                             _field("bl_no", "string", "BL001")])])
        svc.sync_case_variable_pool(db, case, user_id=1)
        keys = {c["key"] for c in added[0].columns}
        assert keys == {"bl_no"}

    def test_nonempty_array_default_collected(self):
        """非空数组默认（["1"]）正常入池——形态不变"""
        cfg = _cfg()
        case = _case()
        db, added = _db([cfg], [_api(fields=[_field("ids", "array", '["1"]')])])
        svc.sync_case_variable_pool(db, case, user_id=1)
        rows = [o for o in added if isinstance(o, models.DataSetRow)]
        assert rows[0].data == {"ids": ["1"]}

    def test_empty_collection_literal_still_collected(self):
        """节点字面量空数组（用户显式配置发 []）仍收集——只拦接口默认值分支"""
        cfg = _cfg(pre=[{"type": "set_field", "path": "audit", "value": []}])
        case = _case()
        db, added = _db([cfg], [_api(fields=[_field("audit", "array")])])
        stats = svc.sync_case_variable_pool(db, case, user_id=1)
        rows = [o for o in added if isinstance(o, models.DataSetRow)]
        assert rows[0].data == {"audit": []}
        assert stats["columns"] == 1


class TestArrayEmptyPlaceholder:
    def test_array_field_empty_placeholder_is_empty_list(self):
        """三层皆空的 array 字段空占位发 []（PHP 空数组语义），不再是 null"""
        from app.engine.prepare_request import prepare_request
        from types import SimpleNamespace as NS

        api = NS(fields=[_field("audit", "array"), _field("bl_no", "string")],
                 request_template=None, headers_template=None)
        config = NS(pre_process=[])
        ctx = NS(to_dict=lambda: {"extracted": {}}, suite_vars=None)
        parts = prepare_request(api, config, context=ctx, row_vars=None,
                                base_headers={}, db_client=None)
        assert parts.body == {"audit": [], "bl_no": ""}

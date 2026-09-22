"""数据集复制与数据集间覆盖合并单测（copy_dataset / compare_datasets / merge_from_dataset）。

seam：services/dataset_service.py 公开函数（SimpleNamespace ORM 替身 + mock crud），
不触真实数据库。
"""
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.services import dataset_service as svc


def _fake_db():
    """带 query 链的空 db 替身（copy 重名查重等惰性查询返回空）"""
    return SimpleNamespace(query=lambda *a: SimpleNamespace(
        filter=lambda *b: SimpleNamespace(first=lambda: None)))


def _field(key, default=None, ftype="string", label=None):
    return SimpleNamespace(key=key, field_type=ftype, default_value=default, label=label)


def _cfg(node_id, api_id, pre=None, post=None, asserts=None, wait=0):
    return SimpleNamespace(node_id=node_id, api_id=api_id, pre_process=pre or [],
                           post_extract=post or [], assertions=asserts or [], wait_after_ms=wait)


# ============ 数据集复制 ============

class TestCopyDataset:
    def _ds(self):
        return SimpleNamespace(
            id=5, project_id=1, case_id=9, name="场景A",
            description="描述", columns=[{"key": "bl_no", "type": "string"}],
            rows=[SimpleNamespace(id=51, row_index=1, data={"bl_no": "B1"}),
                  SimpleNamespace(id=52, row_index=2, data={"bl_no": "B2"})],
        )

    def test_copy_deep_clones_all(self):
        """复制：列/单套值全量深拷贝，命名「原名-副本」，归属同用例"""
        src = self._ds()
        db = _fake_db()
        with patch.object(svc.crud, "get_dataset", return_value=src), \
             patch.object(svc, "create_dataset") as fake_create:
            fake_create.return_value = SimpleNamespace(id=21)
            cp = svc.copy_dataset(db, 5, user_id=1)
        kw = fake_create.call_args.kwargs
        assert kw["name"] == "场景A-副本"
        assert kw["case_id"] == 9 and kw["project_id"] == 1
        assert kw["columns"] == [{"key": "bl_no", "type": "string"}]
        assert kw["rows_data"] == [{"bl_no": "B1"}, {"bl_no": "B2"}]
        assert cp.id == 21

    def test_copy_missing_rejected(self):
        with patch.object(svc.crud, "get_dataset", return_value=None):
            with pytest.raises(ValueError, match="数据集不存在"):
                svc.copy_dataset(_fake_db(), 99, user_id=1)

    def test_copy_name_suffix_strips_old_suffix(self):
        """连续复制「副本」不叠后缀：场景A-副本 → 场景A-副本2"""
        src = self._ds()
        src.name = "场景A-副本"
        db = _fake_db()
        with patch.object(svc.crud, "get_dataset", return_value=src), \
             patch.object(svc, "create_dataset") as fake_create:
            fake_create.return_value = SimpleNamespace(id=22)
            svc.copy_dataset(db, 5, user_id=1)
        assert fake_create.call_args.kwargs["name"] == "场景A-副本2"


# ============ 数据集间对比与覆盖合并 ============

class TestCompareAndMerge:
    """对比按 api_id 配对归属用例当前编排的相同节点；可覆盖列=节点参数化列∩两侧数据集列。"""

    def _mk_env(self):
        """目标 bb（用例#2 编排 n1(api7)/n2(api8)）；源 aa（用例#1 编排 m1(api7)/m3(api9)）。
        api7 相同（可覆盖）；api9 目标没有（跳过）；api8 源没有（跳过）。"""
        t_ds = SimpleNamespace(
            id=101, name="bb", case_id=2, project_id=1,
            columns=[{"key": "bl_no", "type": "string"}, {"key": "teu", "type": "int"},
                     {"key": "only_b", "type": "string"}],
            rows=[SimpleNamespace(id=1, row_index=1, data={"bl_no": "B1", "teu": 1, "only_b": "keep"})],
        )
        s_ds = SimpleNamespace(
            id=202, name="aa", case_id=1, project_id=1,
            columns=[{"key": "bl_no", "type": "string"}, {"key": "teu", "type": "int"},
                     {"key": "only_a", "type": "string"}],
            rows=[SimpleNamespace(id=9, row_index=1, data={"bl_no": "A1", "teu": 9, "only_a": "x"})],
        )
        apis = {
            7: SimpleNamespace(id=7, name="新建订单",
                               fields=[_field("bl_no", "X"), _field("teu", "1", ftype="int"),
                                       _field("order_id", "${order_id}")]),
            8: SimpleNamespace(id=8, name="审核", fields=[_field("only_b", "v")]),
            9: SimpleNamespace(id=9, name="独有API", fields=[_field("only_a", "v")]),
        }
        # 归属用例的当前编排（_case_cfg_dicts 按 case_id 查询取这里）
        self.cfg_by_case = {
            1: [_cfg("m1", 7), _cfg("m3", 9)],
            2: [_cfg("n1", 7), _cfg("n2", 8)],
        }

        def fake_get(_self, pk):
            return apis.get(pk)

        db = SimpleNamespace(get=fake_get, query=self._fake_query, commit=lambda: None)
        return db, t_ds, s_ds, apis

    def _fake_query(self, model):
        from unittest.mock import ANY
        if getattr(model, "__name__", "") == "CaseNodeConfig":
            def by_case(expr=ANY):
                cid = getattr(getattr(expr, "right", None), "value", None)
                return SimpleNamespace(all=lambda: self.cfg_by_case.get(cid, []))
            return SimpleNamespace(filter=by_case)
        return SimpleNamespace(filter=lambda *a: SimpleNamespace(first=lambda: None))

    def test_compare_pairs_by_api_id(self):
        """相同 api_id 配对；可覆盖列=节点参数化列∩两侧列（动态注入列剔除）"""
        db, t_ds, s_ds, _ = self._mk_env()
        datasets = {101: t_ds, 202: s_ds}
        with patch.object(svc.crud, "get_dataset", side_effect=lambda _db, i: datasets[i]), \
             patch.object(svc.crud, "list_rows", return_value=s_ds.rows):
            out = svc.compare_datasets(db, 101, 202)
        assert [n["api_id"] for n in out["common_nodes"]] == [7]
        node = out["common_nodes"][0]
        assert node["api_name"] == "新建订单"
        assert node["columns"] == ["bl_no", "teu"]  # order_id 动态剔除，only_b/only_a 不交集
        assert out["columns_total"] == 2
        assert out["source"]["rows"] == 1

    def test_compare_no_common_nodes(self):
        """无相同节点 → common_nodes 空（前端提示无覆盖必要）"""
        db, t_ds, s_ds, _ = self._mk_env()
        self.cfg_by_case[1] = [self.cfg_by_case[1][1]]  # 源用例只剩独有 api9
        datasets = {101: t_ds, 202: s_ds}
        with patch.object(svc.crud, "get_dataset", side_effect=lambda _db, i: datasets[i]), \
             patch.object(svc.crud, "list_rows", return_value=s_ds.rows):
            out = svc.compare_datasets(db, 101, 202)
        assert out["common_nodes"] == [] and out["columns_total"] == 0

    def test_compare_same_dataset_rejected(self):
        db, _, _, _ = self._mk_env()
        with pytest.raises(ValueError, match="不能相同"):
            svc.compare_datasets(db, 1, 1)

    def _merge_db(self, apis, s_ds):
        def fake_query(model):
            name = getattr(model, "__name__", "")
            if name == "DataSetRow":
                return SimpleNamespace(filter=lambda *a, **k: SimpleNamespace(first=lambda: s_ds.rows[0]))
            if name == "CaseNodeConfig":
                def by_case(*a):
                    cid = getattr(getattr(a[0], "right", None), "value", None) if a else None
                    return SimpleNamespace(all=lambda: self.cfg_by_case.get(cid, []))
                return SimpleNamespace(filter=by_case)
            return SimpleNamespace(filter=lambda *a: SimpleNamespace(all=list))

        return SimpleNamespace(get=lambda _s, pk: apis.get(pk), query=fake_query, commit=lambda: None)

    def test_merge_overrides_common_columns_only(self):
        """合并：源同节点列值刷到目标；目标独有列保留；空值不覆盖"""
        db, t_ds, s_ds, apis = self._mk_env()
        s_ds.rows[0].data["only_a"] = "x"
        s_ds.rows[0].data["bl_no"] = ""  # 空值：不覆盖
        datasets = {101: t_ds, 202: s_ds}
        db = self._merge_db(apis, s_ds)
        with patch.object(svc.crud, "get_dataset", side_effect=lambda _db, i: datasets[i]), \
             patch.object(svc.crud, "list_rows", side_effect=lambda _db, i: s_ds.rows if i == 202 else t_ds.rows):
            result = svc.merge_from_dataset(db, 101, 202)
        assert result["columns"] == 1 and result["keys"] == ["teu"]
        assert t_ds.rows[0].data["teu"] == 9                    # teu 刷成源值
        assert t_ds.rows[0].data["bl_no"] == "B1"               # 源空值不覆盖
        assert t_ds.rows[0].data["only_b"] == "keep"            # 目标独有列保留

    def test_merge_selected_apis_only(self):
        """指定 api_ids 只刷所选节点列（不在相同节点列表内报错）"""
        db, t_ds, s_ds, apis = self._mk_env()
        datasets = {101: t_ds, 202: s_ds}
        db = self._merge_db(apis, s_ds)
        with patch.object(svc.crud, "get_dataset", side_effect=lambda _db, i: datasets[i]), \
             patch.object(svc.crud, "list_rows", side_effect=lambda _db, i: s_ds.rows if i == 202 else t_ds.rows):
            with pytest.raises(ValueError, match="不在相同节点列表"):
                svc.merge_from_dataset(db, 101, 202, api_ids=[8])

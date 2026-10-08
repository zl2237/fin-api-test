"""dataset_service 单测：数据集 CRUD + 单节点入参配置保存 + 删除级联。

seam：services/dataset_service.py 公开函数（SimpleNamespace ORM 替身 + mock crud 落库），
与 test_case_combine.py 同模式，不触真实数据库。

注：列 schema（columns）概念已随「入参收敛到数据集行」移除——行数据承载
{"nodes": {节点ID: {params}}}，列键合法性不再校验
（旧列校验用例已删除：重复列/非法列名/方括号键/行数据悬空列）。
"""
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app import models
from app.services import dataset_service as svc


def _fake_db():
    return SimpleNamespace()


# ============ 数据集 CRUD ============

class TestDatasetCrud:
    def test_create_dataset(self):
        """建数据集：基础字段落库；rows_data 原子写入（复制/克隆带行数据路径）"""
        added = []

        db = SimpleNamespace(add=added.append, flush=lambda: None,
                             commit=lambda: None, refresh=lambda o: None)
        ds = svc.create_dataset(db, project_id=1, case_id=9, name="运单数据", user_id=1,
                                rows_data=[{"nodes": {"n1": {"params": {}}}}])
        assert added[0] is ds and ds.name == "运单数据"
        assert ds.project_id == 1 and ds.case_id == 9
        assert added[1].row_index == 1
        assert added[1].data == {"nodes": {"n1": {"params": {}}}}

    def test_create_rejects_empty_name(self):
        """数据集名称不能为空"""
        with pytest.raises(ValueError, match="名称不能为空"):
            svc.create_dataset(_fake_db(), project_id=1, name="  ", user_id=1)

    def test_create_rejects_non_dict_row(self):
        """rows_data 元素必须是对象"""
        with pytest.raises(ValueError, match="必须是对象"):
            svc.create_dataset(SimpleNamespace(add=lambda o: None, flush=lambda: None),
                               project_id=1, name="坏行", user_id=1, rows_data=["x"])

    def test_update_dataset_rejects_empty_name(self):
        """改名传空串 → 拒绝"""
        ds = SimpleNamespace(id=1, name="旧名", description=None)
        with patch.object(svc.crud, "get_dataset", return_value=ds):
            with pytest.raises(ValueError, match="名称不能为空"):
                svc.update_dataset(_fake_db(), 1, name="  ")

    def test_delete_rejects_when_referenced_by_case(self):
        """数据集被用例绑定 → 删除拒绝"""
        with patch.object(svc.crud, "get_dataset", return_value=SimpleNamespace(id=1)), \
             patch.object(svc.crud, "count_cases_bound_to_dataset", return_value=2):
            with pytest.raises(ValueError, match="被 2 个用例绑定|先解绑"):
                svc.delete_dataset(_fake_db(), 1)

    def test_delete_cascades_rows(self):
        """删除数据集级联删行"""
        deleted = {}
        with patch.object(svc.crud, "get_dataset",
                          return_value=SimpleNamespace(id=1, case_id=5)), \
             patch.object(svc.crud, "count_cases_bound_to_dataset", return_value=0):
            db = SimpleNamespace(
                query=lambda *a, **k: SimpleNamespace(
                    filter=lambda *a, **k: SimpleNamespace(
                        count=lambda: 3,
                        delete=lambda: deleted.update(rows=True))),
                delete=lambda o: deleted.update(ds=True), commit=lambda: None,
            )
            svc.delete_dataset(db, 1)
        assert deleted.get("rows") is True and deleted.get("ds") is True


# ============ 删除级联（case_id 外键防 500） ============

class TestDeleteCascade:
    """数据集不在 Project/TestCase 的 ORM 级联链上（case_id FK RESTRICT），
    删用例/项目前须先清数据集及行——锁住 crud.delete_testcase / crud.delete_project 的清理顺序。"""

    def _db_spy(self, ds_ids):
        """替身 db：记录解绑/删行/删集/删宿主的顺序。
        query(DataSet).with_entities(DataSet.id) 拉归属列表；query(整模型) 链到 update/delete。"""
        calls = []

        class _Q:
            def __init__(self, target, id_col=False):
                self.target = target
                self.id_col = id_col or (target is models.DataSet.id)

            def filter(self, *a, **k):
                return self

            def with_entities(self, *ents):
                return _Q(ents[0] if ents else self.target, id_col=True)

            def all(self):
                return [(i,) for i in ds_ids] if self.id_col else []

            def update(self, values=None, synchronize_session=False):
                calls.append("unbind:TestCase")

            def delete(self, synchronize_session=False):
                calls.append(f"del:{getattr(self.target, '__name__', 'col')}")

        db = SimpleNamespace(
            query=lambda m: _Q(m),
            delete=lambda o: calls.append(f"del_host:{type(o).__name__}"),
            commit=lambda: calls.append("commit"),
        )
        return db, calls

    def test_delete_testcase_clears_its_datasets_first(self):
        """删用例：先解绑 → 删行 → 删数据集 → 删用例本体（外键安全顺序）"""
        from app.crud import legacy
        db, calls = self._db_spy(ds_ids=[7, 8])
        legacy.delete_testcase(db, SimpleNamespace(id=11))
        assert calls[:3] == ["unbind:TestCase", "del:DataSetRow", "del:DataSet"]
        assert len(calls) == 5 and calls[3].startswith("del_host:") and calls[4] == "commit"

    def test_delete_project_clears_project_datasets_first(self):
        """删项目：先清项目名下数据集（解绑+行+集），再删项目（走既有 ORM 级联）"""
        from app.crud import legacy
        db, calls = self._db_spy(ds_ids=[7])
        legacy.delete_project(db, SimpleNamespace(id=3))
        assert calls[:3] == ["unbind:TestCase", "del:DataSetRow", "del:DataSet"]
        assert calls[3].startswith("del_host:") and calls[-1] == "commit"

    def test_delete_testcase_without_datasets_skips_cleanup(self):
        """用例名下无数据集：不动 DataSet 表，直接删用例"""
        from app.crud import legacy
        db, calls = self._db_spy(ds_ids=[])
        legacy.delete_testcase(db, SimpleNamespace(id=11))
        assert calls == [calls[0], "commit"] and calls[0].startswith("del_host:")


# ============ 单节点入参配置保存（入参收敛到数据集行） ============

class TestSaveNodeConfig:
    """save_node_config：该节点的 params 整体替换写进数据集行"""

    def _fake_db(self, rows):
        """query(DataSetRow).filter().order_by().all() → rows；其余落库动作记录"""
        state = {"added": [], "commits": 0}

        class _RowQuery:
            def filter(self, *a, **k):
                return self

            def order_by(self, *a, **k):
                return self

            def all(self):
                return rows

        return SimpleNamespace(
            query=lambda *a, **k: _RowQuery(),
            add=state["added"].append,
            delete=lambda o: None,
            flush=lambda: None,
            commit=lambda: state.update(commits=state["commits"] + 1),
            refresh=lambda o: None,
        ), state

    def test_save_creates_row_when_absent(self):
        """数据集无行：自动建唯一一行（row_index=1），节点配置写进行内 nodes"""
        ds = SimpleNamespace(id=1, rows=[], updated_by=None)
        db, state = self._fake_db([])
        params = {"body": {"bl_no": {"source": "constant", "value": "BL1"}}}

        with patch.object(svc.crud, "get_dataset", return_value=ds):
            svc.save_node_config(db, 1, "n1", params, user_id=9)

        row = state["added"][0]
        assert row.row_index == 1
        assert row.data == {"nodes": {"n1": {"params": params}}}
        assert ds.updated_by == 9 and state["commits"] == 1

    def test_save_replaces_whole_node_config(self):
        """整体替换：该节点旧 params 不留残余，其他节点配置保留"""
        old_row = SimpleNamespace(dataset_id=1, row_index=1, data={"nodes": {
            "n1": {"params": {"body": {"old": {"source": "constant", "value": 1}}}},
            "n2": {"params": {"body": {}}},
        }})
        ds = SimpleNamespace(id=1, rows=[old_row], updated_by=None)
        db, state = self._fake_db([old_row])
        params = {"body": {"new": {"source": "ref", "node_id": "n0", "var_path": "v"}}}

        with patch.object(svc.crud, "get_dataset", return_value=ds):
            svc.save_node_config(db, 1, "n1", params, user_id=2)

        assert old_row.data["nodes"]["n1"] == {"params": params}
        assert "n2" in old_row.data["nodes"]  # 其他节点不受影响

    def test_empty_node_id_rejected(self):
        """node_id 为空 → 拒绝"""
        with pytest.raises(ValueError, match="node_id"):
            svc.save_node_config(_fake_db(), 1, "", {"body": {}})

    def test_spec_params_stored_verbatim(self):
        """四来源 spec（含点路径参数键 / 引用 / SQL 占位）按原样 JSON 落行，服务层不做值解析"""
        ds = SimpleNamespace(id=1, rows=[], updated_by=None)
        db, state = self._fake_db([])
        params = {"body": {
            "to_customer.put_amount": {"source": "constant", "value": 100},
            "oid": {"source": "ref", "node_id": "n_up", "var_path": "order_id"},
            "fee": {"source": "sql", "sql": "SELECT fee FROM t WHERE id={{n_up.oid}}"},
        }}

        with patch.object(svc.crud, "get_dataset", return_value=ds):
            svc.save_node_config(db, 1, "n1", params)

        assert state["added"][0].data["nodes"]["n1"]["params"] == params


# ============ 用例绑定校验（用例级隔离：只能绑自己名下的数据集） ============

class TestCaseBinding:
    def test_unbind_none_passes(self):
        """dataset_id=None（解绑/不绑）直接通过，不查库"""
        with patch.object(svc.crud, "get_dataset") as g:
            svc.validate_binding(_fake_db(), SimpleNamespace(id=1, project_id=1), None)
        g.assert_not_called()

    def test_bind_own_case_dataset_passes(self):
        """绑定本用例名下的数据集：通过"""
        case = SimpleNamespace(id=1, project_id=1)
        with patch.object(svc.crud, "get_dataset",
                          return_value=SimpleNamespace(id=7, project_id=1, case_id=1)):
            svc.validate_binding(_fake_db(), case, 7)  # 不抛即通过

    def test_bind_missing_dataset_rejected(self):
        """数据集不存在 → 拒"""
        with patch.object(svc.crud, "get_dataset", return_value=None):
            with pytest.raises(ValueError, match="数据集不存在"):
                svc.validate_binding(_fake_db(), SimpleNamespace(id=1, project_id=1), 99)

    def test_bind_other_case_dataset_rejected(self):
        """绑定别的用例的数据集 → 拒（用例间隔离，复用靠复制）"""
        case = SimpleNamespace(id=1, project_id=1)
        with patch.object(svc.crud, "get_dataset",
                          return_value=SimpleNamespace(id=7, project_id=1, case_id=2)):
            with pytest.raises(ValueError, match="其他用例|隔离"):
                svc.validate_binding(_fake_db(), case, 7)

"""dataset_service 单测：数据集 CRUD + 行操作 + 导入解析（数据驱动测试地基）。

seam：services/dataset_service.py 公开函数（SimpleNamespace ORM 替身 + mock crud 落库），
与 test_case_combine.py 同模式，不触真实数据库。
"""
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app import models
from app.services import dataset_service as svc

_COLS = [{"key": "bl_no", "type": "string"}, {"key": "put_amount", "type": "int"}]


def _fake_db():
    return SimpleNamespace()


# ============ 数据集 CRUD ============

class TestDatasetCrud:
    def test_create_dataset(self):
        """建数据集：列定义落库，返回对象"""
        captured = {}

        def fake_add(obj):
            captured["obj"] = obj

        db = SimpleNamespace(add=fake_add, commit=lambda: None, refresh=lambda o: None)
        ds = svc.create_dataset(db, project_id=1, name="运单数据", columns=[
            {"key": "bl_no", "label": "运单号", "type": "string"},
            {"key": "put_amount", "label": "放款金额", "type": "int"},
        ], user_id=1)
        assert captured["obj"].name == "运单数据"
        assert captured["obj"].project_id == 1
        assert [c["key"] for c in captured["obj"].columns] == ["bl_no", "put_amount"]
        assert ds is captured["obj"]

    def test_create_rejects_empty_columns(self):
        """数据集至少一列，空列拒绝"""
        with pytest.raises(ValueError, match="至少.*一列"):
            svc.create_dataset(_fake_db(), project_id=1, name="空", columns=[], user_id=1)

    def test_create_rejects_duplicate_column_keys(self):
        """列 key 重复拒绝（列名即变量名，重复会覆盖）"""
        with pytest.raises(ValueError, match="重复"):
            svc.create_dataset(_fake_db(), project_id=1, name="重复列", columns=[
                {"key": "bl_no", "type": "string"}, {"key": "bl_no", "type": "int"},
            ], user_id=1)

    def test_create_rejects_invalid_column_key(self):
        """列 key 不合法（空/空格/表达式符/非法段首）拒绝——点路径键合法（数据集模式）"""
        for bad in ["", "a b", "a${x}", "1abc", "a.1b", "a..b", ".a", "a."]:
            with pytest.raises(ValueError, match="列名.*合法|非法"):
                svc.create_dataset(_fake_db(), project_id=1, name="坏列", columns=[
                    {"key": bad, "type": "string"},
                ], user_id=1)

    def test_create_accepts_dot_path_column_key(self):
        """点路径键（嵌套参数拆叶，如 to_customer.put_amount）合法"""
        captured = {}
        db = SimpleNamespace(add=lambda o: captured.update(obj=o),
                             commit=lambda: None, refresh=lambda o: None)
        ds = svc.create_dataset(db, project_id=1, name="点路径列", columns=[
            {"key": "to_customer.put_amount", "type": "string"},
            {"key": "bl_no", "type": "string"},
        ], user_id=1)
        assert [c["key"] for c in ds.columns] == ["to_customer.put_amount", "bl_no"]

    def test_update_columns_rejects_in_use_key_change(self):
        """改列定义时若行数据含已删列 → 拒绝（防行数据悬空）"""
        ds = SimpleNamespace(id=1, columns=[{"key": "a", "type": "string"}, {"key": "b", "type": "string"}],
                             rows=[SimpleNamespace(row_index=1, data={"a": "1", "b": "2"})])
        with patch.object(svc.crud, "get_dataset", return_value=ds):
            with pytest.raises(ValueError, match="行数据仍使用|已删列"):
                svc.update_dataset(_fake_db(), 1, columns=[{"key": "a", "type": "string"}])

    def test_delete_rejects_when_referenced_by_case(self):
        """数据集被用例绑定 → 删除拒绝"""
        with patch.object(svc.crud, "get_dataset", return_value=SimpleNamespace(id=1)), \
             patch.object(svc.crud, "count_cases_bound_to_dataset", return_value=2):
            with pytest.raises(ValueError, match="被 2 个用例绑定|先解绑"):
                svc.delete_dataset(_fake_db(), 1)

    def test_delete_cascades_rows(self):
        """删除数据集级联删行（无引用且名下非最后一个时）"""
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


# ============ 单套值保存（每个数据集 = 一套数据） ============

class TestSaveValues:
    """save_dataset_values：values 即唯一一套值；列定义随参数走"""

    def _fake_db(self, added, bulk_deleted):
        class FakeQuery:
            def filter(self, *a, **k):
                return SimpleNamespace(delete=lambda: bulk_deleted.append(True))

        return SimpleNamespace(
            query=lambda *a, **k: FakeQuery(),
            add=lambda o: added.append(o),
            commit=lambda: None,
            refresh=lambda o: None,
        )

    def test_save_writes_single_row(self):
        """保存：旧行全删，落唯一一行（row_index=1），值即单套数据"""
        added, bulk_deleted = [], []
        ds = SimpleNamespace(id=1, columns=[{"key": "bl_no", "type": "string"}],
                             rows=[SimpleNamespace(row_index=1), SimpleNamespace(row_index=2)])
        db = self._fake_db(added, bulk_deleted)
        with patch.object(svc.crud, "get_dataset", return_value=ds):
            svc.save_dataset_values(db, 1, {"bl_no": "BL001", "amount": 5})
        assert len(bulk_deleted) == 1  # 存量多行就地收敛为单行
        assert len(added) == 1 and added[0].row_index == 1
        assert added[0].data == {"bl_no": "BL001", "amount": 5}

    def test_columns_follow_values(self):
        """列定义随参数走：现有列类型保留，新键按值推断补列，悬空旧键剔除"""
        added, bulk_deleted = [], []
        ds = SimpleNamespace(id=1, columns=[
            {"key": "bl_no", "type": "string"},          # 保留
            {"key": "stale", "type": "string"},          # 悬空剔除
            {"key": "amount", "type": "int"},            # 类型保留
        ], rows=[])
        db = self._fake_db(added, bulk_deleted)
        with patch.object(svc.crud, "get_dataset", return_value=ds):
            svc.save_dataset_values(db, 1, {"bl_no": "BL9", "amount": 7, "memo": "m"})
        assert ds.columns == [
            {"key": "bl_no", "type": "string"},
            {"key": "amount", "type": "int"},
            {"key": "memo", "type": "string"},  # 新键按值推断
        ]

    def test_invalid_key_rejected(self):
        """键不合法（无法成为变量名）→ 拒绝保存"""
        added, bulk_deleted = [], []
        ds = SimpleNamespace(id=1, columns=[], rows=[])
        db = self._fake_db(added, bulk_deleted)
        with patch.object(svc.crud, "get_dataset", return_value=ds):
            with pytest.raises(ValueError, match="列名.*合法|非法"):
                svc.save_dataset_values(db, 1, {"a b": "x"})
        assert bulk_deleted == [] and added == []  # 校验失败不动库

    def test_dot_path_key_accepted(self):
        """点路径键（嵌套参数拆叶）合法"""
        added, bulk_deleted = [], []
        ds = SimpleNamespace(id=1, columns=[], rows=[])
        db = self._fake_db(added, bulk_deleted)
        with patch.object(svc.crud, "get_dataset", return_value=ds):
            svc.save_dataset_values(db, 1, {"to_customer.put_amount": 100})
        assert added[0].data == {"to_customer.put_amount": 100}


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

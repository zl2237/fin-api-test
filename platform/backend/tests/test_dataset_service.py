"""dataset_service 单测：数据集 CRUD + 行操作 + 导入解析（数据驱动测试地基）。

seam：services/dataset_service.py 公开函数（SimpleNamespace ORM 替身 + mock crud 落库），
与 test_case_combine.py 同模式，不触真实数据库。
"""
import io
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
        """列 key 不合法（含点/空格/空/表达式符）拒绝——点号撞嵌套路径语法，空格撞表达式解析"""
        for bad in ["", "a.b", "a b", "a${x}", "1abc"]:
            with pytest.raises(ValueError, match="列名.*合法|非法"):
                svc.create_dataset(_fake_db(), project_id=1, name="坏列", columns=[
                    {"key": bad, "type": "string"},
                ], user_id=1)

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
        """删除数据集级联删行（无引用时）"""
        deleted = {}
        with patch.object(svc.crud, "get_dataset", return_value=SimpleNamespace(id=1)), \
             patch.object(svc.crud, "count_cases_bound_to_dataset", return_value=0):
            db = SimpleNamespace(
                query=lambda *a, **k: SimpleNamespace(filter=lambda *a, **k: SimpleNamespace(delete=lambda: deleted.update(rows=True))),
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


# ============ 行操作 ============

class TestRowOps:
    def test_add_row_appends_with_next_index(self):
        """增行：row_index 接现有最大值 +1"""
        ds = SimpleNamespace(id=1, columns=[{"key": "bl_no", "type": "string"}],
                             rows=[SimpleNamespace(row_index=3), SimpleNamespace(row_index=5)])
        added = {}

        def fake_add(obj):
            added["row"] = obj

        db = SimpleNamespace(add=fake_add, commit=lambda: None, refresh=lambda o: None)
        with patch.object(svc.crud, "get_dataset", return_value=ds):
            svc.add_row(db, 1, data={"bl_no": "BL006"})
        assert added["row"].row_index == 6
        assert added["row"].data == {"bl_no": "BL006"}

    def test_add_row_rejects_unknown_keys(self):
        """行数据 key 不在 columns → 拒绝"""
        ds = SimpleNamespace(id=1, columns=[{"key": "bl_no", "type": "string"}], rows=[])
        with patch.object(svc.crud, "get_dataset", return_value=ds):
            with pytest.raises(ValueError, match="未定义的列|bl_no2"):
                svc.add_row(_fake_db(), 1, data={"bl_no2": "x"})

    def test_update_row(self):
        """改行：data 整体替换并校验列"""
        ds = SimpleNamespace(id=1, columns=[{"key": "a", "type": "string"}])
        row = SimpleNamespace(id=9, dataset_id=1, data={"a": "old"}, row_index=2)
        with patch.object(svc.crud, "get_dataset", return_value=ds), \
             patch.object(svc.crud, "get_row", return_value=row):
            db = SimpleNamespace(commit=lambda: None, refresh=lambda o: None)
            svc.update_row(db, 1, 9, data={"a": "new"})
        assert row.data == {"a": "new"}

    def test_delete_row_reindexes(self):
        """删行后重排行序保持连续（1..n），前端显示行号不漂移"""
        rows = [SimpleNamespace(id=i, dataset_id=1, row_index=i) for i in (1, 2, 3)]
        ds = SimpleNamespace(id=1, rows=rows, columns=[{"key": "a", "type": "string"}])
        committed = {}

        class FakeQuery:
            def filter(self, *a, **k):
                return SimpleNamespace(delete=lambda: None)

            def order_by(self, *a, **k):
                return SimpleNamespace(all=lambda: rows)

        db = SimpleNamespace(query=lambda *a, **k: FakeQuery(), commit=lambda: committed.update(y=True))
        with patch.object(svc.crud, "get_dataset", return_value=ds), \
             patch.object(svc.crud, "get_row", return_value=rows[0]), \
             patch.object(svc.crud, "list_rows", side_effect=lambda db_, did: sorted(rows, key=lambda r: r.row_index)):
            db.delete = lambda o: rows.remove(o)
            svc.delete_row(db, 1, rows[0].id)
        assert [r.row_index for r in rows] == [1, 2]
        assert committed.get("y") is True


# ============ 批量行操作（表格整页保存） ============

class TestBatchRowOps:
    """PUT /rows 批量保存（整体替换）+ DELETE /rows 全清 的服务层支撑"""

    def _fake_db(self, added, bulk_deleted):
        class FakeQuery:
            def filter(self, *a, **k):
                return SimpleNamespace(delete=lambda: bulk_deleted.append(True))

        return SimpleNamespace(
            query=lambda *a, **k: FakeQuery(),
            add=lambda o: added.append(o),
            commit=lambda: None,
        )

    def test_replace_rows_rewrites_all_with_fresh_index(self):
        """批量保存：现有行全删重写，row_index 从 1 连续编号"""
        added, bulk_deleted = [], []
        ds = SimpleNamespace(id=1, columns=[{"key": "a", "type": "string"}])
        db = self._fake_db(added, bulk_deleted)
        with patch.object(svc.crud, "get_dataset", return_value=ds):
            svc.replace_rows(db, 1, rows_data=[{"a": "x"}, {"a": "y"}, {"a": "z"}])
        assert len(bulk_deleted) == 1  # 旧行一次性清掉
        assert [r.row_index for r in added] == [1, 2, 3]
        assert [r.data for r in added] == [{"a": "x"}, {"a": "y"}, {"a": "z"}]

    def test_replace_rows_empty_clears(self):
        """批量保存传空列表 = 清空所有行"""
        added, bulk_deleted = [], []
        ds = SimpleNamespace(id=1, columns=[{"key": "a", "type": "string"}])
        db = self._fake_db(added, bulk_deleted)
        with patch.object(svc.crud, "get_dataset", return_value=ds):
            svc.replace_rows(db, 1, rows_data=[])
        assert len(bulk_deleted) == 1
        assert added == []

    def test_replace_rows_rejects_unknown_keys(self):
        """批量数据含未定义列 → 整批拒绝（原子性：不落任何行）"""
        added, bulk_deleted = [], []
        ds = SimpleNamespace(id=1, columns=[{"key": "a", "type": "string"}])
        db = self._fake_db(added, bulk_deleted)
        with patch.object(svc.crud, "get_dataset", return_value=ds):
            with pytest.raises(ValueError, match="未定义的列"):
                svc.replace_rows(db, 1, rows_data=[{"a": "x"}, {"b": "bad"}])
        assert bulk_deleted == [] and added == []  # 校验失败不动库

    def test_clear_rows(self):
        """全清：批量删除行，不删数据集本身"""
        added, bulk_deleted = [], []
        ds = SimpleNamespace(id=1, columns=[{"key": "a", "type": "string"}])
        db = self._fake_db(added, bulk_deleted)
        with patch.object(svc.crud, "get_dataset", return_value=ds):
            svc.clear_rows(db, 1)
        assert len(bulk_deleted) == 1
        assert added == []


# ============ 导入解析（Excel/CSV → 行数据，纯函数） ============

def _make_xlsx(header, rows):
    """内存构造 xlsx（openpyxl 写入 BytesIO）"""
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.append(header)
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


class TestImportParse:
    """parse_import_file(filename, content, columns) → (rows_data, warnings)

    契约：首行表头按列 key 匹配；多余列忽略+告警，缺失列置空+告警；
    值不做类型转换（xlsx 保留原始类型，CSV 全字符串），类型语义交给 body_builder。
    """

    def test_parse_csv_utf8(self):
        csv_content = b"bl_no,put_amount\r\nBL001,100\r\nBL002,200\r\n"
        rows, warns = svc.parse_import_file("data.csv", csv_content, _COLS)
        assert rows == [{"bl_no": "BL001", "put_amount": "100"}, {"bl_no": "BL002", "put_amount": "200"}]
        assert warns == []

    def test_parse_csv_with_bom(self):
        """Excel 另存的 CSV 带 BOM：utf-8-sig 兼容，表头首个 key 不能带 \ufeff"""
        csv_content = "bl_no,put_amount\r\nBL001,100\r\n".encode("utf-8-sig")
        rows, _ = svc.parse_import_file("data.csv", csv_content, _COLS)
        assert rows == [{"bl_no": "BL001", "put_amount": "100"}]

    def test_parse_xlsx_keeps_native_types(self):
        """xlsx 数字单元格保留原始类型（int 就是 int），不做字符串化"""
        content = _make_xlsx(["bl_no", "put_amount"], [["BL001", 100], ["BL002", 200]])
        rows, _ = svc.parse_import_file("data.xlsx", content, _COLS)
        assert rows == [{"bl_no": "BL001", "put_amount": 100}, {"bl_no": "BL002", "put_amount": 200}]

    def test_extra_column_ignored_with_warning(self):
        """文件里多余列（columns 未定义）忽略 + 告警"""
        csv_content = b"bl_no,put_amount,extra\r\nBL001,100,xx\r\n"
        rows, warns = svc.parse_import_file("data.csv", csv_content, _COLS)
        assert rows == [{"bl_no": "BL001", "put_amount": "100"}]
        assert any("extra" in w for w in warns)

    def test_missing_column_filled_empty_with_warning(self):
        """文件缺列（columns 定义了但表头没有）→ 置空 + 告警"""
        csv_content = b"bl_no\r\nBL001\r\n"
        rows, warns = svc.parse_import_file("data.csv", csv_content, _COLS)
        assert rows == [{"bl_no": "BL001", "put_amount": ""}]
        assert any("put_amount" in w for w in warns)

    def test_empty_file_rejected(self):
        with pytest.raises(ValueError, match="空|无表头"):
            svc.parse_import_file("data.csv", b"", _COLS)

    def test_header_only_rejected(self):
        """只有表头无数据行 → 拒（导入语义是要有数据，用户多半选错文件）"""
        csv_content = b"bl_no,put_amount\r\n"
        with pytest.raises(ValueError, match="无数据行"):
            svc.parse_import_file("data.csv", csv_content, _COLS)

    def test_unsupported_extension_rejected(self):
        with pytest.raises(ValueError, match="仅支持|格式"):
            svc.parse_import_file("data.json", b"{}", _COLS)


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


# ============ 保存用例自动同步快照（sync_case_datasets） ============

def _cfg(node_id, api_id=None, assertions=None):
    """CaseNodeConfig 替身"""
    return SimpleNamespace(node_id=node_id, api_id=api_id,
                           pre_process=[], post_extract=[],
                           assertions=assertions or [], wait_after_ms=0)


class TestSyncCaseDatasets:
    def _db(self, datasets, cfgs, case):
        """query 链替身：DataSet 查询 → 绑定数据集；CaseNodeConfig 查询 → 当前编排"""

        def fake_query(model):
            if model is models.DataSet:
                return SimpleNamespace(filter=lambda *a, **k: SimpleNamespace(all=lambda: datasets))
            if model is models.CaseNodeConfig:
                return SimpleNamespace(filter=lambda *a, **k: SimpleNamespace(all=lambda: cfgs))
            return SimpleNamespace(filter=lambda *a, **k: SimpleNamespace(all=lambda: []))

        committed = []
        with patch.object(svc.crud, "get_testcase", return_value=case):
            db = SimpleNamespace(query=fake_query, commit=lambda: committed.append(True))
            return svc.sync_case_datasets(db, case_id=case.id), committed

    def test_sync_updates_all_bound_datasets(self):
        """两个数据集绑定同用例：全部拿到最新快照（各自独立深拷贝）"""
        case = SimpleNamespace(id=1, dag_config={"nodes": [{"id": "n1"}, {"id": "n2"}], "edges": []})
        ds1 = SimpleNamespace(id=11, case_id=1, node_configs=[])
        ds2 = SimpleNamespace(id=12, case_id=1, node_configs=[])
        cfgs = [_cfg("n1", api_id=100, assertions=[{"type": "json_path_equals"}]), _cfg("n2")]
        n, committed = self._db([ds1, ds2], cfgs, case)
        assert n == 2
        assert committed == [True]
        for ds in (ds1, ds2):
            assert [c["node_id"] for c in ds.node_configs] == ["n1", "n2"]
            assert ds.node_configs[0]["api_id"] == 100
            assert ds.node_configs[0]["assertions"][0]["type"] == "json_path_equals"
        # 各数据集快照是独立对象：改一个不影响另一个
        ds1.node_configs[0]["api_id"] = 999
        assert ds2.node_configs[0]["api_id"] == 100

    def test_sync_ignores_nodes_removed_from_dag(self):
        """快照只含 dag 中存在的节点（用例删了 n2，快照不再带 n2）"""
        case = SimpleNamespace(id=1, dag_config={"nodes": [{"id": "n1"}], "edges": []})
        ds = SimpleNamespace(id=11, case_id=1, node_configs=[])
        cfgs = [_cfg("n1"), _cfg("n2")]  # n2 的配置行仍在，但 dag 已删节点
        n, _ = self._db([ds], cfgs, case)
        assert n == 1
        assert [c["node_id"] for c in ds.node_configs] == ["n1"]

    def test_sync_without_datasets_returns_zero(self):
        """未绑定数据集：返回 0，不触发 commit（保存用例照常）"""
        case = SimpleNamespace(id=1, dag_config={"nodes": [], "edges": []})
        n, committed = self._db([], [], case)
        assert n == 0
        assert committed == []

    def test_sync_case_missing_returns_zero(self):
        """用例已不存在：返回 0 不抛（调用方刚保存过用例，防御分支）"""
        def fake_query(model):
            return SimpleNamespace(filter=lambda *a, **k: SimpleNamespace(all=lambda: [SimpleNamespace(id=11)]))

        with patch.object(svc.crud, "get_testcase", return_value=None):
            db = SimpleNamespace(query=fake_query, commit=lambda: None)
            assert svc.sync_case_datasets(db, case_id=1) == 0

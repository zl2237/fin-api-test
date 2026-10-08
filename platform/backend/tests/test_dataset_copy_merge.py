"""数据集复制单测（copy_dataset：值全量深拷贝）。

seam：services/dataset_service.py 公开函数（SimpleNamespace ORM 替身 + mock crud），
不触真实数据库。

注：数据集间对比与覆盖合并（compare_datasets / merge_from_dataset）已随
「入参收敛到数据集行」移除——数据集按用例隔离、复用靠复制，跨数据集按列
覆盖合并的语义不复存在（旧 TestCompareAndMerge 用例已删除）。
"""
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.services import dataset_service as svc


def _fake_db():
    """带 query 链的空 db 替身（copy 重名查重等惰性查询返回空）"""
    return SimpleNamespace(query=lambda *a: SimpleNamespace(
        filter=lambda *b: SimpleNamespace(first=lambda: None)))


# ============ 数据集复制 ============

class TestCopyDataset:
    def _ds(self):
        return SimpleNamespace(
            id=5, project_id=1, case_id=9, name="场景A", description="描述",
            rows=[SimpleNamespace(id=51, row_index=1,
                                  data={"nodes": {"n1": {"params": {"body": {"bl_no": {"source": "constant", "value": "B1"}}}}}}),
                  SimpleNamespace(id=52, row_index=2, data={"nodes": {}})],
        )

    def test_copy_deep_clones_all(self):
        """复制：行内节点入参配置全量深拷贝（改副本不动源），命名「原名-副本」，归属同用例"""
        src = self._ds()
        db = _fake_db()
        with patch.object(svc.crud, "get_dataset", return_value=src), \
             patch.object(svc, "create_dataset") as fake_create:
            fake_create.return_value = SimpleNamespace(id=21)
            cp = svc.copy_dataset(db, 5, user_id=1)
        kw = fake_create.call_args.kwargs
        assert kw["name"] == "场景A-副本"
        assert kw["case_id"] == 9 and kw["project_id"] == 1
        assert kw["rows_data"][0] == src.rows[0].data  # 值等价
        assert kw["rows_data"][0] is not src.rows[0].data  # 深拷贝：非同引用
        kw["rows_data"][0]["nodes"]["n1"]["params"]["body"]["bl_no"]["value"] = "MUT"
        assert src.rows[0].data["nodes"]["n1"]["params"]["body"]["bl_no"]["value"] == "B1"
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

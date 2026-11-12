"""执行展开：绑定数据集的用例用其单套数据执行（单套语义）。

seam：
- dataset_service.plan_case_expansion：展开计划纯读函数（未绑定→1条普通；
  绑定→该数据集唯一一套数据展开 1 条；无数据→拒）
- crud.executions.create_execution：dataset 快照落 record（失败可溯源是哪套数据）
"""
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.crud import executions as exec_domain
from app.services import dataset_service as svc


def _ds(rows, columns=None, case_id=11, name="运单数据"):
    return SimpleNamespace(id=7, case_id=case_id, name=name,
                           rows=rows)


def _rows(n):
    return [SimpleNamespace(id=i, dataset_id=7, row_index=i, data={"bl_no": f"BL{i:03d}"})
            for i in range(1, n + 1)]


class TestPlanCaseExpansion:
    def test_unbound_case_rejected(self):
        """无 bound 数据集 → 拒绝执行（入参无默认值兜底，全空参数无意义）"""
        case = SimpleNamespace(id=11)
        with patch.object(svc.crud, "list_bound_datasets", return_value=[]):
            with pytest.raises(ValueError, match="未绑定数据集"):
                svc.plan_case_expansion(SimpleNamespace(), case)

    def test_bound_case_expands_single_set(self):
        """单 bound 数据集 → 恒 1 条展开项：取首行（唯一一套数据），快照含 row_index/data/label"""
        case = SimpleNamespace(id=11)
        rows = _rows(3)  # 存量多行：只取第一行（多场景 = 多个数据集）
        ds = _ds(rows)
        with patch.object(svc.crud, "list_bound_datasets", return_value=[ds]), \
             patch.object(svc.crud, "list_rows", return_value=rows):
            plan = svc.plan_case_expansion(SimpleNamespace(), case)
        assert len(plan) == 1
        assert plan[0]["dataset_id"] == 7
        assert plan[0]["row"] == {"row_index": 1, "data": {"bl_no": "BL001"}, "label": "运单数据"}

    def test_multi_bound_expands_each(self):
        """多 bound 数据集（多选绑定）→ 各展开一条（场景序 = id 稳定序）"""
        case = SimpleNamespace(id=11)
        ds7 = _ds([SimpleNamespace(id=1, dataset_id=7, row_index=1, data={"bl_no": "A"})],
                  name="场景A")
        ds8 = _ds([SimpleNamespace(id=2, dataset_id=8, row_index=1, data={"bl_no": "B"})],
                  case_id=11, name="场景B")
        ds8.id = 8
        rows_by_ds = {7: ds7.rows, 8: ds8.rows}
        with patch.object(svc.crud, "list_bound_datasets", return_value=[ds7, ds8]), \
             patch.object(svc.crud, "list_rows",
                          side_effect=lambda db, did: rows_by_ds.get(did, [])):
            plan = svc.plan_case_expansion(SimpleNamespace(), case)
        assert [(p["dataset_id"], p["row"]["label"]) for p in plan] == [(7, "场景A"), (8, "场景B")]

    def test_explicit_dataset_ids_override_binding(self):
        """成员级/面板级显式 dataset_ids：按名单展开，不读用例绑定"""
        case = SimpleNamespace(id=11)
        ds = _ds(_rows(1))
        with patch.object(svc.crud, "get_dataset", return_value=ds) as g, \
             patch.object(svc.crud, "list_bound_datasets") as lb, \
             patch.object(svc.crud, "list_rows", return_value=_rows(1)):
            plan = svc.plan_case_expansion(SimpleNamespace(), case, dataset_ids=[7])
        assert [p["dataset_id"] for p in plan] == [7]
        g.assert_called_once()
        lb.assert_not_called()

    def test_zero_rows_rejected(self):
        """bound 但数据集无数据 → 拒绝执行（先在数据集页完成入参配置）"""
        case = SimpleNamespace(id=11)
        with patch.object(svc.crud, "list_bound_datasets", return_value=[_ds([])]), \
             patch.object(svc.crud, "list_rows", return_value=[]):
            with pytest.raises(ValueError, match="无数据"):
                svc.plan_case_expansion(SimpleNamespace(), case)

    def test_other_case_dataset_rejected(self):
        """显式指定的数据集属于别的用例 → 拒（用例间隔离）"""
        case = SimpleNamespace(id=11)
        with patch.object(svc.crud, "get_dataset", return_value=_ds(_rows(2), case_id=99)):
            with pytest.raises(ValueError, match="不属于该用例|隔离"):
                svc.plan_case_expansion(SimpleNamespace(), case, dataset_ids=[7])

    def test_bound_dataset_missing_rejected(self):
        """显式指定的数据集不存在（防御）→ 明确报错而非静默单条"""
        case = SimpleNamespace(id=11)
        with patch.object(svc.crud, "get_dataset", return_value=None):
            with pytest.raises(ValueError, match="数据集不存在"):
                svc.plan_case_expansion(SimpleNamespace(), case, dataset_ids=[7])


class TestRecordSnapshot:
    def test_create_execution_persists_dataset_snapshot(self):
        """create_execution 落 dataset_id + dataset_row 快照（历史记录保留当次真实数据）"""
        captured = {}

        def fake_add(obj):
            captured["rec"] = obj

        db = SimpleNamespace(add=fake_add, commit=lambda: None, refresh=lambda o: None)
        rec = exec_domain.create_execution(
            db, case_id=1, env_id=2, user_id=3,
            dataset_id=7, dataset_row={"row_index": 2, "data": {"bl_no": "BL002"}, "label": "BL002"})
        assert captured["rec"].dataset_id == 7
        assert captured["rec"].dataset_row["row_index"] == 2
        assert rec is captured["rec"]

    def test_create_execution_without_dataset_unchanged(self):
        """未传快照：record 的 dataset 字段为 None（现状回归）"""
        captured = {}

        def fake_add(obj):
            captured["rec"] = obj

        db = SimpleNamespace(add=fake_add, commit=lambda: None, refresh=lambda o: None)
        exec_domain.create_execution(db, case_id=1, env_id=2, user_id=3)
        assert captured["rec"].dataset_id is None
        assert captured["rec"].dataset_row is None


class TestBatchExecuteCounts:
    """批量执行次数（counts）与并发数（concurrency）校验：路由层在触达 db 前完成参数检查"""

    def _call(self, counts, concurrency=4):
        from app.routers.executions import batch_execute
        from app.schemas import BatchExecutionCreate

        return batch_execute(
            BatchExecutionCreate(case_ids=[1, 2, 3], env_id=1, counts=counts, concurrency=concurrency),
            db=None, user=None)

    def test_counts_length_mismatch_rejected(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as e:
            self._call([1, 2])  # 3 个用例只给 2 个次数
        assert e.value.status_code == 400
        assert "一致" in e.value.detail

    def test_counts_out_of_range_rejected(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as e:
            self._call([1, 0, 2])  # 0 次非法
        assert e.value.status_code == 400
        assert "1~9999" in e.value.detail

    def test_counts_over_limit_rejected(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as e:
            self._call([10000, 1, 1])  # 超过上限 9999（仅防手滑）
        assert e.value.status_code == 400

    def test_counts_large_but_within_limit_passes(self):
        """100 次循环这类大次数合法（原 20 上限已放开）"""
        from fastapi import HTTPException

        with patch("app.routers.executions.crud.get_testcase", return_value=None):
            with pytest.raises(HTTPException) as e:
                self._call([100, 1, 1])
        assert e.value.status_code == 404  # 通过参数校验，停在用例检查

    def test_concurrency_out_of_range_rejected(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as e:
            self._call([1, 1, 1], concurrency=0)
        assert e.value.status_code == 400
        assert "1~16" in e.value.detail

        with pytest.raises(HTTPException) as e:
            self._call([1, 1, 1], concurrency=17)
        assert e.value.status_code == 400

    def test_concurrency_one_passes_validation(self):
        """并发数 1（串行）合法，继续走到用例检查"""
        from fastapi import HTTPException

        with patch("app.routers.executions.crud.get_testcase", return_value=None):
            with pytest.raises(HTTPException) as e:
                self._call([1, 1, 1], concurrency=1)
        assert e.value.status_code == 404

    def test_valid_counts_passes_validation_and_fails_on_case(self):
        """合法 counts 通过参数校验，继续走到用例检查（无 db 时在用例处被拦即可证明顺序）"""
        from fastapi import HTTPException

        with patch("app.routers.executions.crud.get_testcase", return_value=None):
            with pytest.raises(HTTPException) as e:
                self._call([3, 1, 2])  # 用户示例：A×3 B×1 C×2
        assert e.value.status_code == 404  # 用例不存在：参数校验已放行

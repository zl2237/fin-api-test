"""执行展开（数据驱动测试周期 5）：绑定数据集的用例一次执行展开为 N 次执行。

seam：
- dataset_service.plan_case_expansion：展开计划纯读函数（未绑定→1条普通；N行→N快照；0行→拒）
- crud.executions.create_execution：dataset 快照落 record（失败可溯源是哪行数据）
"""
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.crud import executions as exec_domain
from app.services import dataset_service as svc


def _ds(rows, columns=None, case_id=11):
    return SimpleNamespace(id=7, case_id=case_id, columns=columns or [{"key": "bl_no", "type": "string"}],
                           node_configs=[], rows=rows)


def _rows(n):
    return [SimpleNamespace(id=i, dataset_id=7, row_index=i, data={"bl_no": f"BL{i:03d}"})
            for i in range(1, n + 1)]


class TestPlanCaseExpansion:
    def test_unbound_case_expands_to_single_plain(self):
        """未绑定数据集：单条普通执行（行为与现状完全一致）"""
        case = SimpleNamespace(id=11, dataset_id=None)
        with patch.object(svc.crud, "get_dataset") as g:
            plan = svc.plan_case_expansion(SimpleNamespace(), case)
        assert plan == [{"dataset_id": None, "row": None, "overrides": None, "origins": None}]
        g.assert_not_called()  # 未绑定不查数据集

    def test_bound_case_expands_per_row(self):
        """绑定 3 行 → 3 条展开项，快照含 row_index/data/label（首列值）"""
        case = SimpleNamespace(id=11, dataset_id=7)
        rows = _rows(3)
        with patch.object(svc.crud, "get_dataset", return_value=_ds(rows)), \
             patch.object(svc.crud, "list_rows", return_value=rows):
            plan = svc.plan_case_expansion(SimpleNamespace(), case)
        assert len(plan) == 3
        assert all(p["dataset_id"] == 7 for p in plan)
        assert plan[0]["row"] == {"row_index": 1, "data": {"bl_no": "BL001"}, "label": "BL001"}
        assert plan[2]["row"]["row_index"] == 3

    def test_zero_rows_rejected(self):
        """绑定但数据集 0 行 → 拒绝执行（先录入数据）"""
        case = SimpleNamespace(id=11, dataset_id=7)
        with patch.object(svc.crud, "get_dataset", return_value=_ds([])), \
             patch.object(svc.crud, "list_rows", return_value=[]):
            with pytest.raises(ValueError, match="无数据行|先录入"):
                svc.plan_case_expansion(SimpleNamespace(), case)

    def test_other_case_dataset_rejected(self):
        """绑定别的用例的数据集 → 拒绝（用例间隔离）"""
        case = SimpleNamespace(id=11, dataset_id=7)
        with patch.object(svc.crud, "get_dataset", return_value=_ds(_rows(2), case_id=99)), \
             patch.object(svc.crud, "list_rows", return_value=_rows(2)):
            with pytest.raises(ValueError, match="不属于该用例|隔离"):
                svc.plan_case_expansion(SimpleNamespace(), case)

    def test_node_config_overrides_attached(self):
        """数据集带节点配置快照 → 展开项附 overrides 映射（执行时整块替换用例编排）"""
        case = SimpleNamespace(id=11, dataset_id=7)
        rows = _rows(1)
        ds = _ds(rows)
        ds.node_configs = [{"node_id": "n1", "api_id": 3, "pre_process": [], "post_extract": [],
                            "assertions": [], "wait_after_ms": 100}]
        with patch.object(svc.crud, "get_dataset", return_value=ds), \
             patch.object(svc.crud, "list_rows", return_value=rows):
            plan = svc.plan_case_expansion(SimpleNamespace(), case)
        assert plan[0]["overrides"] == {"n1": ds.node_configs[0]}

    def test_bound_dataset_missing_rejected(self):
        """绑定的数据集不存在（防御：正常被删除保护拦住）→ 明确报错而非静默单条"""
        case = SimpleNamespace(dataset_id=7)
        with patch.object(svc.crud, "get_dataset", return_value=None):
            with pytest.raises(ValueError, match="数据集不存在"):
                svc.plan_case_expansion(SimpleNamespace(), case)


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
    """批量执行次数参数（counts）校验：路由层在触达 db 前完成参数检查"""

    def _call(self, counts):
        from app.routers.executions import batch_execute
        from app.schemas import BatchExecutionCreate

        return batch_execute(BatchExecutionCreate(case_ids=[1, 2, 3], env_id=1, counts=counts), db=None, user=None)

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
        assert "1~20" in e.value.detail

    def test_counts_over_limit_rejected(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as e:
            self._call([21, 1, 1])  # 超过上限 20
        assert e.value.status_code == 400

    def test_valid_counts_passes_validation_and_fails_on_env(self):
        """合法 counts 通过参数校验，继续走到环境检查（无 db 时在 env 处被拦即可证明顺序）"""
        from fastapi import HTTPException

        with patch("app.routers.executions.crud.get_environment", return_value=None):
            with pytest.raises(HTTPException) as e:
                self._call([3, 1, 2])  # 用户示例：A×3 B×1 C×2
        assert e.value.status_code == 404  # 环境不存在：参数校验已放行

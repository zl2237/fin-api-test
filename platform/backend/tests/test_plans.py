"""执行方案单测：validate_plan_items 保存校验（run_plan 两阶段编排用例随后续提交补齐）。

与 test_execution_launcher 同风格：SimpleNamespace 替身 + monkeypatch，不碰真库。
"""
from types import SimpleNamespace

import pytest

from app.services import plan_executor
from app.services.plan_executor import validate_plan_items

# 普通用例 / 套件替身
CASE = SimpleNamespace(id=11, name="下单用例", case_type="normal", env_id=5)
SUITE = SimpleNamespace(id=12, name="结算套件", case_type="suite")


def _item(**kw):
    base = dict(case_id=11, dataset_id=None, run_count=1, sort_order=0)
    base.update(kw)
    return SimpleNamespace(**base)


class TestValidatePlanItems:

    @pytest.fixture
    def stubbed(self, monkeypatch):
        """crud.get_testcase → CASE；validate_binding 打桩（记录调用，dataset_id=999 时抛错）"""
        calls = []

        def fake_binding(db, case, dataset_id):
            calls.append((case.id, dataset_id))
            if dataset_id == 999:
                raise ValueError("数据集不属于该用例（数据集按用例隔离）")

        monkeypatch.setattr(plan_executor.crud, "get_testcase",
                            lambda db, cid: {11: CASE, 12: SUITE}.get(cid))
        monkeypatch.setattr(plan_executor.dataset_service,
                            "validate_binding", fake_binding)
        return SimpleNamespace(calls=calls)

    def test_ok_without_override(self, stubbed):
        """无换绑成员合法，且不触发数据集绑定校验"""
        validate_plan_items(object(), [_item()])
        assert stubbed.calls == []

    def test_case_missing_rejected(self, stubbed):
        with pytest.raises(ValueError, match="用例不存在"):
            validate_plan_items(object(), [_item(case_id=404)])

    def test_dataset_of_other_case_rejected(self, stubbed):
        """换绑数据集不属于成员用例：复用执行面板换绑同口径校验拒绝"""
        with pytest.raises(ValueError, match="不属于该用例"):
            validate_plan_items(object(), [_item(dataset_id=999)])
        assert stubbed.calls == [(11, 999)]

    def test_suite_member_override_rejected(self, stubbed):
        """套件成员：成员各自绑定数据集，禁换绑"""
        with pytest.raises(ValueError, match="套件"):
            validate_plan_items(object(), [_item(case_id=12, dataset_id=7)])

    def test_suite_member_bare_ok(self, stubbed):
        validate_plan_items(object(), [_item(case_id=12)])

    def test_run_count_out_of_range(self, stubbed):
        with pytest.raises(ValueError, match="执行次数"):
            validate_plan_items(object(), [_item(run_count=0)])
        with pytest.raises(ValueError, match="执行次数"):
            validate_plan_items(object(), [_item(run_count=10000)])
        validate_plan_items(object(), [_item(run_count=9999)])  # 边界合法

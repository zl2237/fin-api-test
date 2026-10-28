"""execution_launcher 单测：展开/提交语义的唯一事实源。

- build_launch_plan：单套值展开 → 建记录 → specs（环境严格绑定：读 case.env_id）
- commit_launch：多 plan 平铺一次提交 + concurrency 透传
"""
from types import SimpleNamespace

import pytest

from app.services import execution_launcher as launcher
from app.services.execution_launcher import (
    ExecutionSpec,
    LaunchPlan,
    build_launch_plan,
    commit_launch,
)

# env_id：用例绑定的执行环境（严格绑定：发射编排不再接收环境参数）
CASE = SimpleNamespace(id=11, name="提单用例", env_id=5)


def _row(idx: int, bl: str) -> dict:
    return {"row_index": idx, "data": {"bl_no": bl}, "label": bl}


@pytest.fixture
def patched(monkeypatch):
    created, submitted = [], []

    def fake_create(db, case_id, env_id, user_id, trigger_type="manual",
                    dataset_id=None, dataset_row=None, plan_id=None):
        rec = SimpleNamespace(id=100 + len(created), case_id=case_id, env_id=env_id,
                              dataset_id=dataset_id, dataset_row=dataset_row, plan_id=plan_id)
        created.append({"record": rec, "trigger_type": trigger_type})
        return rec

    monkeypatch.setattr(launcher.exec_domain, "create_execution", fake_create)
    monkeypatch.setattr(launcher, "submit_batch_execution",
                        lambda specs, concurrency=4:
                            submitted.append((list(specs), concurrency)))
    monkeypatch.setattr(launcher, "crud",
                        SimpleNamespace(fill_audit_names=lambda *a: None,
                                        fill_exec_names=lambda *a: None,
                                        get_environment=lambda db, eid: SimpleNamespace(id=eid)))
    return SimpleNamespace(created=created, submitted=submitted)


def _set_plan(monkeypatch, items):
    monkeypatch.setattr(launcher.dataset_service, "plan_case_expansion",
                        lambda db, case, **kw: items)


class TestBuildLaunchPlan:

    def test_single_case_no_dataset(self, patched, monkeypatch):
        """普通用例：1 条记录 1 个 spec，环境=用例绑定环境"""
        _set_plan(monkeypatch, [{"dataset_id": None, "row": None,
                                 "overrides": None}])

        plan = build_launch_plan(object(), CASE, 22)

        assert len(plan.records) == 1
        spec = plan.specs[0]
        assert (spec.execution_id, spec.case_id) == (100, 11)
        assert spec.dataset_row is None
        assert spec.env_id == 5
        assert plan.records[0].env_id == 5

    def test_bound_dataset_row_passthrough(self, patched, monkeypatch):
        """绑定数据集：row 的单套值作为 dataset_row 传入 spec"""
        _set_plan(monkeypatch, [{"dataset_id": 7, "row": _row(1, "BL001"),
                                 "overrides": None}])

        plan = build_launch_plan(object(), CASE, 22)

        assert plan.records[0].dataset_id == 7
        assert plan.specs[0].dataset_row == {"bl_no": "BL001"}

    def test_run_count_multiplies_records(self, patched, monkeypatch):
        """执行次数 ×N：记录与 spec 数量翻倍"""
        _set_plan(monkeypatch, [
            {"dataset_id": 7, "row": _row(1, "BL001"), "overrides": None},
            {"dataset_id": 7, "row": _row(2, "BL002"), "overrides": None},
        ])

        plan = build_launch_plan(object(), CASE, 22, run_count=3)

        assert len(plan.specs) == 6  # 3 轮 × 2 条展开
        assert [s.dataset_row for s in plan.specs[:2]] == [{"bl_no": "BL001"}, {"bl_no": "BL002"}]

    def test_trigger_type_passthrough(self, patched, monkeypatch):
        """trigger_type 透传到每条记录（schedule/manual 溯源）"""
        _set_plan(monkeypatch, [{"dataset_id": None, "row": None,
                                 "overrides": None}])

        build_launch_plan(object(), CASE, 22, trigger_type="schedule")

        assert patched.created[0]["trigger_type"] == "schedule"

    def test_dataset_not_executable_raises(self, patched, monkeypatch):
        """数据集 0 行/过期：ValueError 上抛，由调用方决定 4xx 或跳过本轮"""
        def boom(db, case, **kw):
            raise ValueError("数据集无数据行，请先录入数据再执行")

        monkeypatch.setattr(launcher.dataset_service, "plan_case_expansion", boom)

        with pytest.raises(ValueError, match="无数据行"):
            build_launch_plan(object(), CASE, 22)

    def test_case_without_env_raises(self, patched, monkeypatch):
        """环境严格绑定：未绑定环境的普通用例发射即拒（ValueError → 路由 400）"""
        no_env = SimpleNamespace(id=13, name="无环境用例", env_id=None)

        with pytest.raises(ValueError, match="未绑定执行环境"):
            build_launch_plan(object(), no_env, 22)

    def test_case_env_missing_raises(self, patched, monkeypatch):
        """绑定环境已被删除：发射即拒（自愈：提示重新绑定）"""
        monkeypatch.setattr(launcher, "crud",
                            SimpleNamespace(fill_audit_names=lambda *a: None,
                                            fill_exec_names=lambda *a: None,
                                            get_environment=lambda db, eid: None))

        with pytest.raises(ValueError, match="环境已不存在"):
            build_launch_plan(object(), CASE, 22)


class TestCommitLaunch:

    def _plan(self, ids):
        return LaunchPlan(specs=[ExecutionSpec(execution_id=i, case_id=11, env_id=5) for i in ids])

    def test_flattens_plans_into_one_submit(self, patched):
        """多个 plan 一次提交：specs 平铺、concurrency 透传"""
        p1, p2 = self._plan([100, 101]), self._plan([200, 201])

        commit_launch([p1, p2], concurrency=8)

        assert len(patched.submitted) == 1  # 一个批次专用池
        specs, concurrency = patched.submitted[0]
        assert [s.execution_id for s in specs] == [100, 101, 200, 201]
        assert concurrency == 8

    def test_empty_specs_no_submit(self, patched):
        """无 specs：不提交"""
        commit_launch([LaunchPlan()])

        assert patched.submitted == []

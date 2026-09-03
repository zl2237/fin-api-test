"""execution_launcher 单测：编排收敛后的展开/聚合/提交语义。

此前这段编排散在 execute 路由、batch_execute 路由、scheduler 三处各自拷贝，
测试也随之分裂（只有 scheduler 那份被测过）。收敛后这里成为唯一事实源：
- build_launch_plan：展开 → 建记录 → specs/聚合组（suppress 语义）
- commit_launch：多 plan 平铺一次提交 + 聚合注册 + concurrency 透传
"""
from types import SimpleNamespace

import pytest

from app.services import execution_launcher as launcher
from app.services.execution_launcher import (
    ExecutionSpec,
    LaunchPlan,
    AggregateGroup,
    build_launch_plan,
    commit_launch,
)

CASE = SimpleNamespace(id=11, name="提单用例")


def _row(idx: int, bl: str) -> dict:
    return {"row_index": idx, "data": {"bl_no": bl}, "label": bl}


@pytest.fixture
def patched(monkeypatch):
    created, submitted, aggregates = [], [], []

    def fake_create(db, case_id, env_id, user_id, trigger_type="manual",
                    dataset_id=None, dataset_row=None):
        rec = SimpleNamespace(id=100 + len(created), case_id=case_id, env_id=env_id,
                              dataset_id=dataset_id, dataset_row=dataset_row)
        created.append({"record": rec, "trigger_type": trigger_type})
        return rec

    monkeypatch.setattr(launcher.exec_domain, "create_execution", fake_create)
    monkeypatch.setattr(launcher, "submit_batch_execution",
                        lambda specs, env_id, concurrency=4:
                            submitted.append((list(specs), env_id, concurrency)))
    monkeypatch.setattr(launcher, "submit_batch_aggregate_notify",
                        lambda ids, case_id, env_id, dataset_id, case_name:
                            aggregates.append((tuple(ids), case_id, dataset_id, case_name)))
    monkeypatch.setattr(launcher, "crud",
                        SimpleNamespace(fill_audit_names=lambda *a: None,
                                        fill_exec_names=lambda *a: None))
    return SimpleNamespace(created=created, submitted=submitted, aggregates=aggregates)


def _set_plan(monkeypatch, items):
    monkeypatch.setattr(launcher.dataset_service, "plan_case_expansion",
                        lambda db, case, **kw: items)


class TestBuildLaunchPlan:

    def test_single_case_no_dataset(self, patched, monkeypatch):
        """普通用例：1 条记录 1 个 spec，不抑制通知，无聚合组"""
        _set_plan(monkeypatch, [{"dataset_id": None, "row": None,
                                 "origins": None, "overrides": None}])

        plan = build_launch_plan(object(), CASE, 22, 5)

        assert len(plan.records) == 1
        spec = plan.specs[0]
        assert (spec.execution_id, spec.case_id) == (100, 11)
        assert spec.row_vars is None and spec.row_origins is None
        assert spec.node_config_overrides is None
        assert spec.suppress_notify is False
        assert plan.aggregate_groups == []

    def test_multi_row_dataset_aggregates(self, patched, monkeypatch):
        """数据驱动多行：每行一条记录，整组抑制逐条通知，登记一个聚合组"""
        items = [
            {"dataset_id": 7, "row": _row(1, "BL001"), "origins": {"bl_no": "BL"},
             "overrides": None},
            {"dataset_id": 7, "row": _row(2, "BL002"), "origins": {"bl_no": "BL"},
             "overrides": None},
        ]
        _set_plan(monkeypatch, items)

        plan = build_launch_plan(object(), CASE, 22, 5)

        assert [s.execution_id for s in plan.specs] == [100, 101]
        assert all(s.suppress_notify for s in plan.specs)  # 抑制逐条
        assert [s.row_vars for s in plan.specs] == [{"bl_no": "BL001"}, {"bl_no": "BL002"}]
        assert all(s.row_origins == {"bl_no": "BL"} for s in plan.specs)
        assert len(plan.aggregate_groups) == 1
        group = plan.aggregate_groups[0]
        assert group.execution_ids == [100, 101]
        assert (group.case_id, group.dataset_id, group.case_name) == (11, 7, "提单用例")

    def test_run_count_multiplies_with_single_group(self, patched, monkeypatch):
        """执行次数 ×N：记录数翻倍，聚合组覆盖全部 N×行 的 id"""
        _set_plan(monkeypatch, [
            {"dataset_id": 7, "row": _row(1, "BL001"), "origins": None, "overrides": None},
            {"dataset_id": 7, "row": _row(2, "BL002"), "origins": None, "overrides": None},
        ])

        plan = build_launch_plan(object(), CASE, 22, 5, run_count=3)

        assert len(plan.specs) == 6  # 3 轮 × 2 行
        assert plan.aggregate_groups[0].execution_ids == [100, 101, 102, 103, 104, 105]

    def test_single_row_dataset_no_aggregate(self, patched, monkeypatch):
        """row_ids 只选 1 行：dataset_id 非空但 len(plan)==1，保持逐条通知"""
        _set_plan(monkeypatch, [{"dataset_id": 7, "row": _row(1, "BL001"),
                                 "origins": None, "overrides": None}])

        plan = build_launch_plan(object(), CASE, 22, 5)

        assert plan.specs[0].suppress_notify is False
        assert plan.aggregate_groups == []

    def test_trigger_type_passthrough(self, patched, monkeypatch):
        """trigger_type 透传到每条记录（schedule/manual 溯源）"""
        _set_plan(monkeypatch, [{"dataset_id": None, "row": None,
                                 "origins": None, "overrides": None}])

        build_launch_plan(object(), CASE, 22, 5, trigger_type="schedule")

        assert patched.created[0]["trigger_type"] == "schedule"

    def test_dataset_not_executable_raises(self, patched, monkeypatch):
        """数据集 0 行/过期：ValueError 上抛，由调用方决定 4xx 或跳过本轮"""
        def boom(db, case, **kw):
            raise ValueError("数据集无数据行，请先录入数据再执行")

        monkeypatch.setattr(launcher.dataset_service, "plan_case_expansion", boom)

        with pytest.raises(ValueError, match="无数据行"):
            build_launch_plan(object(), CASE, 22, 5)


class TestCommitLaunch:

    def _plan(self, ids, group=True):
        plan = LaunchPlan(specs=[ExecutionSpec(execution_id=i, case_id=11) for i in ids])
        if group:
            plan.aggregate_groups = [AggregateGroup(execution_ids=ids, case_id=11,
                                                    dataset_id=7, case_name="提单用例")]
        return plan

    def test_flattens_plans_into_one_submit(self, patched):
        """多个 plan 一次提交：specs 平铺、concurrency 透传、每组各注册聚合"""
        p1, p2 = self._plan([100, 101]), self._plan([200, 201])

        commit_launch([p1, p2], 22, concurrency=8)

        assert len(patched.submitted) == 1  # 一个批次专用池
        specs, env_id, concurrency = patched.submitted[0]
        assert [s.execution_id for s in specs] == [100, 101, 200, 201]
        assert (env_id, concurrency) == (22, 8)
        assert patched.aggregates == [((100, 101), 11, 7, "提单用例"),
                                      ((200, 201), 11, 7, "提单用例")]

    def test_empty_specs_no_submit(self, patched):
        """无 specs：不建池不提交，也不注册聚合"""
        commit_launch([LaunchPlan()], 22)

        assert patched.submitted == []
        assert patched.aggregates == []

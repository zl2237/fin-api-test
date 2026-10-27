"""执行方案单测：validate_plan_items 保存校验 + run_plan 两阶段编排。

与 test_execution_launcher 同风格：SimpleNamespace 替身 + monkeypatch，
不碰真库；build/commit 打桩验证透传语义。
"""
from types import SimpleNamespace

import pytest

from app.services import plan_executor
from app.services.plan_executor import run_plan, validate_plan_items

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


DB = lambda: SimpleNamespace(commit=lambda: None)  # db 替身：run_plan 收尾 commit


class TestRunPlan:

    @pytest.fixture
    def stubbed(self, monkeypatch):
        """全发射链路打桩：build 记录 kwargs 返回假 plan，commit 记录 (plans, concurrency)"""
        built, committed = [], []

        def fake_build(db, case, user_id, **kw):
            rec = SimpleNamespace(id=100 + len(built), case_id=case.id)
            built.append({"case_id": case.id, "user_id": user_id, **kw})
            return SimpleNamespace(records=[rec], specs=[SimpleNamespace()])

        def fake_commit(plans, concurrency):
            committed.append((list(plans), concurrency))

        monkeypatch.setattr(plan_executor, "build_launch_plan", fake_build)
        monkeypatch.setattr(plan_executor, "commit_launch", fake_commit)
        return SimpleNamespace(built=built, committed=committed)

    @pytest.fixture
    def plan(self):
        return SimpleNamespace(id=3, concurrency=6, last_run_at=None, items=[
            _item(case_id=11, dataset_id=7, run_count=1, sort_order=0),
            _item(case_id=12, run_count=2, sort_order=1),  # 套件成员 ×2 轮
        ])

    def _stub_env(self, monkeypatch):
        """crud.get_testcase/get_environment 与数据集展开试算打桩（单套语义无行参）"""
        monkeypatch.setattr(plan_executor.crud, "get_testcase",
                            lambda db, cid: {11: CASE, 12: SUITE}.get(cid))
        monkeypatch.setattr(plan_executor.crud, "get_environment",
                            lambda db, eid: SimpleNamespace(id=eid))
        monkeypatch.setattr(plan_executor.dataset_service, "plan_case_expansion",
                            lambda db, case, **kw: [{"dataset_id": 7, "row": None}])

    def test_members_launch_with_override_and_plan_id(self, stubbed, plan, monkeypatch):
        """成员级换绑 + run_count + plan_id/trigger_type 正确透传；concurrency 取方案配置"""
        self._stub_env(monkeypatch)

        records = run_plan(DB(), plan, 22)

        assert [(b["case_id"], b["dataset_id"], b["run_count"]) for b in stubbed.built] \
            == [(11, 7, 1), (12, None, 2)]
        assert all(b["plan_id"] == 3 and b["user_id"] == 22 for b in stubbed.built)
        assert all(b["trigger_type"] == "plan" for b in stubbed.built)
        specs, concurrency = stubbed.committed[0]
        assert concurrency == 6 and len(specs) == 2  # 一次合并提交
        assert len(records) == 2  # 返回平铺记录（假 build 每 plan 1 条）
        assert plan.last_run_at is not None  # 回写最近执行时间

    def test_trigger_type_plan_schedule(self, stubbed, plan, monkeypatch):
        self._stub_env(monkeypatch)
        run_plan(DB(), plan, 22, trigger_type="plan_schedule")
        assert all(b["trigger_type"] == "plan_schedule" for b in stubbed.built)

    def test_empty_plan_rejected(self, stubbed, monkeypatch):
        with pytest.raises(ValueError, match="未配置成员"):
            run_plan(DB(), SimpleNamespace(id=3, concurrency=4,
                                           last_run_at=None, items=[]), 22)
        assert stubbed.built == []  # 零发射

    def test_precheck_failure_zero_records(self, stubbed, plan, monkeypatch):
        """预检（环境/数据集展开试算）失败：零记录零提交，ValueError 上抛"""
        self._stub_env(monkeypatch)

        def boom(db, case, **kw):
            raise ValueError("数据集无数据行，请先在数据集页完成入参配置")

        monkeypatch.setattr(plan_executor.dataset_service, "plan_case_expansion", boom)
        with pytest.raises(ValueError, match="无数据行"):
            run_plan(DB(), plan, 22)
        assert stubbed.built == [] and stubbed.committed == []

    def test_precheck_env_missing(self, stubbed, plan, monkeypatch):
        """成员绑定环境已删：预检即拒（不进 build）"""
        monkeypatch.setattr(plan_executor.crud, "get_testcase",
                            lambda db, cid: {11: CASE, 12: SUITE}.get(cid))
        monkeypatch.setattr(plan_executor.crud, "get_environment", lambda db, eid: None)
        with pytest.raises(ValueError, match="环境已不存在"):
            run_plan(DB(), plan, 22)
        assert stubbed.built == []

    def test_member_case_deleted_precheck_rejects(self, stubbed, plan, monkeypatch):
        monkeypatch.setattr(plan_executor.crud, "get_testcase", lambda db, cid: None)
        with pytest.raises(ValueError, match="已不存在"):
            run_plan(DB(), plan, 22)
        assert stubbed.built == []

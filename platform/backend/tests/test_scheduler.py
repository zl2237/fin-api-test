"""定时任务域单测：调度器配置解析、触发器构建、路由校验与触发动作。

覆盖：
- _parse_daily_time：HH:MM 合法性
- SchedulerService._build_trigger：interval/daily 触发器构建与非法配置拒绝
  （未安装 APScheduler 时跳过——生产环境必装，沙箱可缺）
- _validate_payload（schedules 路由）：配置校验错误直给前端
- _run_schedule_job：触发动作编排（查 schedule → 校验引用 → 建记录 → 提交执行），
  含引用被删后的自愈禁用路径
"""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.routers.schedules import _validate_payload
from app.services import scheduler as sched_mod
from app.services.scheduler import SchedulerService, _parse_daily_time

requires_apscheduler = pytest.mark.skipif(
    not sched_mod.APSCHEDULER_AVAILABLE,
    reason="未安装 APScheduler（生产必装，沙箱降级跳过）",
)


def _schedule(**kw):
    """构造 TestSchedule 假对象（仅触发器构建所需字段）。"""
    base = dict(id=1, schedule_type="interval", interval_minutes=None,
                daily_time=None, enabled=True, case_id=1, env_id=1, created_by=1)
    base.update(kw)
    return SimpleNamespace(**base)


class TestParseDailyTime:
    @pytest.mark.parametrize("value,expected", [
        ("09:30", (9, 30)),
        ("00:00", (0, 0)),
        ("23:59", (23, 59)),
        ("9:05", (9, 5)),
    ])
    def test_valid(self, value, expected):
        assert _parse_daily_time(value) == expected

    @pytest.mark.parametrize("value", [
        None, "", "0930", "abc", "25:00", "09:60", "-1:00", "09:30:00", "aa:bb",
    ])
    def test_invalid(self, value):
        assert _parse_daily_time(value) == (None, None)


class TestBuildTrigger:
    svc = SchedulerService()

    @requires_apscheduler
    def test_interval_valid(self):
        trigger = self.svc._build_trigger(_schedule(interval_minutes=5))
        assert trigger is not None
        assert trigger.interval.total_seconds() == 5 * 60

    @requires_apscheduler
    def test_daily_valid(self):
        trigger = self.svc._build_trigger(_schedule(schedule_type="daily", daily_time="08:30"))
        assert trigger is not None

    def test_interval_below_one_rejected(self):
        assert self.svc._build_trigger(_schedule(interval_minutes=0)) is None
        assert self.svc._build_trigger(_schedule(interval_minutes=None)) is None

    def test_daily_invalid_time_rejected(self):
        assert self.svc._build_trigger(_schedule(schedule_type="daily", daily_time="25:00")) is None
        assert self.svc._build_trigger(_schedule(schedule_type="daily", daily_time=None)) is None

    def test_unknown_type_rejected(self):
        assert self.svc._build_trigger(_schedule(schedule_type="weekly")) is None


class TestValidatePayload:
    def test_valid_interval(self):
        _validate_payload("interval", 10, None)  # 不抛即通过

    def test_valid_daily(self):
        _validate_payload("daily", None, "08:00")

    def test_interval_missing_minutes(self):
        with pytest.raises(HTTPException) as e:
            _validate_payload("interval", None, None)
        assert e.value.status_code == 400

    def test_interval_zero_minutes(self):
        with pytest.raises(HTTPException) as e:
            _validate_payload("interval", 0, None)
        assert e.value.status_code == 400

    def test_daily_invalid_time(self):
        with pytest.raises(HTTPException) as e:
            _validate_payload("daily", None, "99:00")
        assert e.value.status_code == 400

    def test_unknown_type(self):
        with pytest.raises(HTTPException) as e:
            _validate_payload("weekly", 10, None)
        assert e.value.status_code == 400


class FakeDb:
    """按查询模型返回预设结果的假会话（_run_schedule_job 编排测试用）。"""

    def __init__(self, first_by_model=None):
        self._first = first_by_model or {}
        self._model = None
        self.committed = 0
        self.closed = False

    def query(self, model):
        self._model = model
        return self

    def filter(self, *a, **kw):
        return self

    def first(self):
        return self._first.get(self._model)

    def commit(self):
        self.committed += 1

    def close(self):
        self.closed = True


class TestRunScheduleJob:
    """触发动作编排：monkeypatch 掉 SessionLocal/create_execution/submit_execution。"""

    @pytest.fixture
    def patched(self, monkeypatch):
        created = []
        submitted = []
        aggregates = []

        def fake_create(db, case_id, env_id, user_id, trigger_type="manual",
                        dataset_id=None, dataset_row=None):
            created.append(dict(case_id=case_id, env_id=env_id, user_id=user_id,
                                trigger_type=trigger_type, dataset_id=dataset_id,
                                dataset_row=dataset_row))
            return SimpleNamespace(id=len(created) + 100)

        def fake_submit(case_id, env_id, record_id, row_vars=None,
                        node_config_overrides=None, suppress_notify=False):
            submitted.append((case_id, env_id, record_id, suppress_notify))

        def fake_aggregate(execution_ids, case_id, env_id, dataset_id, case_name):
            aggregates.append((tuple(execution_ids), dataset_id))

        monkeypatch.setattr(sched_mod, "create_execution", fake_create)
        monkeypatch.setattr(sched_mod, "submit_execution", fake_submit)
        monkeypatch.setattr(sched_mod, "submit_batch_aggregate_notify", fake_aggregate)
        return SimpleNamespace(created=created, submitted=submitted, aggregates=aggregates)

    def _mk_db(self, sched_mod_alias, schedule, case=object(), env=object()):
        return FakeDb({
            sched_mod_alias.models.TestSchedule: schedule,
            sched_mod_alias.models.TestCase: case,
            sched_mod_alias.models.Environment: env,
        })

    def test_happy_path_creates_schedule_execution(self, patched, monkeypatch):
        schedule = _schedule(id=7, case_id=11, env_id=22, created_by=5)
        db = self._mk_db(sched_mod, schedule)
        monkeypatch.setattr(sched_mod, "SessionLocal", lambda: db)

        sched_mod._run_schedule_job(7)

        # 记录 trigger_type=schedule，执行人归属 schedule 创建者
        assert patched.created == [dict(case_id=11, env_id=22, user_id=5,
                                        trigger_type="schedule", dataset_id=None, dataset_row=None)]
        assert patched.submitted == [(11, 22, 101, False)]  # 普通用例：不抑制通知
        assert patched.aggregates == []  # 单条无聚合
        assert schedule.last_run_at is not None
        assert db.closed

    def test_bound_case_expands_per_row(self, patched, monkeypatch):
        """数据驱动（周期8）：绑定数据集的用例定时触发按行展开 N 条记录 + 聚合通知"""
        plan = [
            {"dataset_id": 7, "row": {"row_index": 1, "data": {"bl_no": "BL001"}, "label": "BL001"}, "overrides": None},
            {"dataset_id": 7, "row": {"row_index": 2, "data": {"bl_no": "BL002"}, "label": "BL002"}, "overrides": None},
        ]
        case = SimpleNamespace(id=11, dataset_id=7, name="数据驱动用例")
        schedule = _schedule(id=12, case_id=11, env_id=22, created_by=5)
        db = self._mk_db(sched_mod, schedule, case=case)
        monkeypatch.setattr(sched_mod, "SessionLocal", lambda: db)
        monkeypatch.setattr(sched_mod.dataset_service, "plan_case_expansion",
                            lambda db_, c, **kw: plan)

        sched_mod._run_schedule_job(12)

        assert len(patched.created) == 2
        assert all(c["dataset_id"] == 7 and c["dataset_row"]["row_index"] == i + 1
                   for i, c in enumerate(patched.created))
        assert all(c["trigger_type"] == "schedule" for c in patched.created)
        assert [s[3] for s in patched.submitted] == [True, True]  # 抑制逐条
        assert patched.aggregates == [((101, 102), 7)]  # 一条聚合

    def test_zero_rows_swallowed(self, patched, monkeypatch):
        """数据集 0 行：打印跳过，不创建记录，调度线程不崩"""
        def boom(db_, c, **kw):
            raise ValueError("数据集无数据行，请先录入数据再执行")

        schedule = _schedule(id=13)
        db = self._mk_db(sched_mod, schedule, case=SimpleNamespace(dataset_id=7))
        monkeypatch.setattr(sched_mod, "SessionLocal", lambda: db)
        monkeypatch.setattr(sched_mod.dataset_service, "plan_case_expansion", boom)

        sched_mod._run_schedule_job(13)  # 不应抛出

        assert patched.created == []
        assert patched.submitted == []

    def test_schedule_missing_silent(self, patched, monkeypatch):
        db = self._mk_db(sched_mod, None)
        monkeypatch.setattr(sched_mod, "SessionLocal", lambda: db)

        sched_mod._run_schedule_job(404)  # 不应抛错

        assert patched.created == []
        assert patched.submitted == []

    def test_disabled_schedule_removed_without_execution(self, patched, monkeypatch):
        schedule = _schedule(id=8, enabled=False)
        db = self._mk_db(sched_mod, schedule)
        monkeypatch.setattr(sched_mod, "SessionLocal", lambda: db)

        sched_mod._run_schedule_job(8)

        assert patched.created == []

    def test_case_deleted_self_heals_disable(self, patched, monkeypatch):
        """引用的用例已删除：自动禁用 schedule 并清 next_run（自愈不报错）。"""
        schedule = _schedule(id=9, next_run_at="whenever")
        db = self._mk_db(sched_mod, schedule, case=None)
        monkeypatch.setattr(sched_mod, "SessionLocal", lambda: db)

        sched_mod._run_schedule_job(9)

        assert schedule.enabled is False
        assert schedule.next_run_at is None
        assert patched.created == []
        assert db.committed >= 1

    def test_env_deleted_self_heals_disable(self, patched, monkeypatch):
        schedule = _schedule(id=10)
        db = self._mk_db(sched_mod, schedule, env=None)
        monkeypatch.setattr(sched_mod, "SessionLocal", lambda: db)

        sched_mod._run_schedule_job(10)

        assert schedule.enabled is False
        assert patched.created == []

    def test_submit_failure_swallowed(self, patched, monkeypatch):
        """执行提交抛异常：捕获打印，不让调度线程崩掉（不影响下轮触发）。"""
        schedule = _schedule(id=11)
        db = self._mk_db(sched_mod, schedule)
        monkeypatch.setattr(sched_mod, "SessionLocal", lambda: db)

        def boom(case_id, env_id, record_id):
            raise RuntimeError("thread pool down")

        monkeypatch.setattr(sched_mod, "submit_execution", boom)

        sched_mod._run_schedule_job(11)  # 不应抛出

        assert patched.created  # 记录已建（执行会停在 running，由清理任务兜底）


class TestSchedulerDegradation:
    """未安装 APScheduler 的降级行为（沙箱即此形态）。"""

    def test_available_flag_matches_install(self):
        assert sched_mod.scheduler_service.available == sched_mod.APSCHEDULER_AVAILABLE

    def test_unavailable_start_is_noop(self):
        # 未安装时 start 不抛错且不创建调度器（真实启动集成由部署验证）
        if not sched_mod.APSCHEDULER_AVAILABLE:
            svc = SchedulerService()
            svc.start()
            assert svc._scheduler is None

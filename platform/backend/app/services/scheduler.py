"""定时任务调度服务：APScheduler in-process 封装。

设计决策（2026-08 grilling 定稿）：
- 单进程假设：部署为单 worker uvicorn，APScheduler 进程内调度安全；
  启动时检测 WEB_CONCURRENCY>1 打警告（多 worker 会重复触发）
- 优雅降级：未安装 APScheduler 时调度功能整体关闭（available=False），
  路由层返回明确错误，其余功能不受影响（同 DBClient 降级模式）
- 重叠保护：max_instances=1 + coalesce=True——上轮未跑完时本轮跳过合并，
  不会堆积执行
- 错过不补跑：misfire_grace_time=60s，重启窗口内错过的触发直接丢弃
  （MeterSphere 同款语义）
- 时区固定 Asia/Shanghai，用户配置按本地时间理解
- 触发动作复用现有执行通道：execution_launcher（与手动执行同一条编排路径，
  TokenCache 共享锁统一生效），trigger_type="schedule" 落库可溯源
- 配置存 test_schedules / execution_plans 业务表，jobstore 用内存
  （重启时从表全量重建，不引入 SQLAlchemyJobStore 的 pickle 污染）

job id 规范：schedule-{schedule_id}（单用例定时）/ plan-{plan_id}（方案内嵌定时），
与业务表主键一一对应；reload 双源扫描两张业务表全量重建。
"""
import os
import threading
from datetime import datetime

try:
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger
    from apscheduler.triggers.interval import IntervalTrigger

    APSCHEDULER_AVAILABLE = True
except ImportError:
    APSCHEDULER_AVAILABLE = False

TZ = "Asia/Shanghai"
MISFIRE_GRACE = 60  # 秒：错过超过 60s 的触发直接丢弃，不补跑

from .. import models
from ..database import SessionLocal
from .execution_launcher import build_launch_plan, commit_launch
from .plan_executor import run_plan


def _job_id(schedule_id: int) -> str:
    return f"schedule-{schedule_id}"


def _plan_job_id(plan_id: int) -> str:
    return f"plan-{plan_id}"


class SchedulerService:
    """进程内单例调度器；APScheduler 缺失时所有方法降级为 no-op"""

    def __init__(self):
        self._scheduler: BackgroundScheduler | None = None
        self._lock = threading.Lock()

    @property
    def available(self) -> bool:
        return APSCHEDULER_AVAILABLE

    def start(self) -> None:
        """启动调度器并从业务表全量加载启用中的定时任务（应用 startup 时调用）"""
        if not APSCHEDULER_AVAILABLE:
            print("[定时任务] 未安装 APScheduler，定时执行功能已关闭（pip install APScheduler 后重启启用）")
            return
        if os.getenv("WEB_CONCURRENCY", "1") not in ("1", ""):
            print("[定时任务][警告] 检测到多 worker 部署，定时任务会重复触发！请保持单 worker 或将调度独立部署")
        with self._lock:
            if self._scheduler is not None:
                return
            self._scheduler = BackgroundScheduler(timezone=TZ)
            self._scheduler.start()
        # 先移除孤儿 job（上次运行遗留的已删任务），再加载当前启用项
        self.reload()

    def shutdown(self) -> None:
        with self._lock:
            if self._scheduler is not None:
                self._scheduler.shutdown(wait=False)
                self._scheduler = None

    # ---------- 业务表 ↔ 调度器 同步 ----------
    def reload(self) -> None:
        """按业务表全量重建 job（启动时用；运行期增删改走 add/remove 单点同步）。

        双源扫描：单用例定时（test_schedules）+ 方案内嵌定时
        （execution_plans：配置了 schedule_type 且双开关开）。
        """
        if self._scheduler is None:
            return
        db = SessionLocal()
        try:
            schedules = db.query(models.TestSchedule).filter(models.TestSchedule.enabled.is_(True)).all()
            plans = db.query(models.ExecutionPlan).filter(
                models.ExecutionPlan.enabled.is_(True),
                models.ExecutionPlan.schedule_enabled.is_(True),
                models.ExecutionPlan.schedule_type.isnot(None)).all()
            live_ids = {_job_id(s.id) for s in schedules} | {_plan_job_id(p.id) for p in plans}
            # 清理孤儿 job：调度器里有但业务表已删/已停用
            for job in self._scheduler.get_jobs():
                if job.id not in live_ids:
                    self._scheduler.remove_job(job.id)
            count = 0
            for s in schedules:
                before = len(self._scheduler.get_jobs())
                self._upsert_job(s)
                if len(self._scheduler.get_jobs()) > before:
                    count += 1
            plan_count = 0
            for p in plans:
                before = len(self._scheduler.get_jobs())
                self._upsert_plan_job(p)
                if len(self._scheduler.get_jobs()) > before:
                    plan_count += 1
            if schedules or plans:
                print(f"[定时任务] 已加载 {count}/{len(schedules)} 个用例定时、"
                      f"{plan_count}/{len(plans)} 个方案定时")
        finally:
            db.close()

    def _upsert_job(self, schedule: models.TestSchedule) -> None:
        """按 schedule 配置构建触发器并注册/替换 job；配置非法时跳过（不中断其他任务）"""
        assert self._scheduler is not None
        trigger = self._build_trigger(schedule.schedule_type, schedule.interval_minutes, schedule.daily_time)
        if trigger is None:
            print(f"[定时任务] schedule#{schedule.id} 触发配置非法（type={schedule.schedule_type}），已跳过")
            return
        self._scheduler.add_job(
            _run_schedule_job,
            trigger=trigger,
            id=_job_id(schedule.id),
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            misfire_grace_time=MISFIRE_GRACE,
            kwargs={"schedule_id": schedule.id},
        )
        self._sync_next_run(schedule.id)

    def _upsert_plan_job(self, plan: models.ExecutionPlan) -> None:
        """按方案内嵌定时构建触发器并注册/替换 job；配置非法时跳过"""
        assert self._scheduler is not None
        trigger = self._build_trigger(plan.schedule_type, plan.schedule_interval_minutes,
                                      plan.schedule_daily_time)
        if trigger is None:
            print(f"[方案定时] plan#{plan.id} 触发配置非法（type={plan.schedule_type}），已跳过")
            return
        self._scheduler.add_job(
            _run_plan_job,
            trigger=trigger,
            id=_plan_job_id(plan.id),
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            misfire_grace_time=MISFIRE_GRACE,
            kwargs={"plan_id": plan.id},
        )
        self._sync_next_run(plan.id, is_plan=True)

    @staticmethod
    def _build_trigger(schedule_type, interval_minutes, daily_time):
        """interval → IntervalTrigger；daily → CronTrigger；非法配置返回 None。
        单用例定时与方案内嵌定时共用（B 方案：字段名在调用方对齐）"""
        if schedule_type == "interval":
            minutes = interval_minutes or 0
            if minutes < 1:
                return None
            return IntervalTrigger(minutes=minutes, timezone=TZ)
        if schedule_type == "daily":
            hh, mm = _parse_daily_time(daily_time)
            if hh is None:
                return None
            return CronTrigger(hour=hh, minute=mm, timezone=TZ)
        return None

    def _sync_next_run(self, schedule_id: int, *, is_plan: bool = False) -> None:
        """把调度器计算的下次触发时间回写业务表（冗余展示字段；两源共用）"""
        assert self._scheduler is not None
        db = SessionLocal()
        try:
            jid = _plan_job_id(schedule_id) if is_plan else _job_id(schedule_id)
            job = self._scheduler.get_job(jid)
            if not job or not job.next_run_time:
                return
            model = models.ExecutionPlan if is_plan else models.TestSchedule
            row = db.query(model).filter(model.id == schedule_id).first()
            if row:
                row.next_run_at = job.next_run_time.replace(tzinfo=None)
                db.commit()
        finally:
            db.close()

    # ---------- 运行期单点同步（路由层调用） ----------
    def add_or_update(self, schedule: models.TestSchedule) -> None:
        """新增/更新定时任务：启用则注册 job，禁用则移除"""
        if self._scheduler is None:
            return
        if schedule.enabled:
            self._upsert_job(schedule)
        else:
            self.remove(schedule.id)

    def remove(self, schedule_id: int) -> None:
        if self._scheduler is None:
            return
        try:
            self._scheduler.remove_job(_job_id(schedule_id))
        except Exception:
            pass  # job 不存在（未启用/已移除）视为幂等成功

    # ---------- 方案内嵌定时（B 方案）：与单用例定时平行的同步入口 ----------
    def upsert_plan_job(self, plan: models.ExecutionPlan) -> None:
        """方案定时增改后的同步入口（plans 路由调用）：
        配置了 schedule_type 且方案/定时双开关开 → 注册，否则移除 job"""
        if self._scheduler is None:
            return
        if plan.schedule_type and plan.enabled and plan.schedule_enabled:
            self._upsert_plan_job(plan)
        else:
            self.remove_plan_job(plan.id)

    def remove_plan_job(self, plan_id: int) -> None:
        """方案删除/清定时时移除 job（幂等；执行记录 plan_id 无外键、历史存活）"""
        if self._scheduler is None:
            return
        try:
            self._scheduler.remove_job(_plan_job_id(plan_id))
        except Exception:
            pass

    def remove_by_case(self, case_id: int) -> None:
        """删除用例时连带清理其所有定时 job（业务表由路由层级联删）"""
        if self._scheduler is None:
            return
        db = SessionLocal()
        try:
            ids = [s.id for s in db.query(models.TestSchedule).filter(models.TestSchedule.case_id == case_id).all()]
            for sid in ids:
                self.remove(sid)
        finally:
            db.close()

    def remove_by_env(self, env_id: int) -> None:
        """删除环境时连带清理引用该环境的定时 job（业务表由路由层删）"""
        if self._scheduler is None:
            return
        db = SessionLocal()
        try:
            ids = [s.id for s in db.query(models.TestSchedule).filter(models.TestSchedule.env_id == env_id).all()]
            for sid in ids:
                self.remove(sid)
        finally:
            db.close()

    def trigger_now(self, schedule_id: int) -> bool:
        """立即触发一次（「立即执行」按钮）：直接执行任务函数，不走调度排队"""
        _run_schedule_job(schedule_id)
        return True


def _parse_daily_time(value: str | None):
    """解析 HH:MM；非法返回 (None, None)"""
    if not value or ":" not in value:
        return None, None
    try:
        parts = value.split(":", 1)
        hh, mm = int(parts[0]), int(parts[1])
        if 0 <= hh <= 23 and 0 <= mm <= 59:
            return hh, mm
    except (ValueError, IndexError):
        pass
    return None, None


def _validate_schedule_payload(schedule_type, interval_minutes, daily_time) -> None:
    """调度配置整体校验（单用例定时与方案内嵌定时共用口径）；非法抛 ValueError。

    路由层捕获转 400/503，错误信息直给前端。
    """
    if schedule_type not in ("interval", "daily"):
        raise ValueError("schedule_type 仅支持 interval / daily")
    if schedule_type == "interval":
        if not interval_minutes or interval_minutes < 1:
            raise ValueError("间隔分钟数必须 ≥ 1")
    else:
        hh, _ = _parse_daily_time(daily_time)
        if hh is None:
            raise ValueError("每日时刻格式应为 HH:MM（24小时制）")


def _run_schedule_job(schedule_id: int) -> None:
    """定时触发动作：加载 schedule → 校验用例存在 → 创建执行记录 → 提交线程池。

    与手动执行同一条编排路径（execution_launcher），TokenCache 共享登录统一生效。
    环境严格绑定：执行环境取 case.env_id（schedule 上的 env_id 已废止）。
    用例已被删除时静默禁用该 schedule 并移除 job（自愈，不报错刷屏）。
    """
    db = SessionLocal()
    try:
        schedule = db.query(models.TestSchedule).filter(models.TestSchedule.id == schedule_id).first()
        if not schedule:
            return
        if not schedule.enabled:
            scheduler_service.remove(schedule_id)
            return
        case = db.query(models.TestCase).filter(models.TestCase.id == schedule.case_id).first()
        if not case:
            # 引用用例已删除：自愈——禁用并移除
            schedule.enabled = False
            schedule.next_run_at = None
            db.commit()
            scheduler_service.remove(schedule_id)
            print(f"[定时任务] schedule#{schedule_id} 引用的用例已删除，已自动禁用")
            return
        # 记录最近触发时间；执行人归属 schedule 创建者（审计可追溯）
        schedule.last_run_at = datetime.now()
        db.commit()
        # 数据驱动（周期8）：绑定数据集的用例按行展开，每行一条 trigger_type=schedule 记录；
        # 多行批量失败聚合成一条通知（与手动执行同策略，编排统一在 execution_launcher）
        try:
            assert schedule.created_by is not None  # 定时任务必由用户创建
            plan = build_launch_plan(db, case, schedule.created_by,
                                     trigger_type="schedule")
            commit_launch([plan])
        except ValueError as e:
            print(f"[定时任务] schedule#{schedule_id} 数据集不可执行，跳过本轮: {e}")
    except Exception as e:
        print(f"[定时任务] schedule#{schedule_id} 触发失败: {e}")
    finally:
        db.close()


def _run_plan_job(plan_id: int) -> None:
    """方案定时触发动作：加载方案 → 双开关校验 → run_plan（trigger_type=plan_schedule）。

    与手动一键同一条编排路径（plan_executor），成员失败互不影响；
    方案已删除 → 移除 job（自愈）；预检失败（成员用例/数据集不可执行）→
    打印跳过本轮（自愈语义，同单用例定时对 ValueError 的处理）。
    last_run_at 由 run_plan 回写；执行人归属方案创建者（审计可追溯）。
    """
    db = SessionLocal()
    try:
        plan = db.query(models.ExecutionPlan).filter(models.ExecutionPlan.id == plan_id).first()
        if not plan:
            scheduler_service.remove_plan_job(plan_id)
            return
        if not plan.enabled or not plan.schedule_enabled:
            print(f"[方案定时] plan#{plan_id} 方案/定时开关已关，跳过本轮")
            return
        assert plan.created_by is not None  # 方案必由用户创建
        run_plan(db, plan, plan.created_by, trigger_type="plan_schedule")
    except ValueError as e:
        print(f"[方案定时] plan#{plan_id} 成员预检失败，跳过本轮: {e}")
    except Exception as e:
        print(f"[方案定时] plan#{plan_id} 触发失败: {e}")
    finally:
        db.close()


scheduler_service = SchedulerService()

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
- 触发动作复用现有执行通道：创建 ExecutionRecord(trigger_type="schedule")
  → submit_execution 线程池，与手动执行同一路径（TokenCache 共享锁统一生效）
- 配置存 test_schedules 业务表，jobstore 用内存（重启时从表全量重建，
  不引入 SQLAlchemyJobStore 的 pickle 污染）

job id 规范：schedule-{schedule_id}，与业务表主键一一对应。
"""
import os
import threading
from datetime import datetime
from typing import Optional

try:
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger
    from apscheduler.triggers.interval import IntervalTrigger

    APSCHEDULER_AVAILABLE = True
except ImportError:
    APSCHEDULER_AVAILABLE = False

TZ = "Asia/Shanghai"
MISFIRE_GRACE = 60  # 秒：错过超过 60s 的触发直接丢弃，不补跑

from ..database import SessionLocal
from .. import models
from ..crud.executions import create_execution
from ..engine.runner import submit_execution


def _job_id(schedule_id: int) -> str:
    return f"schedule-{schedule_id}"


class SchedulerService:
    """进程内单例调度器；APScheduler 缺失时所有方法降级为 no-op"""

    def __init__(self):
        self._scheduler: Optional["BackgroundScheduler"] = None
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
        """按业务表全量重建 job（启动时用；运行期增删改走 add/remove 单点同步）"""
        if self._scheduler is None:
            return
        db = SessionLocal()
        try:
            schedules = db.query(models.TestSchedule).filter(models.TestSchedule.enabled.is_(True)).all()
            live_ids = {_job_id(s.id) for s in schedules}
            # 清理孤儿 job：调度器里有但业务表已删/已禁用
            for job in self._scheduler.get_jobs():
                if job.id not in live_ids:
                    self._scheduler.remove_job(job.id)
            count = 0
            for s in schedules:
                before = len(self._scheduler.get_jobs())
                self._upsert_job(s)
                if len(self._scheduler.get_jobs()) > before:
                    count += 1
            if schedules:
                print(f"[定时任务] 已加载 {count}/{len(schedules)} 个启用的定时任务")
        finally:
            db.close()

    def _upsert_job(self, schedule: models.TestSchedule) -> None:
        """按 schedule 配置构建触发器并注册/替换 job；配置非法时跳过（不中断其他任务）"""
        assert self._scheduler is not None
        trigger = self._build_trigger(schedule)
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

    def _build_trigger(self, schedule: models.TestSchedule):
        """interval → IntervalTrigger；daily → CronTrigger；非法配置返回 None"""
        if schedule.schedule_type == "interval":
            minutes = schedule.interval_minutes or 0
            if minutes < 1:
                return None
            return IntervalTrigger(minutes=minutes, timezone=TZ)
        if schedule.schedule_type == "daily":
            hh, mm = _parse_daily_time(schedule.daily_time)
            if hh is None:
                return None
            return CronTrigger(hour=hh, minute=mm, timezone=TZ)
        return None

    def _sync_next_run(self, schedule_id: int) -> None:
        """把调度器计算的下次触发时间回写业务表（冗余展示字段）"""
        assert self._scheduler is not None
        db = SessionLocal()
        try:
            job = self._scheduler.get_job(_job_id(schedule_id))
            if not job or not job.next_run_time:
                return
            row = db.query(models.TestSchedule).filter(models.TestSchedule.id == schedule_id).first()
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


def _parse_daily_time(value: Optional[str]):
    """解析 HH:MM；非法返回 (None, None)"""
    if not value or ":" not in value:
        return None, None
    try:
        hh, mm = value.split(":", 1)
        hh, mm = int(hh), int(mm)
        if 0 <= hh <= 23 and 0 <= mm <= 59:
            return hh, mm
    except ValueError:
        pass
    return None, None


def _run_schedule_job(schedule_id: int) -> None:
    """定时触发动作：加载 schedule → 校验用例/环境存在 → 创建执行记录 → 提交线程池。

    与手动执行同一路径（submit_execution），TokenCache 共享登录统一生效。
    用例/环境已被删除时静默禁用该 schedule 并移除 job（自愈，不报错刷屏）。
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
        env = db.query(models.Environment).filter(models.Environment.id == schedule.env_id).first()
        if not case or not env:
            # 引用对象已删除：自愈——禁用并移除
            schedule.enabled = False
            schedule.next_run_at = None
            db.commit()
            scheduler_service.remove(schedule_id)
            print(f"[定时任务] schedule#{schedule_id} 引用的用例/环境已删除，已自动禁用")
            return
        # 记录最近触发时间；执行人归属 schedule 创建者（审计可追溯）
        schedule.last_run_at = datetime.now()
        db.commit()
        record = create_execution(db, case_id=schedule.case_id, env_id=schedule.env_id,
                                  user_id=schedule.created_by, trigger_type="schedule")
        submit_execution(schedule.case_id, schedule.env_id, record.id)
    except Exception as e:
        print(f"[定时任务] schedule#{schedule_id} 触发失败: {e}")
    finally:
        db.close()


scheduler_service = SchedulerService()

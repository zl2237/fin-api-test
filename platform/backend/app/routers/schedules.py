"""定时任务路由：用例管理页行内联入口的后端支撑。

权限与用例一致（登录即可管理）；创建/更新/启停/立即触发均可。
调度器未安装（APScheduler 缺失）时创建/更新返回 503 明确提示，查询不受影响。
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import crud, models, schemas
from ..auth import get_current_user
from ..database import get_db
from ..services.scheduler import _parse_daily_time, scheduler_service

router = APIRouter(prefix="/api/schedules", tags=["定时任务"])


def _validate_payload(schedule_type, interval_minutes, daily_time):
    """校验调度配置：类型合法 + 对应参数存在且合法；错误信息直给前端"""
    if schedule_type not in ("interval", "daily"):
        raise HTTPException(400, "schedule_type 仅支持 interval / daily")
    if schedule_type == "interval":
        if not interval_minutes or interval_minutes < 1:
            raise HTTPException(400, "间隔分钟数必须 ≥ 1")
    else:
        hh, mm = _parse_daily_time(daily_time)
        if hh is None:
            raise HTTPException(400, "每日时刻格式应为 HH:MM（24小时制）")


def _require_scheduler():
    """APScheduler 未安装时创建/更新操作明确失败（查询与启停不受影响）"""
    if not scheduler_service.available:
        raise HTTPException(503, "定时任务功能未启用：服务器未安装 APScheduler")


def _fill_names(db: Session, obj: models.TestSchedule) -> models.TestSchedule:
    obj.case_name = obj.case.name if obj.case else None
    obj.env_name = obj.env.name if obj.env else None
    crud.fill_audit_names(db, obj)
    return obj


@router.get("", response_model=list[schemas.TestScheduleOut])
def list_schedules(project_id: int | None = None, case_id: int | None = None,
                   db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """列出定时任务：project_id 过滤该项目的（用例归属项目），case_id 过滤单用例的"""
    q = db.query(models.TestSchedule)
    if case_id:
        q = q.filter(models.TestSchedule.case_id == case_id)
    if project_id:
        q = q.join(models.TestCase, models.TestSchedule.case_id == models.TestCase.id).filter(
            models.TestCase.project_id == project_id)
    objs = q.order_by(models.TestSchedule.id.desc()).all()
    return [_fill_names(db, o) for o in objs]


@router.post("", response_model=schemas.TestScheduleOut)
def create(data: schemas.TestScheduleCreate, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    _require_scheduler()
    _validate_payload(data.schedule_type, data.interval_minutes, data.daily_time)
    if not crud.get_testcase(db, data.case_id):
        raise HTTPException(404, "用例不存在")
    if not crud.get_environment(db, data.env_id):
        raise HTTPException(404, "环境不存在")

    obj = models.TestSchedule(
        case_id=data.case_id, env_id=data.env_id,
        schedule_type=data.schedule_type,
        interval_minutes=data.interval_minutes if data.schedule_type == "interval" else None,
        daily_time=data.daily_time if data.schedule_type == "daily" else None,
        enabled=data.enabled, created_by=user.id, updated_by=user.id,
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    scheduler_service.add_or_update(obj)
    db.refresh(obj)  # _sync_next_run 已回写 next_run_at
    crud.log_operation(db, user, "create", "schedule", obj.id, f"case#{obj.case_id}")
    return _fill_names(db, obj)


@router.put("/{schedule_id}", response_model=schemas.TestScheduleOut)
def update(schedule_id: int, data: schemas.TestScheduleUpdate, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    _require_scheduler()
    obj = db.query(models.TestSchedule).filter(models.TestSchedule.id == schedule_id).first()
    if not obj:
        raise HTTPException(404, "定时任务不存在")

    # 合并后的最终配置做整体校验（避免局部更新漏配必填项）
    schedule_type = data.schedule_type or obj.schedule_type
    interval_minutes = data.interval_minutes if data.interval_minutes is not None else obj.interval_minutes
    daily_time = data.daily_time if data.daily_time is not None else obj.daily_time
    _validate_payload(schedule_type, interval_minutes, daily_time)
    if data.env_id is not None and not crud.get_environment(db, data.env_id):
        raise HTTPException(404, "环境不存在")

    obj.env_id = data.env_id if data.env_id is not None else obj.env_id
    obj.schedule_type = schedule_type
    # 按最终类型收纳参数：interval 只留分钟，daily 只留时刻，防止脏数据残留
    obj.interval_minutes = interval_minutes if schedule_type == "interval" else None
    obj.daily_time = daily_time if schedule_type == "daily" else None
    obj.enabled = data.enabled if data.enabled is not None else obj.enabled
    obj.updated_by = user.id
    db.commit()
    db.refresh(obj)
    scheduler_service.add_or_update(obj)
    db.refresh(obj)
    crud.log_operation(db, user, "update", "schedule", obj.id, f"case#{obj.case_id}")
    return _fill_names(db, obj)


@router.delete("/{schedule_id}")
def delete(schedule_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    obj = db.query(models.TestSchedule).filter(models.TestSchedule.id == schedule_id).first()
    if not obj:
        raise HTTPException(404, "定时任务不存在")
    db.delete(obj)
    db.commit()
    scheduler_service.remove(schedule_id)
    crud.log_operation(db, user, "delete", "schedule", obj.id, f"case#{obj.case_id}")
    return {"message": "已删除"}


@router.post("/{schedule_id}/run")
def run_now(schedule_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """立即执行一次（不等调度到达）：走定时任务同一路径，记录 trigger_type=schedule"""
    _require_scheduler()
    obj = db.query(models.TestSchedule).filter(models.TestSchedule.id == schedule_id).first()
    if not obj:
        raise HTTPException(404, "定时任务不存在")
    from ..services.scheduler import _run_schedule_job
    _run_schedule_job(schedule_id)
    crud.log_operation(db, user, "execute", "schedule", obj.id, f"case#{obj.case_id}")
    return {"message": "已触发执行"}

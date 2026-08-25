"""操作日志路由：仅管理员可查看"""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..auth import get_current_user
from ..database import get_db

router = APIRouter(prefix="/api/operation-logs", tags=["操作日志"])


def _require_admin(user: models.User = Depends(get_current_user)) -> models.User:
    if user.role != "admin":
        raise HTTPException(403, "需要管理员权限")
    return user


@router.get("", response_model=list[schemas.OperationLogOut])
def list_logs(
    action: str | None = None,
    target_type: str | None = None,
    user_id: int | None = None,
    limit: int = 100,
    db: Session = Depends(get_db),
    _admin: models.User = Depends(_require_admin),
):
    """查询操作日志（仅 admin），支持按操作类型、目标类型、操作人筛选，默认最近100条"""
    q = db.query(models.OperationLog)
    if action:
        q = q.filter(models.OperationLog.action == action)
    if target_type:
        q = q.filter(models.OperationLog.target_type == target_type)
    if user_id:
        q = q.filter(models.OperationLog.user_id == user_id)
    return q.order_by(models.OperationLog.id.desc()).limit(limit).all()


@router.delete("/cleanup")
def cleanup_logs(
    days: int = 30,
    db: Session = Depends(get_db),
    _admin: models.User = Depends(_require_admin),
):
    """手动清理指定天数前的操作日志，仅管理员可操作。"""
    if days < 1:
        raise HTTPException(400, "天数必须大于 0")
    cutoff = datetime.now() - timedelta(days=days)
    old_logs = db.query(models.OperationLog).filter(
        models.OperationLog.created_at < cutoff
    ).all()
    count = len(old_logs)
    for log_obj in old_logs:
        db.delete(log_obj)
    db.commit()
    return {"message": f"已清理 {count} 条 {days} 天前的操作日志", "deleted": count, "days": days}

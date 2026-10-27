"""方案域（执行方案）：查询与成员数聚合。

方案 = 执行配置组合（成员独立并行，语义见 services/plan_executor）；
业务校验在服务层，本模块只做数据访问。审计名回填复用 crud.fill_audit_names。
"""
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import models


def get_plan(db: Session, plan_id: int) -> models.ExecutionPlan | None:
    return db.query(models.ExecutionPlan).filter(models.ExecutionPlan.id == plan_id).first()


def list_plans(db: Session, project_id: int | None = None) -> list[models.ExecutionPlan]:
    """方案列表（新→旧），每项挂 item_count（数据库端聚合，展示字段非列）。"""
    q = db.query(models.ExecutionPlan)
    if project_id is not None:
        q = q.filter(models.ExecutionPlan.project_id == project_id)
    objs = q.order_by(models.ExecutionPlan.id.desc()).all()
    counts = {}
    if objs:
        rows = db.query(models.ExecutionPlanItem.plan_id, func.count()).filter(
            models.ExecutionPlanItem.plan_id.in_([o.id for o in objs])).group_by(
            models.ExecutionPlanItem.plan_id).all()
        counts = {r[0]: r[1] for r in rows}
    for o in objs:
        setattr(o, "item_count", counts.get(o.id, 0))
    return objs

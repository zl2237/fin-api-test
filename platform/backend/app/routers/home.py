"""工作台聚合：一次请求喂饱首页（2026-10-12 性能修复）。

首页旧实现并发拉 4 个重接口——GET /apis 全量（225 接口完整字段表+请求模板）、
testcases 全量（每条含 dag_config/node_configs 大 JSON）、executions limit=200
完整记录、stats——只为 4 个数字 + 8 条最近执行 + 3 个快速执行候选。
本接口按需轻量取数：count 聚合、最近执行只选列表所需列、快速执行候选取
「最近执行过的用例」（按最近一次执行倒序去重，替代旧 cases.slice(0,3)）。
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import models, schemas
from ..auth import get_current_user
from ..crud.executions import aggregate_stats
from ..database import get_db

router = APIRouter(prefix="/api", tags=["首页"])

RECENT_EXEC_LIMIT = 8
RECENT_CASE_LIMIT = 3


def _recent_execs(db: Session, project_id: int) -> list[schemas.HomeRecentExecOut]:
    """最近执行（只选列表所需列，不拉 dataset_row/请求快照等重列）。"""
    rows = (db.query(models.ExecutionRecord.id, models.ExecutionRecord.case_id,
                     models.TestCase.name, models.ExecutionRecord.env_id,
                     models.ExecutionRecord.status, models.ExecutionRecord.summary,
                     models.ExecutionRecord.started_at)
            .join(models.TestCase, models.ExecutionRecord.case_id == models.TestCase.id)
            .filter(models.TestCase.project_id == project_id)
            .order_by(models.ExecutionRecord.id.desc())
            .limit(RECENT_EXEC_LIMIT).all())
    env_ids = {r[3] for r in rows if r[3]}
    env_map: dict[int, str] = (
        {r[0]: r[1] for r in db.query(models.Environment.id, models.Environment.name)
         .filter(models.Environment.id.in_(env_ids)).all()}
        if env_ids else {})
    return [schemas.HomeRecentExecOut(
        id=r[0], case_id=r[1], case_name=r[2], env_id=r[3],
        env_name=env_map.get(r[3]), status=r[4], summary=r[5], started_at=r[6])
        for r in rows]


def _recent_cases(db: Session, project_id: int) -> list[schemas.HomeRecentCaseOut]:
    """快速执行候选：最近执行过的用例（每用例最近一条执行，按其 id 倒序去重取前 N）。"""
    latest = (db.query(models.ExecutionRecord.case_id,
                       func.max(models.ExecutionRecord.id).label("mid"))
              .join(models.TestCase, models.ExecutionRecord.case_id == models.TestCase.id)
              .filter(models.TestCase.project_id == project_id)
              .group_by(models.ExecutionRecord.case_id)
              .order_by(func.max(models.ExecutionRecord.id).desc())
              .limit(RECENT_CASE_LIMIT).subquery())
    rows = (db.query(models.TestCase.id, models.TestCase.name)
            .join(latest, models.TestCase.id == latest.c.case_id)
            .order_by(latest.c.mid.desc()).all())
    return [schemas.HomeRecentCaseOut(id=r[0], name=r[1]) for r in rows]


@router.get("/home/summary", response_model=schemas.HomeSummaryOut)
def home_summary(project_id: int, days: int = 7,
                 db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """首页聚合（一个接口替代 4 个重列表请求）。"""
    if days < 1 or days > 365:
        raise HTTPException(400, "天数须在 1~365 之间")
    api_count = (db.query(func.count(models.ApiDefinition.id))
                 .filter(models.ApiDefinition.project_id == project_id).scalar() or 0)
    case_count = (db.query(func.count(models.TestCase.id))
                  .filter(models.TestCase.project_id == project_id).scalar() or 0)
    return schemas.HomeSummaryOut(
        api_count=api_count, case_count=case_count,
        stats=schemas.ExecutionStatsOut(**aggregate_stats(db, project_id, days)),
        recent_execs=_recent_execs(db, project_id),
        recent_cases=_recent_cases(db, project_id),
    )

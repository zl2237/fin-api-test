from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from .. import models, schemas, crud
from ..auth import get_current_user

router = APIRouter(prefix="/api/reports", tags=["报告"])


@router.get("/executions/{exec_id}", response_model=schemas.ExecutionRecordOut)
def get_report(exec_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """获取完整执行报告（含 steps + assertions）"""
    obj = db.query(models.ExecutionRecord).filter(models.ExecutionRecord.id == exec_id).first()
    if not obj:
        raise HTTPException(404, "执行记录不存在")
    crud.fill_audit_names(db, obj)
    crud.fill_exec_names(db, obj)
    return obj


@router.get("/executions/{exec_id}/steps/{step_id}/assertions",
            response_model=list[schemas.AssertionRecordOut])
def get_step_assertions(exec_id: int, step_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    step = db.query(models.StepRecord).filter(
        models.StepRecord.id == step_id,
        models.StepRecord.execution_id == exec_id,
    ).first()
    if not step:
        raise HTTPException(404, "步骤不存在")
    return step.assertions

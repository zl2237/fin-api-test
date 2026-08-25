from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from .. import crud, models, schemas
from ..auth import get_current_user
from ..database import get_db
from ..services.report_export import export_report_html, export_steps_csv

router = APIRouter(prefix="/api/reports", tags=["报告"])


@router.get("/executions/{exec_id}", response_model=schemas.ExecutionRecordOut)
def get_report(exec_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """获取完整执行报告（含 steps + assertions）"""
    obj = crud.get_execution(db, exec_id)
    if not obj:
        raise HTTPException(404, "执行记录不存在")
    crud.fill_audit_names(db, obj)
    crud.fill_exec_names(db, obj)
    return obj


@router.get("/executions/{exec_id}/export")
def export_report(exec_id: int, format: str = Query("csv", pattern="^(csv|html)$"),
                  db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """导出执行报告（csv=Excel 兼容表格；html=自包含单文件报告）。
    导出逻辑在后端 services.report_export，CI/定时任务等非交互方可直接复用。"""
    obj = crud.get_execution(db, exec_id)
    if not obj:
        raise HTTPException(404, "执行记录不存在")
    crud.fill_audit_names(db, obj)
    crud.fill_exec_names(db, obj)
    if format == "html":
        content = export_report_html(obj, obj.steps or []).encode("utf-8")
        media, ext = "text/html; charset=utf-8", "html"
    else:
        content = export_steps_csv(obj.steps or []).encode("utf-8")
        media, ext = "text/csv; charset=utf-8", "csv"
    filename = f"report_{exec_id}.{ext}"
    return Response(
        content=content,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


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

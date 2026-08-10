from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from .. import crud, schemas, models
from ..auth import get_current_user
from ..engine.runner import submit_execution, submit_batch_execution

router = APIRouter(prefix="/api", tags=["执行"])


@router.post("/testcases/{case_id}/execute", response_model=schemas.ExecutionRecordOut)
def execute(case_id: int, data: schemas.ExecutionCreate, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """触发用例执行（异步）：立即创建 running 状态的执行记录并返回，后台线程池执行。
    前端通过 GET /executions/{id} 轮询执行状态。"""
    if data.case_id != case_id:
        raise HTTPException(400, "case_id 不一致")
    case = crud.get_testcase(db, case_id)
    if not case:
        raise HTTPException(404, f"用例不存在: {case_id}")
    env = crud.get_environment(db, data.env_id)
    if not env:
        raise HTTPException(404, f"环境不存在: {data.env_id}")

    # 先创建 running 状态的执行记录，立即返回给前端
    record = models.ExecutionRecord(
        case_id=case_id, env_id=data.env_id, status="running", created_by=user.id,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    crud.fill_audit_names(db, record)
    crud.fill_exec_names(db, record)

    # 提交到后台线程池执行（非阻塞）
    submit_execution(case_id, data.env_id, record.id)
    return record


@router.post("/testcases/batch-execute", response_model=list[schemas.ExecutionRecordOut])
def batch_execute(data: schemas.BatchExecutionCreate, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """批量执行多个用例（串行）：为每个用例创建 running 状态的执行记录并立即返回，
    后台线程池串行执行，一个结束再执行下一个。前端可轮询各 record 状态。"""
    if not data.case_ids:
        raise HTTPException(400, "请至少选择一个用例")
    env = crud.get_environment(db, data.env_id)
    if not env:
        raise HTTPException(404, f"环境不存在: {data.env_id}")

    records = []
    for case_id in data.case_ids:
        case = crud.get_testcase(db, case_id)
        if not case:
            raise HTTPException(404, f"用例不存在: {case_id}")
        record = models.ExecutionRecord(
            case_id=case_id, env_id=data.env_id, status="running", created_by=user.id,
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        crud.fill_audit_names(db, record)
        crud.fill_exec_names(db, record)
        records.append(record)

    # 提交批量串行执行（非阻塞）
    submit_batch_execution([r.id for r in records], data.case_ids, data.env_id)
    return records


@router.get("/executions", response_model=list[schemas.ExecutionRecordOut])
def list_executions(case_id: int | None = None, project_id: int | None = None, created_by: int | None = None, limit: int = 50, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    objs = crud.list_executions(db, case_id, project_id, created_by, limit)
    crud.fill_audit_names_batch(db, objs)
    crud.fill_exec_names(db, objs)
    return objs


@router.delete("/executions/cleanup")
def cleanup_executions(days: int = 30, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """手动清理指定天数前的执行记录（含步骤和断言），仅管理员可操作。需在 /{exec_id} 之前注册。"""
    if user.role != "admin":
        raise HTTPException(403, "需要管理员权限")
    if days < 1:
        raise HTTPException(400, "天数必须大于 0")
    cutoff = datetime.now() - timedelta(days=days)
    # StepRecord/AssertionRecord 通过 ORM 级联删除
    old_execs = db.query(models.ExecutionRecord).filter(
        models.ExecutionRecord.started_at < cutoff
    ).all()
    count = len(old_execs)
    for exec_obj in old_execs:
        db.delete(exec_obj)
    db.commit()
    return {"message": f"已清理 {count} 条 {days} 天前的执行记录", "deleted": count, "days": days}


@router.get("/executions/{exec_id}", response_model=schemas.ExecutionRecordOut)
def get_execution(exec_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    obj = crud.get_execution(db, exec_id)
    if not obj:
        raise HTTPException(404, "执行记录不存在")
    crud.fill_audit_names(db, obj)
    crud.fill_exec_names(db, obj)
    return obj

"""executions 域：执行记录的创建与清理。

router 只管 HTTP 语义与触发线程池；记录创建/批量创建/清理收敛到此，
消除 router 内联 ORM 与 legacy 中无人调用的 create_execution 死代码。
"""
from datetime import datetime

from sqlalchemy.orm import Session

from .. import models


def create_execution(db: Session, case_id: int, env_id: int, user_id: int,
                     trigger_type: str = "manual",
                     dataset_id: int = None, dataset_row: dict = None) -> models.ExecutionRecord:
    """创建 running 状态的执行记录（触发执行前先落库，前端立即可轮询）。

    dataset_id/dataset_row：数据驱动执行时的数据行快照（失败可溯源是哪行）。
    """
    record = models.ExecutionRecord(
        case_id=case_id, env_id=env_id, status="running", created_by=user_id,
        trigger_type=trigger_type, dataset_id=dataset_id, dataset_row=dataset_row,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def cleanup_old_records(db: Session, cutoff: datetime) -> int:
    """删除 started_at 早于 cutoff 的执行记录（Step/Assertion 级联），返回删除数"""
    old_execs = db.query(models.ExecutionRecord).filter(
        models.ExecutionRecord.started_at < cutoff
    ).all()
    for exec_obj in old_execs:
        db.delete(exec_obj)
    db.commit()
    return len(old_execs)

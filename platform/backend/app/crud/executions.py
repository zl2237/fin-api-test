"""executions 域：执行记录的创建与清理。

router 只管 HTTP 语义与触发线程池；记录创建/批量创建/清理收敛到此，
消除 router 内联 ORM 与 legacy 中无人调用的 create_execution 死代码。
"""
from datetime import datetime

from sqlalchemy.orm import Session

from .. import models


def create_execution(db: Session, case_id: int, env_id: int, user_id: int,
                     trigger_type: str = "manual",
                     dataset_id: int | None = None, dataset_row: dict | None = None) -> models.ExecutionRecord:
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


# 僵尸 running 判定阈值：进程重启会杀执行线程，记录永远停在 running（无结束回调）。
# 超过该时长的 running 视为僵尸，不再据此拦截保存（误拦会让用例永远无法修改）
_RUNNING_ZOMBIE_HOURS = 6


def running_execution_of(db: Session, case_id: int) -> models.ExecutionRecord | None:
    """用例当前执行中的记录（用于保存拦截）。僵尸 running（超时未结束）返回 None。"""
    from datetime import datetime, timedelta
    cutoff = datetime.now() - timedelta(hours=_RUNNING_ZOMBIE_HOURS)
    return (db.query(models.ExecutionRecord)
            .filter(models.ExecutionRecord.case_id == case_id,
                    models.ExecutionRecord.status == "running",
                    models.ExecutionRecord.started_at >= cutoff)
            .order_by(models.ExecutionRecord.id.desc())
            .first())


def ensure_case_not_running(db: Session, case_id: int, what: str = "保存") -> None:
    """执行中的用例禁止改编排/数据集（运行线程读的是库内配置，改了会串版本）。
    命中抛 ValueError，由路由层转 409 提示。"""
    rec = running_execution_of(db, case_id)
    if rec:
        rid = f"#{rec.id}" if rec.id else ""
        raise ValueError(
            f"用例正在执行中{rid}，为避免运行与编辑串版本，{what}已被阻止；"
            f"请等执行结束，或到执行记录中手动终止后再保存")


def cleanup_old_records(db: Session, cutoff: datetime) -> int:
    """删除 started_at 早于 cutoff 的执行记录（Step/Assertion 级联），返回删除数"""
    old_execs = db.query(models.ExecutionRecord).filter(
        models.ExecutionRecord.started_at < cutoff
    ).all()
    for exec_obj in old_execs:
        db.delete(exec_obj)
    db.commit()
    return len(old_execs)

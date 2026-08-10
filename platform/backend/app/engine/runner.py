"""执行入口：从数据库加载用例与环境，驱动 DAG 执行"""
import threading
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy.orm import Session

from .. import crud, models
from ..database import SessionLocal
from .dag_executor import DagExecutor

# 全局线程池：限制并发执行数，避免资源耗尽
# max_workers=4 允许最多 4 个用例同时执行
_executor_lock = threading.Lock()
_executor: ThreadPoolExecutor | None = None


def _get_executor() -> ThreadPoolExecutor:
    """懒加载全局线程池（线程安全）"""
    global _executor
    with _executor_lock:
        if _executor is None:
            _executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="case-runner")
    return _executor


def run_execution(db: Session, case_id: int, env_id: int) -> models.ExecutionRecord:
    """同步执行用例（兼容旧调用方）"""
    case = crud.get_testcase(db, case_id)
    if not case:
        raise ValueError(f"用例不存在: {case_id}")
    env = crud.get_environment(db, env_id)
    if not env:
        raise ValueError(f"环境不存在: {env_id}")
    return DagExecutor(db, case, env).execute()


def run_execution_background(execution_id: int, case_id: int, env_id: int) -> None:
    """在后台线程中执行用例，使用独立的数据库会话。
    execution_id 对应的 ExecutionRecord 已由调用方创建（status=running）。"""
    db = SessionLocal()
    try:
        case = crud.get_testcase(db, case_id)
        if not case:
            # 用例不存在，标记执行失败
            rec = db.query(models.ExecutionRecord).filter(models.ExecutionRecord.id == execution_id).first()
            if rec:
                rec.status = "failed"
                rec.ended_at = __import__("datetime").datetime.now()
                rec.summary = {"total": 0, "passed": 0, "failed": 1, "error": f"用例不存在: {case_id}"}
                db.commit()
            return
        env = crud.get_environment(db, env_id)
        if not env:
            rec = db.query(models.ExecutionRecord).filter(models.ExecutionRecord.id == execution_id).first()
            if rec:
                rec.status = "failed"
                rec.ended_at = __import__("datetime").datetime.now()
                rec.summary = {"total": 0, "passed": 0, "failed": 1, "error": f"环境不存在: {env_id}"}
                db.commit()
            return
        # 加载已有的 record 并传入 DagExecutor，避免重复创建
        record = db.query(models.ExecutionRecord).filter(models.ExecutionRecord.id == execution_id).first()
        if not record:
            return  # record 已被删除，放弃执行
        DagExecutor(db, case, env, execution_record=record).execute()
    except Exception as e:
        # 兜底：任何异常都标记执行失败，避免 record 永远停在 running
        try:
            rec = db.query(models.ExecutionRecord).filter(models.ExecutionRecord.id == execution_id).first()
            if rec and rec.status == "running":
                rec.status = "failed"
                rec.ended_at = __import__("datetime").datetime.now()
                rec.summary = {**(rec.summary or {}), "error": str(e)}
                db.commit()
        except Exception:
            pass
    finally:
        db.close()


def submit_execution(case_id: int, env_id: int, execution_id: int) -> None:
    """提交用例执行到线程池（非阻塞）"""
    _get_executor().submit(run_execution_background, execution_id, case_id, env_id)


def run_batch_execution_background(execution_ids: list, case_ids: list, env_id: int) -> None:
    """批量执行：串行执行多个用例，一个结束再执行下一个。
    execution_ids[i] 对应 case_ids[i]，均已由调用方创建为 running 状态的 record。
    使用独立数据库会话，每个用例执行完立即提交其 record 状态。"""
    from datetime import datetime
    db = SessionLocal()
    try:
        for exec_id, case_id in zip(execution_ids, case_ids):
            try:
                case = crud.get_testcase(db, case_id)
                env = crud.get_environment(db, env_id)
                rec = db.query(models.ExecutionRecord).filter(models.ExecutionRecord.id == exec_id).first()
                if not case or not env or not rec:
                    if rec:
                        rec.status = "failed"
                        rec.ended_at = datetime.now()
                        rec.summary = {"total": 0, "passed": 0, "failed": 1, "error": "用例或环境不存在"}
                        db.commit()
                    continue
                # 复用已创建的 record，串行执行
                DagExecutor(db, case, env, execution_record=rec).execute()
                db.commit()
            except Exception as e:
                # 单个用例异常不影响后续用例执行
                try:
                    rec = db.query(models.ExecutionRecord).filter(models.ExecutionRecord.id == exec_id).first()
                    if rec and rec.status == "running":
                        rec.status = "failed"
                        rec.ended_at = datetime.now()
                        rec.summary = {"total": 0, "passed": 0, "failed": 1, "error": str(e)}
                        db.commit()
                except Exception:
                    pass
    finally:
        db.close()


def submit_batch_execution(execution_ids: list, case_ids: list, env_id: int) -> None:
    """提交批量串行执行到线程池（非阻塞）"""
    _get_executor().submit(run_batch_execution_background, execution_ids, case_ids, env_id)

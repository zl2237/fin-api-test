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

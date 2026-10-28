"""执行入口：从数据库加载用例与环境，驱动 DAG 执行"""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from .. import crud, models
from ..database import SessionLocal
from .dag_executor import DagExecutor

# 批量执行默认并发数：用户未指定时的并发上限
DEFAULT_CONCURRENCY = 4


@dataclass
class ExecutionSpec:
    """单条执行的提交规格：record 已建为 running，executor 按此执行。
    env_id 为用例绑定环境。"""

    execution_id: int
    case_id: int
    env_id: int | None = None
    # 数据集行数据 {"nodes": {...}}——各节点入参配置源（四来源参数模型）
    dataset_row: dict | None = None


def run_execution_background(execution_id: int, case_id: int, env_id: int | None,
                             dataset_row: dict | None = None) -> None:
    """在后台线程中执行用例，使用独立的数据库会话。
    execution_id 对应的 ExecutionRecord 已由调用方创建（status=running）。
    dataset_row：数据集行数据（{"nodes": {...}}，节点入参配置源）。"""
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
        # 加载已有的 record 并传入 DagExecutor，避免重复创建
        record = db.query(models.ExecutionRecord).filter(models.ExecutionRecord.id == execution_id).first()
        if not record:
            return  # record 已被删除，放弃执行
        # 普通用例：按用例绑定环境执行（launcher 已校验；此处兜底拦截脏数据）
        env = crud.get_environment(db, env_id) if env_id else None
        if not env:
            rec = db.query(models.ExecutionRecord).filter(models.ExecutionRecord.id == execution_id).first()
            if rec:
                rec.status = "failed"
                rec.ended_at = __import__("datetime").datetime.now()
                reason = f"环境不存在: {env_id}" if env_id else "用例未绑定执行环境"
                rec.summary = {**(rec.summary or {}), "total": 0, "passed": 0, "failed": 1, "error": reason}
                db.commit()
                from ..crud.executions import touch_case_last_exec
                touch_case_last_exec(db, rec)
            return
        DagExecutor(db, case, env, execution_record=record, dataset_row=dataset_row).execute()
    except Exception as e:
        # 兜底：任何异常都标记执行失败，避免 record 永远停在 running
        try:
            rec = db.query(models.ExecutionRecord).filter(models.ExecutionRecord.id == execution_id).first()
            if rec and rec.status == "running":
                rec.status = "failed"
                rec.ended_at = __import__("datetime").datetime.now()
                rec.summary = {**(rec.summary or {}), "error": str(e)}
                db.commit()
                from ..crud.executions import touch_case_last_exec
                touch_case_last_exec(db, rec)
        except Exception:
            pass
    finally:
        db.close()


def submit_batch_execution(specs: list[ExecutionSpec],
                           concurrency: int = DEFAULT_CONCURRENCY) -> None:
    """提交批量并行执行到线程池（非阻塞）。specs 为空则什么都不做。

    每条 spec 独立 submit 到批次专用线程池（max_workers=concurrency）：
    concurrency=1 时逐个串行（一个结束再下一个），>1 并行。环境为每 spec
    自带（用例严格绑定），批次可混环境；同环境并发下的登录互踢由
    EnvTokenCache 共享 token 方案消除（见 services/token_cache.py）。
    """
    if not specs:
        return
    pool = ThreadPoolExecutor(max_workers=concurrency, thread_name_prefix=f"case-c{concurrency}")
    for spec in specs:
        pool.submit(run_execution_background, spec.execution_id, spec.case_id, spec.env_id,
                    spec.dataset_row)
    pool.shutdown(wait=False)  # 提交完即关闭，已提交任务继续执行完

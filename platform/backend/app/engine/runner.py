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
    """单条执行的提交规格：record 已建为 running，executor 按此执行。"""

    execution_id: int
    case_id: int
    # 数据集域变量（点路径键）——编排按用例当前配置执行
    row_vars: dict | None = None


def run_execution_background(execution_id: int, case_id: int, env_id: int,
                             row_vars: dict | None = None) -> None:
    """在后台线程中执行用例，使用独立的数据库会话。
    execution_id 对应的 ExecutionRecord 已由调用方创建（status=running）。
    row_vars：数据集域变量（prepare_request 第 3 层解析）。"""
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
        if getattr(case, "case_type", "normal") == "suite":
            # 套件用例：分流到套件执行器（串行驱动成员链）——
            # 手动/批量/定时三入口共用本函数，套件能力由此天然全继承
            from ..services.suite_executor import run_suite
            run_suite(db, case, record)
            return
        DagExecutor(db, case, env, execution_record=record, row_vars=row_vars).execute()
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


def submit_batch_execution(specs: list[ExecutionSpec], env_id: int,
                           concurrency: int = DEFAULT_CONCURRENCY) -> None:
    """提交批量并行执行到线程池（非阻塞）。specs 为空则什么都不做。

    每条 spec 独立 submit 到批次专用线程池（max_workers=concurrency）：
    concurrency=1 时逐个串行（一个结束再下一个），>1 并行。同环境并发下的
    登录互踢由 EnvTokenCache 共享 token 方案消除（见 services/token_cache.py）。
    """
    if not specs:
        return
    pool = ThreadPoolExecutor(max_workers=concurrency, thread_name_prefix=f"case-c{concurrency}")
    for spec in specs:
        pool.submit(run_execution_background, spec.execution_id, spec.case_id, env_id,
                    spec.row_vars)
    pool.shutdown(wait=False)  # 提交完即关闭，已提交任务继续执行完

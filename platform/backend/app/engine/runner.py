"""执行入口：从数据库加载用例与环境，驱动 DAG 执行"""
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from .. import crud, models
from ..database import SessionLocal
from .dag_executor import DagExecutor

# 内部后台任务池：聚合通知等零散提交。用例执行一律走批次专用池
# （见 submit_batch_execution），互不复用避免两套池并存时并发额度互相不可见。
_executor_lock = threading.Lock()
_executor: ThreadPoolExecutor | None = None

# 批量执行默认并发数：用户未指定时的并发上限
DEFAULT_CONCURRENCY = 4


@dataclass
class ExecutionSpec:
    """单条执行的提交规格：record 已建为 running，executor 按此执行。

    这是 submit_batch_execution 的接口——替代此前的 5 个平行数组，
    调用方（execution_launcher）不再需要知道实现内部按索引 zip 的表示。
    """

    execution_id: int
    case_id: int
    # 数据驱动：行变量（列名即变量名）、列快照原值（快照保真过滤）、节点配置快照
    row_vars: dict | None = None
    row_origins: dict | None = None
    node_config_overrides: dict | None = None
    # 多行数据驱动批量时抑制逐条通知（由聚合器汇总发送）
    suppress_notify: bool = False


def _get_executor() -> ThreadPoolExecutor:
    """懒加载内部任务池（线程安全）"""
    global _executor
    with _executor_lock:
        if _executor is None:
            _executor = ThreadPoolExecutor(max_workers=DEFAULT_CONCURRENCY, thread_name_prefix="case-runner")
    return _executor


def run_execution_background(execution_id: int, case_id: int, env_id: int,
                             row_vars: dict | None = None,
                             row_origins: dict | None = None,
                             node_config_overrides: dict | None = None,
                             suppress_notify: bool = False) -> None:
    """在后台线程中执行用例，使用独立的数据库会话。
    execution_id 对应的 ExecutionRecord 已由调用方创建（status=running）。
    row_vars：数据驱动执行的数据行变量（列名即变量名，覆盖同名环境变量）。
    row_origins：列快照原值（数据集 columns 的 origin），执行时快照保真过滤（可选）。
    node_config_overrides：数据集节点配置快照 {node_id: {...}}，命中节点整块替换用例编排。
    suppress_notify：数据驱动批量执行时抑制逐条通知（由聚合器汇总发送）。"""
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
        DagExecutor(db, case, env, execution_record=record, row_vars=row_vars,
                    row_origins=row_origins,
                    node_config_overrides=node_config_overrides,
                    suppress_notify=suppress_notify).execute()
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
                    spec.row_vars, spec.row_origins,
                    spec.node_config_overrides, spec.suppress_notify)
    pool.shutdown(wait=False)  # 提交完即关闭，已提交任务继续执行完


def submit_batch_aggregate_notify(execution_ids: list, case_id: int, env_id: int,
                                  dataset_id: int, case_name: str) -> None:
    """数据驱动批量执行的聚合通知（方案定案 #7）。

    独立线程等待这批 record 全部到达终态（超时 30 分钟放弃），然后：
    - 全成功 → 不发（enable_on_success 语义）
    - 有失败 → 一条汇总（失败行号列表 + 首个失败原因）
    """
    _get_executor().submit(_wait_and_notify, list(execution_ids), case_id, env_id,
                           dataset_id, case_name)


def _wait_and_notify(execution_ids: list, case_id: int, env_id: int,
                     dataset_id: int, case_name: str) -> None:
    """聚合通知的等待侧：轮询批次到终态后调用 send_batch_notify。

    环境名/数据集名取数与门控都在 notifier（单点），本函数只剩等待 + 调用。
    """
    import time as _time
    db = SessionLocal()
    try:
        deadline = _time.time() + 30 * 60  # 超时上限：防 record 卡 running 死等
        while _time.time() < deadline:
            recs = (db.query(models.ExecutionRecord)
                    .filter(models.ExecutionRecord.id.in_(execution_ids)).all())
            if len(recs) == len(execution_ids) and all(r.status != "running" for r in recs):
                break
            db.expire_all()  # 后台线程各自独立会话，需强制刷新缓存
            _time.sleep(2)
        else:
            print(f"[聚合通知] 等待超时放弃：case#{case_id} dataset#{dataset_id}")
            return
        from ..services.notifier import send_batch_notify
        send_batch_notify(db, env_id, dataset_id, recs, case_name)
    except Exception as e:
        # 聚合通知失败不影响执行结果
        print(f"[聚合通知] 发送失败（忽略）: {e}")
    finally:
        db.close()

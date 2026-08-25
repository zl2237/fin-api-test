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


def run_execution_background(execution_id: int, case_id: int, env_id: int,
                             row_vars: dict | None = None,
                             node_config_overrides: dict | None = None,
                             suppress_notify: bool = False) -> None:
    """在后台线程中执行用例，使用独立的数据库会话。
    execution_id 对应的 ExecutionRecord 已由调用方创建（status=running）。
    row_vars：数据驱动执行的数据行变量（列名即变量名，覆盖同名环境变量）。
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
        DagExecutor(db, case, env, execution_record=record, row_vars=row_vars,
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


def submit_execution(case_id: int, env_id: int, execution_id: int, row_vars: dict | None = None,
                     node_config_overrides: dict | None = None,
                     suppress_notify: bool = False) -> None:
    """提交用例执行到线程池（非阻塞）；row_vars 为数据驱动行变量"""
    _get_executor().submit(run_execution_background, execution_id, case_id, env_id,
                           row_vars, node_config_overrides, suppress_notify)


def submit_batch_execution(execution_ids: list, case_ids: list, env_id: int,
                           rows_vars: list | None = None,
                           node_config_overrides_list: list | None = None,
                           suppress_notify_flags: list | None = None) -> None:
    """提交批量并行执行到线程池（非阻塞）。

    每个用例独立 submit，复用全局线程池（max_workers=4）天然限流：
    最多 4 个用例同时执行，其余排队。同环境并发下的登录互踢由
    EnvTokenCache 共享 token 方案消除（见 services/token_cache.py）。
    execution_ids[i] 对应 case_ids[i]，record 已由调用方创建为 running 状态。
    rows_vars[i] 为该条的数据驱动行变量（普通执行传 None）。
    node_config_overrides_list[i] 为该条使用的数据集节点配置快照（普通执行传 None）。
    suppress_notify_flags[i] 为 True 时该条不发逐条通知（数据驱动批量）。
    """
    for i, (execution_id, case_id) in enumerate(zip(execution_ids, case_ids)):
        row_vars = rows_vars[i] if rows_vars else None
        overrides = node_config_overrides_list[i] if node_config_overrides_list else None
        flag = suppress_notify_flags[i] if suppress_notify_flags else False
        _get_executor().submit(run_execution_background, execution_id, case_id, env_id,
                               row_vars, overrides, flag)


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
        env = crud.get_environment(db, env_id)
        dataset = crud.get_dataset(db, dataset_id)
        if not env or not dataset:
            return
        from ..services.notifier import build_batch_notify_content
        content = build_batch_notify_content(recs, case_name, dataset.name)
        if content is None:
            print("[聚合通知] 跳过：数据驱动批量全部成功")
            return
        notify_config = env.notify_config or {}
        webhook = notify_config.get("wecom_webhook")
        if not webhook:
            return
        if not notify_config.get("enable_on_failure", True):
            return
        from utils.wecom_util import WeComRobot
        WeComRobot(webhook).send_markdown("数据驱动批量执行通知", content)
    except Exception as e:
        # 聚合通知失败不影响执行结果
        print(f"[聚合通知] 发送失败（忽略）: {e}")
    finally:
        db.close()

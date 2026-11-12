"""方案执行器：一键执行与方案定时的唯一编排入口。

并行组合（2026-11-12 B3 删链定案，串行链/轮次/相邻传参已废止）：
成员相互独立（无依赖、无变量传递、无阻断），各自「选中数据集 × run_count」
条记录按 plan.concurrency 平铺进批次线程池。跨系统链路用融合用例编排
（跨项目接口 + 节点级环境绑定），不再由方案组织传参。

两阶段执行（run_plan 核心不变量，见 execution_launcher 模块注释的扩展约定）：
①预检全部成员——环境绑定 + plan_case_expansion 只读试算（数据集悬空、
  无数据行均在此报错），失败抛 ValueError，零记录产生；
②建记录——逐成员 build_launch_plan（成员级多选数据集 + run_count），
  一次 commit_launch 并行提交。
预检必须先于建记录：create_execution 逐条 commit，先建后检会产生半批 running。

API 平台数据集为单套语义（每个数据集恒第 1 行），成员记录数 = 选中数据集数 × run_count。
"""
from datetime import datetime

from sqlalchemy.orm import Session

from .. import crud, models
from . import dataset_service
from .execution_launcher import build_launch_plan, commit_launch

# 与 executions 路由的批量执行同上限（routers/executions.py MAX_RUN_COUNT）
MAX_RUN_COUNT = 9999


def validate_plan_items(db, items: list) -> None:
    """保存时校验方案成员（全量校验，不落库；items 为 PlanItemIn 或同形对象）。

    - case 必须存在（可跨项目）
    - dataset_ids 非空时：各数据集存在且属于该成员用例（复用执行面板换绑同口径）
    - run_count 1~9999
    """
    for i, item in enumerate(items, start=1):
        case = crud.get_testcase(db, item.case_id)
        if not case:
            raise ValueError(f"第 {i} 个成员的用例不存在（id={item.case_id}）")
        for ds_id in (item.dataset_ids or []):
            dataset_service.validate_binding(db, case, ds_id)
        if not 1 <= item.run_count <= MAX_RUN_COUNT:
            raise ValueError(f"第 {i} 个成员「{case.name}」执行次数须在 1~{MAX_RUN_COUNT} 之间")


def _validate_item_launchable(db: Session, item: models.ExecutionPlanItem, case) -> None:
    """执行预检（无副作用）：环境绑定 + 数据集展开试算，口径与真实执行 100% 一致。"""
    if not case.env_id:
        raise ValueError(f"成员「{case.name}」未绑定执行环境，请先在用例编辑中选择")
    if not crud.get_environment(db, case.env_id):
        raise ValueError(f"成员「{case.name}」绑定的环境已不存在（id={case.env_id}），请重新绑定")
    dataset_service.plan_case_expansion(db, case, dataset_ids=item.dataset_ids)


def run_plan(db: Session, plan: models.ExecutionPlan, user_id: int, *,
             trigger_type: str = "plan") -> list[models.ExecutionRecord]:
    """执行方案：预检 → 建记录 → 并行提交（concurrency=方案配置）。

    trigger_type：'plan'（一键）/ 'plan_schedule'（方案定时）。
    任何成员不可执行抛 ValueError（调用方转 400 或定时跳过本轮），零记录产生。
    返回本次产生的全部执行记录（各成员 选中数据集数 × run_count）。
    """
    items = sorted(plan.items, key=lambda x: x.sort_order)
    if not items:
        raise ValueError("方案未配置成员，请先在方案编辑中添加用例")

    # 阶段 1：全量预检（只读）——任何失败在产生记录前抛出
    for item in items:
        case = crud.get_testcase(db, item.case_id)
        if not case:
            raise ValueError(f"成员用例已不存在（id={item.case_id}），请移除后重试")
        _validate_item_launchable(db, item, case)

    # 阶段 2：逐成员发射（成员级多选数据集 + 次数）
    plans = []
    for item in items:
        case = crud.get_testcase(db, item.case_id)
        plans.append((case, build_launch_plan(
            db, case, user_id,
            trigger_type=trigger_type,
            dataset_ids=item.dataset_ids,
            run_count=item.run_count,
            plan_id=plan.id)))

    commit_launch([p for _, p in plans], concurrency=plan.concurrency)

    plan.last_run_at = datetime.now()
    db.commit()

    records = [r for _, p in plans for r in p.records]
    _spawn_plan_notify_watcher(plan.id, [r.id for r in records])
    return records


# ============ 方案聚合通知（方案成员不逐条通知，全量结束后一条汇总） ============

def _spawn_plan_notify_watcher(plan_id: int, record_ids: list) -> None:
    """批次线程池无统一收尾点，起后台线程轮询至全部终态。

    5s 粒度轮询（通知延迟可接受）；24h 上限后仍发（带未结束计数）。
    """
    import threading
    from ..database import SessionLocal

    threading.Thread(target=_watch_and_notify, args=(SessionLocal, plan_id, record_ids),
                     name=f"plan-notify-{plan_id}", daemon=True).start()


def _watch_and_notify(SessionLocal, plan_id: int, record_ids: list) -> None:
    import time
    from .notifier import send_plan_notify

    def _all_terminal(db) -> bool:
        rows = (db.query(models.ExecutionRecord.status)
                .filter(models.ExecutionRecord.id.in_(record_ids)).all())
        return bool(rows) and all(s in ("success", "failed", "terminated") for (s,) in rows)

    for _ in range(12 * 60 * 24):  # 24h @ 5s
        time.sleep(5)
        db = SessionLocal()
        try:
            if _all_terminal(db):
                send_plan_notify(db, plan_id, record_ids)
                return
        finally:
            db.close()
    db = SessionLocal()  # 超时兜底：仍发聚合（含未结束计数）
    try:
        send_plan_notify(db, plan_id, record_ids)
    finally:
        db.close()

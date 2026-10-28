"""方案执行器：一键执行与方案定时的唯一编排入口。

两模式（2026-10-28 套件收口 + 链式定向传参/批量策略正交定案）：
- combo 并行组合（默认）：成员相互独立（无依赖、无变量传递、无阻断），
  各自 run_count 次按 plan.concurrency 平铺进批次线程池。
- chain 串行链：链 = 依赖与传参链路的组织方式，批量策略叠加其上——
  整链 plan.rounds 轮，轮内成员按 sort_order 串行 + 相邻定向传参
  （成员 pass_vars 名单快照注入下一棒 __prev__ 命名空间）+ 上游失败
  阻断本轮下游；轮间按 plan.concurrency 并行（轮与轮互不影响）。

两阶段执行（run_plan 核心不变量，见 execution_launcher 模块注释的扩展约定）：
①预检全部成员——环境绑定 + plan_case_expansion 只读试算（数据集悬空、
  无数据行均在此报错），失败抛 ValueError，零记录产生；
②建记录——combo 逐成员 build_launch_plan（成员级换绑 + run_count）；
  chain 按「轮主序」（第 1 轮全员、第 2 轮全员…）预建 rounds×成员 记录，
  第 r 轮各成员取自身数据集第 r 套值（不足沿用最后一套）。
预检必须先于建记录：create_execution 逐条 commit，先建后检会产生半批 running。
combo：一次 commit_launch 并行提交；chain：后台线程按轮驱动（_submit_chain）。

chain 记录全量预建（running）：执行列表/方案过滤/终止级联与 combo 完全同构；
未执行的记录由链驱动置 failed 并注明「阻断」原因，现场可查。

API 平台数据集为单套语义（每个数据集恒第 1 行），多轮复用同一套值。
"""
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from .. import crud, models
from . import dataset_service
from .execution_launcher import build_launch_plan, commit_launch

# 与 executions 路由的批量执行同上限（routers/executions.py MAX_RUN_COUNT）
MAX_RUN_COUNT = 9999


def validate_plan_items(db, items: list) -> None:
    """保存时校验方案成员（全量校验，不落库；items 为 PlanItemIn 或同形对象）。

    - case 必须存在（可跨项目）
    - dataset_id 非空时：数据集存在且属于该成员用例（复用执行面板换绑同口径）
    - run_count 1~9999（combo 生效；chain 整链轮数在方案级 rounds，此项忽略）
    """
    for i, item in enumerate(items, start=1):
        case = crud.get_testcase(db, item.case_id)
        if not case:
            raise ValueError(f"第 {i} 个成员的用例不存在（id={item.case_id}）")
        if item.dataset_id is not None:
            dataset_service.validate_binding(db, case, item.dataset_id)
        if not 1 <= item.run_count <= MAX_RUN_COUNT:
            raise ValueError(f"第 {i} 个成员「{case.name}」执行次数须在 1~{MAX_RUN_COUNT} 之间")


def _validate_item_launchable(db: Session, item: models.ExecutionPlanItem, case) -> None:
    """执行预检（无副作用）：环境绑定 + 数据集展开试算，口径与真实执行 100% 一致。"""
    if not case.env_id:
        raise ValueError(f"成员「{case.name}」未绑定执行环境，请先在用例编辑中选择")
    if not crud.get_environment(db, case.env_id):
        raise ValueError(f"成员「{case.name}」绑定的环境已不存在（id={case.env_id}），请重新绑定")
    dataset_service.plan_case_expansion(db, case, dataset_id=item.dataset_id)


def run_plan(db: Session, plan: models.ExecutionPlan, user_id: int, *,
             trigger_type: str = "plan") -> list[models.ExecutionRecord]:
    """执行方案：预检 → 建记录 → 提交（combo 并行 / chain 按轮并行）。

    trigger_type：'plan'（一键）/ 'plan_schedule'（方案定时）。
    任何成员不可执行抛 ValueError（调用方转 400 或定时跳过本轮），零记录产生。
    返回本次产生的全部执行记录（combo 含 run_count 重复；chain 为 轮数×成员）。
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

    if (plan.mode or "combo") == "chain":
        return _launch_chain(db, plan, items, user_id, trigger_type=trigger_type)

    # 阶段 2（combo）：逐成员发射（成员级换绑 + 次数）
    plans = []
    for item in items:
        case = crud.get_testcase(db, item.case_id)
        plans.append((case, build_launch_plan(
            db, case, user_id,
            trigger_type=trigger_type,
            dataset_id=item.dataset_id,
            run_count=item.run_count,
            plan_id=plan.id)))

    commit_launch([p for _, p in plans], concurrency=plan.concurrency)

    plan.last_run_at = datetime.now()
    db.commit()

    return [r for _, p in plans for r in p.records]


# ============ chain 串行链（组织依赖与传参；批量策略=轮数×轮间并发） ============

def _launch_chain(db: Session, plan: models.ExecutionPlan, items: list,
                  user_id: int, *, trigger_type: str) -> list[models.ExecutionRecord]:
    """链模式建记录 + 后台驱动：轮主序预建 rounds×成员，第 r 轮取各成员第 r 套值。"""
    from ..crud import executions as exec_domain

    rounds = plan.rounds or 1
    if rounds * len(items) > MAX_RUN_COUNT:
        raise ValueError(f"整链轮数×成员数超过 {MAX_RUN_COUNT}（当前 {rounds}×{len(items)}），请调低轮数")

    members: list[dict] = []
    records: list[models.ExecutionRecord] = []
    for item in items:
        case = crud.get_testcase(db, item.case_id)
        if not case:  # run_plan 预检已挡，此处窄化给 mypy（口径同上）
            raise ValueError(f"成员用例已不存在（id={item.case_id}），请移除后重试")
        expansion = dataset_service.plan_case_expansion(db, case, dataset_id=item.dataset_id)
        members.append({
            "case_id": case.id,
            "case_name": case.name,
            "env_id": case.env_id,
            "pass_vars": item.pass_vars or [],
            # 数据集行（完整行：建记录用 dataset_id+row；驱动取 row["data"]）
            "expansion": expansion,
            "record_ids": [],
        })
    # 轮主序建记录：执行列表按「第 1 轮全员 → 第 2 轮全员」呈现
    for r in range(rounds):
        for m in members:
            it = m["expansion"][min(r, len(m["expansion"]) - 1)]
            rec = exec_domain.create_execution(
                db, case_id=m["case_id"], env_id=m["env_id"], user_id=user_id,
                trigger_type=trigger_type, dataset_id=it["dataset_id"],
                dataset_row=it["row"], plan_id=plan.id)
            crud.fill_audit_names(db, rec)
            crud.fill_exec_names(db, rec)
            m["record_ids"].append(rec.id)
            records.append(rec)

    _submit_chain(plan, rounds, members)

    plan.last_run_at = datetime.now()
    db.commit()
    return records


def _snapshot_vars(pass_vars: list[str], registry) -> dict[str, Any]:
    """按成员 pass_vars 名单从节点命名空间注册表快照（名单外变量不外泄）。

    名单是变量名（无节点维度）：跨全部命名空间按名收集，同名后写覆盖；
    注入下一棒 __prev__ 伪命名空间（相邻定向传参，下一棒 {{__prev__.变量名}} 引用）。
    """
    flat: dict[str, Any] = {}
    for _, vars_ in registry.to_dict().items():
        for k, v in vars_.items():
            flat[k] = v
    return {k: flat[k] for k in (pass_vars or []) if k in flat}


def _submit_chain(plan: models.ExecutionPlan, rounds: int, members: list[dict]) -> None:
    """链模式提交：后台线程按轮驱动（非阻塞，调用方为 API 请求线程）。

    members 各项补齐驱动所需纯数据（rows=数据集行 data、record_ids 按轮序），
    不携带 ORM 对象（跨线程/跨会话安全）。
    """
    import threading
    from ..database import SessionLocal

    plan_id = plan.id
    # 显式类型局部变量：payload 字典值类型会被推断为 object，链驱动侧还要迭代它
    members_payload: list[dict] = [{
        "case_id": m["case_id"],
        "env_id": m["env_id"],
        "pass_vars": m["pass_vars"],
        "rows": [(it["row"] or {}).get("data") for it in m["expansion"]],
        "record_ids": m["record_ids"],
    } for m in members]
    payload = {
        "plan_id": plan_id,
        "rounds": rounds,
        "concurrency": max(1, plan.concurrency or 1),
        "members": members_payload,
    }
    all_record_ids = [rid for m in members_payload for rid in m["record_ids"]]

    def _bg():
        try:
            _run_chain(SessionLocal, payload)
        except Exception as e:  # 兜底：链驱动异常不应留半批 running
            print(f"[串行链 #{plan_id}] 驱动异常: {e}")
            try:
                db = SessionLocal()
                try:
                    for rid in all_record_ids:
                        rec = db.query(models.ExecutionRecord).get(rid)
                        if rec and rec.status == "running":
                            rec.status = "failed"
                            rec.ended_at = datetime.now()
                            rec.summary = {**(rec.summary or {}), "error": f"串行链驱动异常: {e}"}
                    db.commit()
                finally:
                    db.close()
            except Exception:
                pass

    threading.Thread(target=_bg, name=f"plan-chain-{plan_id}", daemon=True).start()


def _fail_record(db: Session, record, reason: str) -> None:
    record.status = "failed"
    record.ended_at = datetime.now()
    record.summary = {**(record.summary or {}), "error": reason}
    db.commit()
    from ..crud.executions import touch_case_last_exec
    touch_case_last_exec(db, record)


def _run_round(SessionLocal, members: list[dict], r: int) -> None:
    """驱动一轮（独立线程/独立会话）：成员按序串行 + 相邻定向传参 + 轮内阻断。

    - 传参：上一棒成功后按其 pass_vars 快照注入下一棒 __prev__；
      名单为空=快照空 dict（下一棒照常执行、无注入），失败=下一棒阻断
    - 阻断：上游失败/被终止 → 本轮下游预建记录置 failed 并注明原因
      （其他轮不受影响）；成员用例或环境被删同理
    - 手动终止：terminate 已把同方案 running 记录级联置 terminated，
      驱动逐成员检查记录状态，非 running 一律跳过执行（终态保留）
    """
    from ..engine.dag_executor import DagExecutor
    from ..crud.executions import touch_case_last_exec

    db = SessionLocal()
    try:
        prev: dict[str, Any] | None = None  # 上一棒成功快照（None=失败/未执行）
        has_upstream = False                 # 首棒无注入也不阻断
        for m in members:
            rec = db.query(models.ExecutionRecord).get(m["record_ids"][r])
            if rec is None or rec.status != "running":
                prev = None
                has_upstream = True
                continue
            if has_upstream and prev is None:
                _fail_record(db, rec, "上游成员未成功执行，本轮阻断")
                continue
            case = crud.get_testcase(db, m["case_id"])
            env = crud.get_environment(db, m["env_id"]) if m["env_id"] else None
            if case is None or env is None or not m["rows"]:
                _fail_record(db, rec, "成员用例或环境已不存在（可能被删除），本轮阻断")
                prev = None
                has_upstream = True
                continue
            executor = None
            try:
                executor = DagExecutor(
                    db, case, env, execution_record=rec,
                    dataset_row=m["rows"][min(r, len(m["rows"]) - 1)],
                    prev_vars=prev)
                executor.execute()
                db.refresh(rec)
            except Exception as e:  # 单成员异常视作该成员失败，本轮阻断下游
                rec.status = "failed"
                rec.ended_at = datetime.now()
                rec.summary = {**(rec.summary or {}), "error": str(e)}
                db.commit()
                touch_case_last_exec(db, rec)
            prev = (_snapshot_vars(m["pass_vars"], executor.context.registry)
                    if rec.status == "success" and executor else None)
            has_upstream = True
    finally:
        db.close()


def _run_chain(SessionLocal, payload: dict) -> None:
    """链总驱动：rounds 轮提交线程池（max_workers=concurrency，轮间并行、轮内串行）。"""
    from concurrent.futures import ThreadPoolExecutor

    members, rounds = payload["members"], payload["rounds"]
    if rounds <= 1 or payload["concurrency"] <= 1:
        for r in range(rounds):
            _run_round(SessionLocal, members, r)
        return
    with ThreadPoolExecutor(max_workers=payload["concurrency"],
                            thread_name_prefix=f"chain-{payload.get('plan_id', 'p')}") as pool:
        futures = [pool.submit(_run_round, SessionLocal, members, r) for r in range(rounds)]
        for f in futures:
            f.result()  # 逐轮收集异常（_run_round 内部已兜底，这里再抛即触发上层兜底）

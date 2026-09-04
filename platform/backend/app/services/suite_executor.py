"""套件执行器：跨系统用例链的串行驱动（case_type=suite 的执行实现）。

接入点：run_execution_background 检测 case_type=suite 时分流至此，套件主
ExecutionRecord 已由 execution_launcher 创建（status=running），本模块在
同一后台线程内串行驱动成员——上游结束才能快照白名单注入下游，天然串行。

语义（设计定案）：
- 成员按 sort_order 串行执行，逐成员独立环境（跨系统各用各的）
- 共享变量白名单（suite.shared_vars）：上游成员每行执行结束时从变量池
  按名单快照；下游成员执行时以最高优先级注入（ExecutionContext.suite_vars）
- 逐行配对：上游 N 行 → 下游第 i 次执行注入第 i 行快照；下游行数超出时
  沿用最后一个有效快照
- 阻断：上游某行失败 → 该行快照置 None → 下游对应行 blocked（不建执行
  记录），其余行照常；上游整体全失败/自身异常 → 后续成员整体 blocked
- 成员执行 suppress_notify=True，套件结束发一条汇总通知
- 套件主记录 summary：{suite: true, total/passed/failed/blocked, members:
  [{case_id, case_name, project_name, status, rows: [{execution_id, status}]}],
  shared_vars: 最终快照}
"""
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from .. import crud, models
from ..crud import executions as exec_domain
from ..engine.dag_executor import DagExecutor
from . import dataset_service
from .notifier import send_suite_notify


def _snapshot_vars(whitelist: list[str], extracted: dict[str, Any]) -> dict[str, Any]:
    """按白名单从变量池快照（名单外的变量不外泄，只保留名单内且在池中的）"""
    keys = whitelist or []
    return {k: extracted[k] for k in keys if k in (extracted or {})}


def run_suite(db: Session, suite_case: models.TestCase, record: models.ExecutionRecord) -> None:
    """串行执行套件链，回填主记录状态与 summary。调用方保证在后台线程且 record 已落库。"""
    record.started_at = datetime.now()
    members = (db.query(models.SuiteMember)
               .filter(models.SuiteMember.suite_case_id == suite_case.id)
               .order_by(models.SuiteMember.sort_order, models.SuiteMember.id)
               .all())
    whitelist = suite_case.shared_vars or []

    total = passed = failed = blocked = 0
    member_reports: list[dict] = []
    # 上游行的白名单快照序列：元素 None 表示该行失败（下游对应行阻断）
    snapshots: list[dict | None] = []
    chain_broken = False  # 上游整体失败/异常 → 后续成员整体阻断

    if not members:
        record.status = "failed"
        record.ended_at = datetime.now()
        record.summary = {"total": 0, "passed": 0, "failed": 1, "blocked": 0,
                          "error": "套件未配置成员，请先在套件编排中添加成员用例"}
        return

    # 主记录环境对齐首成员环境（报告/通知取数更有意义；路由传入的 env 对套件无语义）
    first_member_case = crud.get_testcase(db, members[0].member_case_id)
    if first_member_case:
        first_env = crud.get_environment(db, members[0].env_id)
        if first_env:
            record.env_id = first_env.id

    for member in members:
        member_report: dict[str, Any] = {"sort_order": member.sort_order, "rows": []}
        member_case = crud.get_testcase(db, member.member_case_id)
        member_env = crud.get_environment(db, member.env_id)

        if member_case is None or member_env is None:
            member_report.update(case_id=member.member_case_id,
                                 case_name=f"# {member.member_case_id}",
                                 status="failed",
                                 error="成员用例或其绑定环境不存在（可能已被删除）")
            member_reports.append(member_report)
            total += 1
            failed += 1
            chain_broken = True
            continue
        member_report.update(case_id=member_case.id, case_name=member_case.name)

        if getattr(member_case, "case_type", "normal") == "suite":
            member_report.update(status="failed", error="套件不能嵌套套件（成员必须为普通用例）")
            member_reports.append(member_report)
            total += 1
            failed += 1
            chain_broken = True
            continue

        if chain_broken:
            member_report.update(status="blocked",
                                 error="上游成员失败，整链阻断")
            member_reports.append(member_report)
            total += 1
            blocked += 1
            continue

        try:
            plan_items = dataset_service.plan_case_expansion(db, member_case)
        except ValueError as e:
            member_report.update(status="failed", error=str(e))
            member_reports.append(member_report)
            total += 1
            failed += 1
            chain_broken = True
            continue

        row_snapshots: list[dict | None] = []
        for i, item in enumerate(plan_items):
            row_report: dict[str, Any] = {"row_index": (item["row"] or {}).get("row_index")}
            # 逐行配对：第 i 行注入上游第 i 行快照（None=该行失败→阻断本行）；
            # 下游行数超出上游时沿用最后一个有效快照（上游整体无有效快照才整行阻断）
            inject: dict[str, Any] | None = None
            if snapshots:
                if i < len(snapshots):
                    inject = snapshots[i]
                else:
                    valid = [s for s in snapshots if s is not None]
                    inject = valid[-1] if valid else None
                if inject is None:
                    row_report.update(status="blocked", reason="上游对应行失败")
                    member_report["rows"].append(row_report)
                    row_snapshots.append(None)
                    continue
            row_vars = (item["row"] or {}).get("data")
            row_record = exec_domain.create_execution(
                db, case_id=member_case.id, env_id=member_env.id,
                user_id=record.created_by, trigger_type=record.trigger_type,
                dataset_id=item["dataset_id"], dataset_row=item["row"])
            row_record.suite_execution_id = record.id
            db.commit()
            try:
                executor = DagExecutor(
                    db, member_case, member_env, execution_record=row_record,
                    row_vars=row_vars, row_origins=item.get("origins"),
                    node_config_overrides=item.get("overrides"),
                    suite_vars=inject or None, suppress_notify=True)
                executor.execute()
                # 重新attach：DagExecutor.execute 内部 commit 后 record 对象仍可用
                db.refresh(row_record)
            except Exception as e:  # 兜底：成员执行异常视作该行失败，链不断（其余行继续）
                executor = None
                row_record.status = "failed"
                row_record.ended_at = datetime.now()
                row_record.summary = {**(row_record.summary or {}), "error": str(e)}
                db.commit()
            ok = row_record.status == "success"
            row_report.update(execution_id=row_record.id,
                              status="success" if ok else "failed")
            if not ok:
                # 行失败原因回填（登录失败等执行级错误在 row_record.summary.error），
                # 套件报告页行内直接可见，无需点进成员报告排查
                err = (row_record.summary or {}).get("error")
                if err:
                    row_report["reason"] = str(err)[:200]
            member_report["rows"].append(row_report)
            row_snapshots.append(
                _snapshot_vars(whitelist, executor.context.extracted)
                if ok and executor else None)

        # 成员整体状态：所有行成功 → success；全部被阻断 → blocked；否则 failed
        statuses = [r["status"] for r in member_report["rows"]]
        if statuses and all(s == "success" for s in statuses):
            member_report["status"] = "success"
            passed += 1
        elif statuses and all(s == "blocked" for s in statuses):
            member_report["status"] = "blocked"
            blocked += 1
        else:
            member_report["status"] = "failed"
            failed += 1
            # 有效快照全无（全部行失败/阻断）→ 下游成员整体阻断
            if not any(s is not None for s in row_snapshots):
                chain_broken = True
        member_reports.append(member_report)
        if any(s is not None for s in row_snapshots):
            snapshots = row_snapshots
        total += 1

    record.status = "failed" if (failed or blocked) else "success"
    record.ended_at = datetime.now()
    final_shared = next((s for s in reversed(snapshots) if s is not None), None)
    record.summary = {
        "suite": True,
        "total": total, "passed": passed, "failed": failed, "blocked": blocked,
        "members": member_reports,
        "shared_vars": final_shared or {},
    }
    db.commit()

    # 套件级一条通知（成员逐条通知已抑制）；环境取主记录 env（已对齐首成员）
    try:
        env = crud.get_environment(db, record.env_id)
        if env:
            send_suite_notify(db, env, suite_case, record)
    except Exception as e:
        print(f"[套件通知] 发送失败（忽略）: {e}")

"""执行编排（execution launcher）：单套值展开 → 建记录 → 批量提交的唯一入口。

- build_launch_plan：一个用例的一次发射计划（可与其他 plan 合并后一次 commit）
- commit_launch：把若干 plan 平铺为一份 specs 提交线程池

调用方只剩两类：executions 路由（手动/批量，concurrency 可配）与 scheduler
（定时触发，默认并发）。新触发来源只需调用这两个函数即可接入全部语义。
"""
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from .. import crud
from ..crud import executions as exec_domain
from ..engine.runner import (
    DEFAULT_CONCURRENCY,
    ExecutionSpec,
    submit_batch_execution,
)
from . import dataset_service


@dataclass
class LaunchPlan:
    """一个用例（× run_count 轮）的发射计划。commit 前可与其他 plan 合并。"""

    records: list = field(default_factory=list)
    specs: list[ExecutionSpec] = field(default_factory=list)


def build_launch_plan(db: Session, case, env_id: int, user_id: int, *,
                      trigger_type: str = "manual",
                      dataset_id: int | None = None,
                      run_count: int = 1) -> LaunchPlan:
    """规划一个用例的一次发射：展开 → 建记录 → 组装 specs。

    数据集不可执行（无数据/不存在）抛 ValueError，由调用方决定 4xx 或跳过。
    单套语义：绑定数据集恒展开 1 条（该数据集唯一一套数据）；
    run_count>1 时复用一次规划重复提交（run_count 次执行）。
    套件：本体无变量池（成员各自绑定数据集与环境），单条直发不校验绑定。"""
    if getattr(case, "case_type", "normal") == "suite":
        plan_items = [{"dataset_id": None, "row": None}]
    else:
        plan_items = dataset_service.plan_case_expansion(db, case, dataset_id=dataset_id)

    launch = LaunchPlan()
    for _ in range(run_count):
        for item in plan_items:
            record = exec_domain.create_execution(db, case_id=case.id, env_id=env_id,
                                                  user_id=user_id, trigger_type=trigger_type,
                                                  dataset_id=item["dataset_id"],
                                                  dataset_row=item["row"])
            launch.records.append(record)
            launch.specs.append(ExecutionSpec(
                execution_id=record.id,
                case_id=case.id,
                row_vars=(item["row"] or {}).get("data"),
            ))

    for record in launch.records:
        crud.fill_audit_names(db, record)
        crud.fill_exec_names(db, record)
    return launch


def commit_launch(plans: list[LaunchPlan], env_id: int,
                  concurrency: int = DEFAULT_CONCURRENCY) -> None:
    """提交若干 plan（非阻塞）：全部 specs 平铺进一个批次专用线程池，
    concurrency=1 串行、>1 并行。"""
    specs = [spec for plan in plans for spec in plan.specs]
    if specs:
        submit_batch_execution(specs, env_id, concurrency=concurrency)

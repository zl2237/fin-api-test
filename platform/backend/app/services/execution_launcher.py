"""执行编排（execution launcher）：数据驱动展开 → 建记录 → 批量提交 → 聚合通知的唯一入口。

此前这段编排存在 3 份平行实现（execute 路由 / batch_execute 路由 / 定时任务），
聚合判定与平行数组表示各自拷贝。现在收敛为一个深模块：

- build_launch_plan：一个用例的一次发射计划（可与其他 plan 合并后一次 commit）
- commit_launch：把若干 plan 平铺为一份 specs 提交线程池，并注册聚合通知

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
    submit_batch_aggregate_notify,
    submit_batch_execution,
)
from . import dataset_service


@dataclass
class AggregateGroup:
    """一次数据驱动多行展开的聚合通知组：全部终态后只发一条汇总。"""

    execution_ids: list[int]
    case_id: int
    dataset_id: int
    case_name: str


@dataclass
class LaunchPlan:
    """一个用例（× run_count 轮）的发射计划。commit 前可与其他 plan 合并。"""

    records: list = field(default_factory=list)
    specs: list[ExecutionSpec] = field(default_factory=list)
    aggregate_groups: list[AggregateGroup] = field(default_factory=list)


def build_launch_plan(db: Session, case, env_id: int, user_id: int, *,
                      trigger_type: str = "manual",
                      dataset_id: int | None = None,
                      row_ids: list | None = None,
                      run_count: int = 1) -> LaunchPlan:
    """规划一个用例的一次发射：展开 → 建记录 → 组装 specs。

    数据集不可执行（0 行/过期/不存在）抛 ValueError，由调用方决定 4xx 或跳过。
    多行展开时整组抑制逐条通知并登记一个 AggregateGroup。
    run_count>1 时同轮次展开结果一致，复用一次规划重复提交。
    """
    plan_items = dataset_service.plan_case_expansion(db, case, dataset_id=dataset_id,
                                                     row_ids=row_ids)
    aggregate = len(plan_items) > 1 and plan_items[0]["dataset_id"] is not None

    launch = LaunchPlan()
    group_ids: list[int] = []
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
                row_origins=item.get("origins"),
                node_config_overrides=item["overrides"],
                suppress_notify=aggregate,
            ))
            group_ids.append(record.id)
    if aggregate:
        launch.aggregate_groups.append(AggregateGroup(
            execution_ids=group_ids, case_id=case.id,
            dataset_id=plan_items[0]["dataset_id"], case_name=case.name,
        ))

    for record in launch.records:
        crud.fill_audit_names(db, record)
        crud.fill_exec_names(db, record)
    return launch


def commit_launch(plans: list[LaunchPlan], env_id: int,
                  concurrency: int = DEFAULT_CONCURRENCY) -> None:
    """提交若干 plan（非阻塞）：全部 specs 平铺进一个批次专用线程池，
    concurrency=1 串行、>1 并行；随后为每个聚合组注册终态汇总通知。"""
    specs = [spec for plan in plans for spec in plan.specs]
    if specs:
        submit_batch_execution(specs, env_id, concurrency=concurrency)
    for plan in plans:
        for group in plan.aggregate_groups:
            submit_batch_aggregate_notify(group.execution_ids, group.case_id, env_id,
                                          group.dataset_id, group.case_name)

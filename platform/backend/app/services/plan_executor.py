"""方案执行器：一键执行与方案定时的唯一编排入口（与 suite_executor 平级）。

与套件的语义差异：成员相互独立（无依赖链、无变量传递、无阻断），
按 plan.concurrency 平铺进批次线程池；任一成员失败不影响其他成员。

两阶段执行（run_plan 核心不变量，见 execution_launcher 模块注释的扩展约定）：
①预检全部成员——环境绑定 + plan_case_expansion 只读试算（数据集悬空、
  无数据行均在此报错），失败抛 ValueError，零记录产生；
②逐成员 build_launch_plan（带成员级数据集换绑与 run_count）→ 一次 commit_launch。
预检必须先于 build：create_execution 逐条 commit，先建后检会产生半批 running 记录。

API 平台数据集为单套语义（每个数据集恒第 1 行），成员无行选择参数。
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

    - case 必须存在（普通用例或套件均可，可跨项目）
    - dataset_id 非空时：数据集存在且属于该成员用例（复用执行面板换绑同口径）
    - 套件成员禁配数据集换绑（dataset_id 必须为 None）
    - run_count 1~9999
    """
    for i, item in enumerate(items, start=1):
        case = crud.get_testcase(db, item.case_id)
        if not case:
            raise ValueError(f"第 {i} 个成员的用例不存在（id={item.case_id}）")
        if item.dataset_id is not None:
            if case.case_type == "suite":
                raise ValueError(f"第 {i} 个成员「{case.name}」是套件：套件成员各自绑定数据集，不能换绑")
            dataset_service.validate_binding(db, case, item.dataset_id)
        if not 1 <= item.run_count <= MAX_RUN_COUNT:
            raise ValueError(f"第 {i} 个成员「{case.name}」执行次数须在 1~{MAX_RUN_COUNT} 之间")


def _validate_item_launchable(db: Session, item: models.ExecutionPlanItem, case) -> None:
    """执行预检（无副作用）：环境绑定 + 数据集展开试算，口径与真实执行 100% 一致。

    套件成员只校验 case 存在（build_launch_plan 套件分支单条直发不校验绑定）。
    """
    if case.case_type == "suite":
        return
    if not case.env_id:
        raise ValueError(f"成员「{case.name}」未绑定执行环境，请先在用例编辑中选择")
    if not crud.get_environment(db, case.env_id):
        raise ValueError(f"成员「{case.name}」绑定的环境已不存在（id={case.env_id}），请重新绑定")
    dataset_service.plan_case_expansion(db, case, dataset_id=item.dataset_id)


def run_plan(db: Session, plan: models.ExecutionPlan, user_id: int, *,
             trigger_type: str = "plan") -> list[models.ExecutionRecord]:
    """执行方案：预检 → 逐成员发射 → 一次提交。

    trigger_type：'plan'（一键）/ 'plan_schedule'（方案定时）。
    任何成员不可执行抛 ValueError（调用方转 400 或定时跳过本轮），零记录产生。
    返回本次产生的全部执行记录（平铺，含 run_count 重复）。
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

    # 阶段 2：逐成员发射（成员级换绑 + 次数），一次合并提交
    plans = []
    for item in items:
        case = crud.get_testcase(db, item.case_id)
        plans.append(build_launch_plan(
            db, case, user_id,
            trigger_type=trigger_type,
            dataset_id=item.dataset_id,
            run_count=item.run_count,
            plan_id=plan.id))
    commit_launch(plans, concurrency=plan.concurrency)

    plan.last_run_at = datetime.now()
    db.commit()

    return [r for p in plans for r in p.records]

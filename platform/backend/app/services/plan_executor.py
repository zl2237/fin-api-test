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
from .. import crud
from . import dataset_service

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

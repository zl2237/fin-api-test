"""报告虚拟上下文：从报告步骤拼装重放/续跑共用的 ${} 统一池。

三个消费方共用一份拼装口径（断点续跑设计定稿）：
- 重放：断言求值 / 提取 SQL 的 ${} 引用上下文（before_node 截断到被重放节点之前）
- 续跑：DagExecutor 的 context_seed（全部成功步骤，首个未成功节点之前天然如此）

口径与 ExecutionContext 一致：数据集 row_vars 打底，运行时提取覆盖同名；
同 node 多条成功（重跑替换）按步骤顺序后者覆盖——即「最新成功步骤」生效。
失败步骤的提取值不进池：该节点重跑时会重新提取，旧值无意义。
"""
from typing import Any


def build_report_context(steps: list[Any], row_vars: dict | None = None,
                         before_node: str | None = None) -> dict[str, Any]:
    """拼装报告虚拟上下文（${} 统一池）。

    :param steps: 按执行顺序（id 升序）排列的步骤记录，
                  取 .node_id / .status / .extracted_vars 三个属性
    :param row_vars: 当前数据集单套数据（重放/续跑时取当前值，非执行时快照）
    :param before_node: 重放场景传被重放节点 id——只拼步骤顺序在该节点之前的
                        成功步骤；None 或不存在于步骤中则拼全部
    :return: extracted 池 dict（ExpressionEngine({"extracted": ...}) 直接可用）
    """
    extracted: dict[str, Any] = dict(row_vars or {})
    for step in steps:
        if before_node is not None and getattr(step, "node_id", None) == before_node:
            break
        if getattr(step, "status", None) != "success":
            continue
        vars_ = getattr(step, "extracted_vars", None)
        if isinstance(vars_, dict):
            extracted.update(vars_)
    return extracted

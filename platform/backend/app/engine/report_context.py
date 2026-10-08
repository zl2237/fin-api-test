"""报告虚拟上下文 v2：从报告步骤拼装节点命名空间 seed（重放/续跑共用口径）。

消费方：
- 重放：前缀成功步骤的提取值按 node_id 分组注入注册表（断言/提取 {{}} 引用）
- 续跑：DagExecutor 的 context_seed（ExecutionContext.resume_seed 嵌套注入）

口径：同 node 多条成功（重跑替换）按步骤顺序后者覆盖——「最新成功步骤」生效；
失败步骤的提取值不进 seed（该节点重跑时会重新提取）。
数据集行为 per-node 入参配置（非键值），不在此打底（执行侧 dataset_vars 消费）。
"""
from typing import Any


def build_report_context(steps: list[Any], before_node: str | None = None) -> dict[str, dict[str, Any]]:
    """拼装报告虚拟上下文（节点命名空间 seed）。

    :param steps: 按执行顺序（id 升序）排列的步骤记录
                  （取 .node_id / .status / .extracted_vars 三个属性）
    :param before_node: 重放场景传被重放节点 id——只拼该节点之前的成功步骤
    :return: {node_id: {变量名: 值}}（ExecutionContext.resume_seed 同构）
    """
    seed: dict[str, dict[str, Any]] = {}
    for step in steps:
        if before_node is not None and getattr(step, "node_id", None) == before_node:
            break
        if getattr(step, "status", None) != "success":
            continue
        node_id = getattr(step, "node_id", None)
        vars_ = getattr(step, "extracted_vars", None)
        if node_id and isinstance(vars_, dict):
            seed.setdefault(node_id, {}).update(vars_)
    return seed

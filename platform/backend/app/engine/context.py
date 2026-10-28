"""执行上下文 v2：节点命名空间变量注册表（2026-09-30 参数模型定案）。

取代旧「row_vars/suite_vars 双域池 + extracted 统一池 dict.update 覆盖」：
- 串行链方案上一棒按 pass_vars 名单快照注入 __prev__ 伪命名空间（相邻定向传参）
- 断点续跑 seed 注入各前缀节点命名空间（报告虚拟上下文）
- 节点运行时产出（参数解析结果 / 后置提取 / SQL 参数结果）写入各自节点命名空间
- 同名冲突三场景从根上消除：引用结构化携带 {"node_id", "var_path"}
- 数据集行不再以平铺键值注入（2026-09-30 入参收敛定案：行数据承载各节点
  params 配置，跨节点共享值改引用上游产出；dataset_vars 仅由
  DagExecutor 读取作节点入参配置源，不进注册表）
"""
from typing import Any

from .variables import PREV_NS, VariableRegistry


class ExecutionContext:
    def __init__(self, dataset_vars: dict[str, Any] | None = None,
                 prev_vars: dict[str, Any] | None = None,
                 resume_seed: dict[str, dict[str, Any]] | None = None):
        """dataset_vars：数据集行数据（{"nodes": {...}}，节点入参配置源，
        由 DagExecutor 消费，不注入注册表）。

        prev_vars：串行链上一棒成员的输出快照（按其 pass_vars 名单收集），
        注入 __prev__ 伪命名空间，本成员入参以 {{__prev__.变量名}} 引用。

        resume_seed 为嵌套结构 {node_id: {变量名: 值}}（report_context 产出）：
        断点续跑时前缀成功步骤的提取值按原节点命名空间还原，下游 {{节点.变量}}
        引用链保持完整。"""
        self.dataset_vars: dict[str, Any] = dataset_vars or {}
        self.registry = VariableRegistry()
        self.registry.inject(PREV_NS, prev_vars)
        for node_id, vars_ in (resume_seed or {}).items():
            self.registry.inject(node_id, vars_)

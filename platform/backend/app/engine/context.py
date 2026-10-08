"""执行上下文 v2：节点命名空间变量注册表（2026-09-30 参数模型定案）。

取代旧「row_vars/suite_vars 双域池 + extracted 统一池 dict.update 覆盖」：
- 套件上游白名单注入 __suite__ 伪命名空间
- 断点续跑 seed 注入 __resume__ 伪命名空间（报告虚拟上下文）
- 节点运行时产出（参数解析结果 / 后置提取 / SQL 参数结果）写入各自节点命名空间
- 同名冲突三场景从根上消除：引用结构化携带 {"node_id", "var_path"}
- 数据集行不再以平铺键值注入（2026-09-30 入参收敛定案：行数据承载各节点
  params 配置，跨节点共享值改引用上游产出；dataset_vars 仅由
  DagExecutor 读取作节点入参配置源，不进注册表）
"""
from typing import Any

from .variables import SUITE_NS, VariableRegistry


class ExecutionContext:
    def __init__(self, dataset_vars: dict[str, Any] | None = None,
                 suite_vars: dict[str, Any] | None = None,
                 resume_seed: dict[str, dict[str, Any]] | None = None):
        """dataset_vars：数据集行数据（{"nodes": {...}}，节点入参配置源，
        由 DagExecutor 消费，不注入注册表）。
        resume_seed 为嵌套结构 {node_id: {变量名: 值}}（report_context 产出）：
        断点续跑时前缀成功步骤的提取值按原节点命名空间还原，下游 {{节点.变量}}
        引用链保持完整。"""
        self.dataset_vars: dict[str, Any] = dataset_vars or {}
        self.registry = VariableRegistry()
        self.registry.inject(SUITE_NS, suite_vars)
        for node_id, vars_ in (resume_seed or {}).items():
            self.registry.inject(node_id, vars_)

    # ---------- 便捷写入口（节点执行期） ----------
    def write(self, node_id: str, var_path: str, value: Any) -> None:
        self.registry.write(node_id, var_path, value)

    def write_extracted(self, node_id: str, extracted: dict[str, Any]) -> None:
        """后置提取批量写入（变量名即提取规则 name）。"""
        for k, v in (extracted or {}).items():
            self.registry.write(node_id, k, v)

    # ---------- 视图 ----------
    def flat_view(self) -> dict[str, Any]:
        """全注册表扁平视图 {命名空间.变量: 值}（报告展示 / 套件白名单快照 / 调试）。"""
        out: dict[str, Any] = {}
        for ns, vars_ in self.registry.to_dict().items():
            for k, v in vars_.items():
                out[f"{ns}.{k}"] = v
        return out

    def to_dict(self) -> dict[str, Any]:
        """报告/快照用全量视图。"""
        return {"registry": self.registry.to_dict()}

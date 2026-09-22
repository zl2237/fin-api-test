"""执行上下文管理：用例内变量统一池 + 三层解析的两个域池。

变量生命周期：整个用例执行期间，各节点后置提取的变量统一存放在同一池
（extracted），用例结束前不销毁，任一接口均可引用。

引用方式：
    ${name}   从上下文统一变量池取值
    ${context.name}   兼容旧写法，等价于 ${name}

测试数据来源唯一性（定案）：环境不再提供变量池——extracted 只由数据集行值
（row_vars，数据集域）与运行时产出（套件上游注入、后置提取、set_field 同步）
构成，测试数据严格来自数据集。

按名自动解析（prepare_request，定案）：参数值只认三个来源——
手动覆盖（节点 pre_process 非空值）> 套件注入（suite_vars，上游白名单
快照，最高优先级注入）> 数据集域（row_vars，绑定数据集当前行）。
运行时变量（后置提取 / set_field 求值同步）不参与按名解析，
仅能通过 ${} 显式引用取值。
"""
from typing import Any


class ExecutionContext:
    def __init__(self, global_vars: dict[str, Any] | None = None,
                 row_vars: dict[str, Any] | None = None, suite_vars: dict[str, Any] | None = None):
        # 数据集域：数据集单套数据的原始引用（按名自动解析取值处）
        self.row_vars: dict[str, Any] = dict(row_vars or {})
        # 套件注入：上游成员白名单快照（按名自动解析的最高优先级来源；
        # 仅套件链下游成员有值，单独执行为空）
        self.suite_vars: dict[str, Any] = dict(suite_vars or {})
        # ${} 求值统一池（数据集行值 < 套件共享值）；环境变量已退役，不再并入
        self.extracted: dict[str, Any] = {**self.row_vars, **self.suite_vars}
        self.global_vars: dict[str, Any] = global_vars or {}

    def update_extracted(self, data: dict[str, Any]):
        """后置提取等运行时产出：只进 ${} 统一池（显式引用可见）。"""
        self.extracted.update(data)

    def set_global(self, key: str, value: Any):
        self.global_vars[key] = value

    def to_dict(self) -> dict[str, Any]:
        return {
            "extracted": self.extracted,
            "global": self.global_vars,
        }

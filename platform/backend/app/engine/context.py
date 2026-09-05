"""执行上下文管理：用例内变量统一池。

变量生命周期：整个用例执行期间，环境全局定义的变量与各节点后置提取的变量
统一存放在同一池（extracted），用例结束前不销毁，任一接口均可引用。

引用方式：
    ${name}   从上下文统一变量池取值
    ${context.name}   兼容旧写法，等价于 ${name}

数据驱动（方案定案 #4）：数据集行的列名即变量名，row_vars 在初始化时
覆盖同名环境变量进池，${列名} 全链路（默认值/前置/断言）直接可用。

套件注入（测试套件）：suite_vars 为上游成员按共享变量白名单产出的快照，
仅在套件链内生效，优先级最高（环境变量 < 数据行变量 < 套件共享值）。
下游用例配置零改动——单独执行时无 suite_vars，行为与普通执行完全一致。
"""
from typing import Any


class ExecutionContext:
    def __init__(self, env_vars: dict[str, Any] = None, global_vars: dict[str, Any] = None,
                 row_vars: dict[str, Any] = None, suite_vars: dict[str, Any] = None):
        # 环境变量在用例开始时并入统一变量池，作为初始已提取变量
        self.env_vars: dict[str, Any] = env_vars or {}
        # 数据行变量优先于同名环境变量（列名即变量名）
        # 套件共享变量优先于一切（上游成员产出，链语义的传递契约）
        self.extracted: dict[str, Any] = {**self.env_vars, **(row_vars or {}), **(suite_vars or {})}
        self.global_vars: dict[str, Any] = global_vars or {}

    def update_extracted(self, data: dict[str, Any]):
        self.extracted.update(data)

    def set_global(self, key: str, value: Any):
        self.global_vars[key] = value

    def to_dict(self) -> dict[str, Any]:
        return {
            "env": self.env_vars,
            "extracted": self.extracted,
            "global": self.global_vars,
        }

"""执行上下文管理：用例内变量统一池。

变量生命周期：整个用例执行期间，环境全局定义的变量与各节点后置提取的变量
统一存放在同一池（extracted），用例结束前不销毁，任一接口均可引用。

引用方式：
    ${name}   从上下文统一变量池取值
    ${context.name}   兼容旧写法，等价于 ${name}
"""
from typing import Any, Dict


class ExecutionContext:
    def __init__(self, env_vars: Dict[str, Any] = None, global_vars: Dict[str, Any] = None):
        # 环境变量在用例开始时并入统一变量池，作为初始已提取变量
        self.env_vars: Dict[str, Any] = env_vars or {}
        self.extracted: Dict[str, Any] = dict(self.env_vars)
        self.global_vars: Dict[str, Any] = global_vars or {}

    def update_extracted(self, data: Dict[str, Any]):
        self.extracted.update(data)

    def set_global(self, key: str, value: Any):
        self.global_vars[key] = value

    def to_dict(self) -> Dict[str, Any]:
        return {
            "env": self.env_vars,
            "extracted": self.extracted,
            "global": self.global_vars,
        }

"""执行上下文管理：环境变量 + 已提取变量 + 全局变量"""
from typing import Any, Dict


class ExecutionContext:
    def __init__(self, env_vars: Dict[str, Any] = None, global_vars: Dict[str, Any] = None):
        self.env_vars: Dict[str, Any] = env_vars or {}
        self.extracted: Dict[str, Any] = {}
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

"""执行事件与持久化接缝（sink）。

设计：
- 执行主链路（_execute_node）只产出 StepResult 事件，不直接落库；
- 落库/收集作为可替换的 sink（ExecutionSink 协议）注入 DagExecutor；
- 生产环境用 DbSink（写 StepRecord/AssertionRecord），测试/dry-run 用内存 sink。

这让执行主链路（请求发送、变量注入、断言、提取）脱离 Session 可测。
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol


@dataclass
class AssertionResult:
    """单条断言的求值结果"""
    type: str
    rule_config: dict[str, Any]
    passed: bool
    actual: Any = None
    expected: Any = None
    message: str = ""


@dataclass
class StepResult:
    """单节点执行的完整产出（事件）"""
    execution_id: int
    node_id: str
    api_name: str
    api_path: str
    api_method: str
    request_headers: dict[str, Any]
    request_body: Any
    response_status: int
    response_body: Any
    response_time_ms: int
    started_at: datetime
    ended_at: datetime
    status: str  # success / failed
    assertions: list[AssertionResult] = field(default_factory=list)
    pre_process: list[dict[str, Any]] | None = None  # 前置处理快照
    post_extract: list[dict[str, Any]] | None = None  # 后置提取规则快照
    extracted_vars: dict[str, Any] | None = None  # 后置提取实际结果 {name: value}


class ExecutionSink(Protocol):
    """执行事件出口：DagExecutor 把每个节点的产出交给 sink。"""

    def record_step(self, result: StepResult) -> None: ...


class DbSink:
    """生产 sink：事件落 StepRecord / AssertionRecord"""

    def __init__(self, db):
        self.db = db

    def record_step(self, result: StepResult) -> None:
        from .. import models

        step = models.StepRecord(
            execution_id=result.execution_id, node_id=result.node_id,
            api_name=result.api_name, api_path=result.api_path, api_method=result.api_method,
            request_headers=result.request_headers, request_body=result.request_body,
            response_status=result.response_status,
            response_body=result.response_body if isinstance(result.response_body, (dict, list)) else {"text": str(result.response_body)},
            response_time_ms=result.response_time_ms,
            started_at=result.started_at, ended_at=result.ended_at,
            status=result.status,
            pre_process=result.pre_process, post_extract=result.post_extract,
            extracted_vars=result.extracted_vars,
        )
        self.db.add(step)
        self.db.commit()
        self.db.refresh(step)
        for ar in result.assertions:
            self.db.add(models.AssertionRecord(
                step_id=step.id, rule_type=ar.type, rule_config=ar.rule_config,
                result=ar.passed, actual_value=str(ar.actual),
                expected_value=str(ar.expected), message=ar.message,
            ))
        self.db.commit()

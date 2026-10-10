"""报告虚拟上下文 v2：从报告步骤拼装节点命名空间 seed（重放/续跑共用口径）。

消费方：
- 重放：前缀成功步骤的产出按 node_id 分组注入注册表（断言/提取 {{}} 引用）
- 续跑：DagExecutor 的 context_seed（ExecutionContext.resume_seed 嵌套注入）

口径：同 node 多条成功（重跑替换）按步骤顺序后者覆盖——「最新成功步骤」生效；
失败步骤的产出不进 seed（该节点重跑时会重新产出）。
产出两类：
- 后置提取值（extracted_vars）
- 入参解析结果（request_body 快照回放）——续跑前缀节点被跳过不再真实执行，
  执行期 prepare_request._register 的入参注册不会发生，下游 {{节点.入参}}
  引用会断链（如 915：n_create 的 bl_no 入参）；用请求体快照按执行期同口径
  （完整路径 + 末段别名）还原。数组请求体锚定首元素字段（与配置路径口径一致）。
数据集行为 per-node 入参配置（非键值），不在此打底（执行侧 dataset_vars 消费）。
"""
import json
from typing import Any, Iterator


def iter_body_paths(obj: Any, prefix: str = "", *, top: bool = True) -> Iterator[tuple[str, Any]]:
    """展开请求体的字段路径（dict 键 / list 元素下标）。

    顶层 list（数组请求体）取首元素展开——入参配置路径以元素字段为锚
    （currency 而非 0.currency），回放口径与其一致。
    """
    if top and isinstance(obj, list):
        obj = obj[0] if obj else None
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f"{prefix}.{k}" if prefix else str(k)
            yield p, v
            yield from iter_body_paths(v, p, top=False)
    elif isinstance(obj, list) and not top:
        for i, v in enumerate(obj):
            p = f"{prefix}.{i}"
            yield p, v
            yield from iter_body_paths(v, p, top=False)


def iter_replay_paths(body: Any, extracted: dict[str, Any] | None = None) -> Iterator[tuple[str, Any]]:
    """入参回放路径：完整路径 + 末段别名（a.b.c 附带 c），供注册表/seed 写入。

    extracted 非空时同名路径跳过——后置提取名优先于同名入参快照。
    消费方：build_report_context（seed 拼装）与续跑重放的入参回放注册。
    """
    for path, val in iter_body_paths(body):
        if extracted is None or path not in extracted:
            yield path, val
            tail = path.rsplit(".", 1)[-1]
            if tail != path and (extracted is None or tail not in extracted):
                yield tail, val


def build_report_context(steps: list[Any], before_node: str | None = None) -> dict[str, dict[str, Any]]:
    """拼装报告虚拟上下文（节点命名空间 seed）。

    :param steps: 按执行顺序（id 升序）排列的步骤记录
                  （取 .node_id / .status / .extracted_vars / .request_body）
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
        if not node_id:
            continue
        ns = seed.setdefault(node_id, {})
        vars_ = getattr(step, "extracted_vars", None)
        extracted = vars_ if isinstance(vars_, dict) else {}
        ns.update(extracted)
        # 入参回放：本步骤后置提取名优先于同名入参路径；历史值被最新成功覆盖
        body = getattr(step, "request_body", None)
        if isinstance(body, str):
            try:
                body = json.loads(body)
            except Exception:
                body = None
        if isinstance(body, (dict, list)):
            for path, val in iter_replay_paths(body, extracted):
                ns[path] = val
    return seed

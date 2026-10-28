"""四来源参数解析器：节点入参取值模型的唯一定义点（2026-09-30 定案）。

来源（单选，spec["source"]）：
1. constant  手动常量：spec = {"source": "constant", "value": <any>}
             —— value 为容器（list/dict）时，内嵌的 spec（ref/func/constant）
                会逐个递归解析（常量元素原样保留）——整组数组/对象一次声明
2. func      内置函数：spec = {"source": "func", "func": "upper",
               "args": [{"name": "s", "kind": "const", "value": "abc"}
                        | {"name": "s", "kind": "ref", "node_id": "n_create", "var_path": "bl_no"}]}
3. ref       上游引用：spec = {"source": "ref", "node_id": "n_create", "var_path": "order_id"}
             —— node_id 可为画布节点 / PREV_NS（串行链上一棒快照）/ 本节点（SQL 参数结果）
4. sql       参数级标量：spec = {"source": "sql", "sql": "SELECT ... {{n_create.bl_no}} ...",
               "column": "order_id"(可选，缺省取首行首列)}
             —— 执行结果按 本节点.参数路径 注册进注册表（供本节点后续参数与下游引用）
ref/func 可附 "as_array": true——解析值包成单元素数组（存量 '[${x}]' 写法的等价迁移）。

执行时序：节点内参数按 order_params 拓扑序逐个解析（SQL 在首个引用它的参数之前
自然执行）；引用取值失败抛 ReferenceError（节点失败并标明引用链），不再静默放行。
"""
from typing import Any

from .functions import call_function
from .variables import PLACEHOLDER_RE, VariableRegistry


class SqlExecutionError(Exception):
    """来源4 SQL 执行失败（连接异常/语法错误等）。"""


def render_placeholders(text: str, registry: VariableRegistry) -> str:
    """{{node.var}} 占位渲染（SQL 内联值，字符串转义防注入）。

    取不到值的引用抛 ReferenceError（对齐「不静默放行」定案）。
    """
    def repl(m):
        node_id, _, var_path = m.group(1).partition(".")
        val = registry.read(node_id, var_path)
        if val is None:
            from .variables import ReferenceError
            raise ReferenceError(f"占位符取值失败：{node_id}.{var_path}")
        if isinstance(val, str):
            return "'" + val.replace("'", "''") + "'"
        if val is None:  # pragma: no cover - read 已过滤 None
            return "NULL"
        return str(val)

    return PLACEHOLDER_RE.sub(repl, text)


def _resolve_arg(arg: dict, registry: VariableRegistry) -> tuple[str, Any]:
    """函数入参求值：const 直接取值 / ref 注册表解析。"""
    name = arg.get("name") or ""
    if arg.get("kind") == "ref":
        return name, registry.resolve({"node_id": arg.get("node_id"), "var_path": arg.get("var_path")})
    return name, arg.get("value")


def _extract_scalar(rows: list, column: str | None) -> Any:
    """SQL 结果标量化：column 指定列；缺省首行首列；无行返回 None（空结果非错误）。"""
    if not rows:
        return None
    first = rows[0]
    if not isinstance(first, dict):
        return first
    if column:
        return first.get(column)
    if first:
        return next(iter(first.values()))
    return None


def _resolve_embedded(param_path: str, raw: Any, *, registry: VariableRegistry,
                      self_node: str, db_client: Any) -> Any:
    """constant 容器值内嵌 spec 的递归解析（常量元素原样保留）。

    内嵌 spec 仅允许 constant/func/ref——SQL 来源禁用（读库取值请声明为
    独立参数；旧「动作值禁 SQL」同口径）。
    """
    if isinstance(raw, dict) and raw.get("source"):
        if raw.get("source") == "sql":
            raise ValueError(f"{param_path}：容器常量内嵌 SQL 来源禁用（读库取值请声明为独立参数）")
        return resolve_param(param_path, raw, registry=registry,
                             self_node=self_node, db_client=None)
    if isinstance(raw, list):
        return [_resolve_embedded(f"{param_path}[{i}]", item, registry=registry,
                                  self_node=self_node, db_client=db_client)
                for i, item in enumerate(raw)]
    if isinstance(raw, dict):
        return {k: _resolve_embedded(f"{param_path}.{k}", v, registry=registry,
                                     self_node=self_node, db_client=db_client)
                for k, v in raw.items()}
    return raw


def resolve_param(param_path: str, spec: dict, *, registry: VariableRegistry,
                  self_node: str, db_client: Any) -> Any:
    """解析单个参数并按需注册产出（来源4 结果入池：节点.参数路径）。

    返回解析后的参数值。spec 非法抛 ValueError。
    """
    source = (spec or {}).get("source")
    as_array = bool((spec or {}).get("as_array"))  # 单值数组化（存量 '[${x}]' 写法的等价迁移）
    if source == "constant":
        return _resolve_embedded(param_path, spec.get("value"), registry=registry,
                                 self_node=self_node, db_client=db_client)
    if source == "ref":
        val = registry.resolve({"node_id": spec.get("node_id"), "var_path": spec.get("var_path")})
        return [val] if as_array else val
    if source == "func":
        kwargs = dict(_resolve_arg(a, registry) for a in (spec.get("args") or []) if isinstance(a, dict))
        val = call_function(spec.get("func") or "", kwargs)
        return [val] if as_array else val
    if source == "sql":
        sql = (spec.get("sql") or "").strip()
        if not sql:
            raise ValueError(f"参数 {param_path}：SQL 来源缺少 sql 语句")
        if db_client is None:
            raise SqlExecutionError(f"参数 {param_path}：环境未配置数据库连接")
        rendered = render_placeholders(sql, registry)
        try:
            rows = db_client.query(rendered)
        except Exception as e:
            raise SqlExecutionError(f"参数 {param_path}：SQL 执行失败：{e}") from e
        val = _extract_scalar(rows, spec.get("column"))
        # SQL 结果入池（定案：以 节点.参数路径 注册，下游与本节点后续参数直接引用）
        registry.write(self_node, param_path, val)
        return val
    raise ValueError(f"参数 {param_path}：未知来源 {source!r}")

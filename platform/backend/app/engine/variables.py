"""节点命名空间变量注册表：多节点同名冲突的根治点。

设计定案（2026-09-30 需求拷问纪要 + 入参收敛定案）：
- 变量全名 = 命名空间.变量路径；存储结构 {ns: {var_path: value}}
- 写入方仅三类：数据集行参数解析结果（节点.参数路径，另附末段别名兼容
  旧 {{节点.末段}} 引用名）/ 后置提取 / SQL 参数结果
- 引用是结构化的 {"node_id", "var_path"}，取不到值 = 执行失败
  （旧引擎「未定义变量保留 ${} 占位符静默放行」的行为已废止）
- 同名冲突（同名异值 / 同名异型 / 同名嵌套层级不一致）从根上消除：
  不同命名空间互不覆盖，引用永远显式携带命名空间
- 伪节点：串行链方案上一棒按 pass_vars 名单快照注入 "__prev__"（链式相邻定向传参）；
  "__dataset__" 平铺键值注入已退役（入参收敛到数据集行 per-node 配置）

SQL 占位语法（替代旧 ${xxx}）：{{node_id.var_path}}
- 与旧语法刻意区分：可静态解析依赖、迁移时可精确扫描
- node_id 指向本节点时即引用本节点其他参数（SQL 参数结果按 节点.参数路径 注册，
  参数间依赖由此产生）
"""
import re
from typing import Any

# 串行链方案伪命名空间（非画布节点，注入型变量域：上一棒成员的输出快照）
PREV_NS = "__prev__"

# SQL / 模板占位符：{{node_id.var.path}}（node_id 为画布节点 id 或伪命名空间）
PLACEHOLDER_RE = re.compile(r"\{\{([\w.\-]+)\}\}")


class ReferenceError(Exception):
    """结构化引用取值失败（引用链描述见 message）。"""


class CycleError(Exception):
    """参数间依赖成环（保存时校验与运行时防御共用）。"""


def split_ref(text: str) -> tuple[str, str]:
    """ '{{n_create.order_id}}' -> ('n_create', 'order_id')；'{{__prev__.bl_no}}' -> ('__prev__', 'bl_no')"""
    node_id, _, var_path = text.partition(".")
    return node_id, var_path


def extract_refs(text: str) -> list[tuple[str, str]]:
    """静态扫描文本中的全部 {{节点.变量}} 引用（SQL 依赖分析 / 保存时校验共用）。"""
    return [split_ref(m.group(1)) for m in PLACEHOLDER_RE.finditer(text or "")]


class VariableRegistry:
    """节点命名空间变量注册表（执行期实例，随 ExecutionContext 存活）。"""

    def __init__(self) -> None:
        self._ns: dict[str, dict[str, Any]] = {}

    # ---------- 写入 ----------
    def inject(self, ns: str, values: dict[str, Any] | None) -> None:
        """批量注入（数据集行值 / 串行链上一棒快照 / 断点续跑 seed）。同名后写覆盖先写。"""
        if values:
            self._ns.setdefault(ns, {}).update(values)

    def write(self, ns: str, var_path: str, value: Any) -> None:
        """单变量写入（set_field / 后置提取 / SQL 参数结果）。"""
        self._ns.setdefault(ns, {})[var_path] = value

    # ---------- 读取 ----------
    def read(self, node_id: str, var_path: str) -> Any | None:
        return self._ns.get(node_id, {}).get(var_path)

    def resolve(self, ref: dict) -> Any:
        """结构化引用取值：{"node_id", "var_path"}。取不到抛 ReferenceError。"""
        node_id = (ref or {}).get("node_id") or ""
        var_path = (ref or {}).get("var_path") or ""
        if not node_id or not var_path:
            raise ReferenceError(f"引用不完整：{ref}")
        val = self.read(node_id, var_path)
        if val is None:
            raise ReferenceError(f"引用取值失败：{node_id}.{var_path}（未产出或值为 null）")
        return val

    def vars_of(self, node_id: str) -> dict[str, Any]:
        """某命名空间已注册的全部变量（前端下拉数据源 / 迁移消歧用）。"""
        return dict(self._ns.get(node_id, {}))

    def to_dict(self) -> dict[str, dict[str, Any]]:
        """全量视图（报告展示 / 调试）。"""
        return {ns: dict(vs) for ns, vs in self._ns.items()}


# ============ 参数间依赖拓扑排序 ============

def iter_spec_refs(spec: Any):
    """产出 spec 树内全部引用 (node_id, var_path)。

    覆盖：ref spec（含 constant 容器值内嵌的 spec）/ func 的 ref 入参 /
    SQL {{节点.变量}} 占位。容器（无 source 键的 dict / list）递归展开。
    """
    if isinstance(spec, list):
        for item in spec:
            yield from iter_spec_refs(item)
        return
    if not isinstance(spec, dict):
        return
    src = spec.get("source")
    if src == "ref":
        yield spec.get("node_id") or "", spec.get("var_path") or ""
    elif src == "func":
        for arg in spec.get("args") or []:
            if isinstance(arg, dict) and arg.get("kind") == "ref":
                yield arg.get("node_id") or "", arg.get("var_path") or ""
    elif src == "sql":
        yield from extract_refs(spec.get("sql") or "")
    elif src == "constant":
        yield from iter_spec_refs(spec.get("value"))
    else:
        for v in spec.values():
            yield from iter_spec_refs(v)


def param_dependencies(spec: dict, self_node: str) -> set[str]:
    """提取单个参数 spec 对本节点其他参数的依赖（指向本节点的引用）。

    依赖可为参数完整路径或其末段（旧 {{节点.末段}} 引用名，见 order_params 别名归一）。
    """
    deps: set[str] = set()
    for node_id, var_path in iter_spec_refs(spec):
        if node_id == self_node and var_path:
            deps.add(var_path)
    return deps


def order_params(params: dict[str, dict], self_node: str) -> list[str]:
    """按参数间依赖拓扑排序（稳定：同层按原路径序）。

    - 依赖归一：完整参数路径优先；否则按末段别名映射（旧 set_field 注册名
      = path 末段，同名后写覆盖先写——别名取最后一个同名参数，与运行期
      注册语义一致）
    - 通配路径参数（列表.*.字段）自动依赖其容器前缀参数（存在时），
      保证逐元素展开时容器已就位；对通配参数的具体下标引用
      （列表.下标.字段）归一为依赖该通配参数
    params: {参数路径: 来源spec}；成环抛 CycleError。
    """
    import re as _re

    alias: dict[str, str] = {}
    wildcards = [p for p in params if "*" in p]
    wc_patterns = [(p, _re.compile("^" + r"\.".join(
        r"\d+" if s == "*" else _re.escape(s) for s in p.split(".")) + "$"))
        for p in wildcards]

    def _norm(dep: str) -> str | None:
        if dep in params:
            return dep
        hit = alias.get(dep)
        if hit:
            return hit
        for p, pat in wc_patterns:
            if pat.match(dep):
                return p
        return None

    for p in params:
        if "*" in p:
            continue  # 通配参数运行期只注册具体下标路径，不注册末段别名
        tail = p.rsplit(".", 1)[-1]
        alias[tail] = p  # 同名末段：后写覆盖（注册表 last-write-wins）

    deps: dict[str, set[str]] = {}
    for p, spec in params.items():
        d = {norm for norm in map(_norm, param_dependencies(spec, self_node)) if norm is not None}
        deps[p] = d
        if "*" in p:
            prefix = p.split(".*", 1)[0]
            if prefix in params:
                deps[p].add(prefix)

    ordered: list[str] = []
    done: set[str] = set()
    pending = list(params.keys())
    while pending:
        progressed = [p for p in pending if deps.get(p, set()) <= done]
        if not progressed:
            raise CycleError(f"参数间依赖成环：{sorted(pending)}")
        ordered.extend(progressed)
        done.update(progressed)
        pending = [p for p in pending if p not in done]
    return ordered

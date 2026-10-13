"""保存时静态校验器：四来源参数模型的完整性（数据集节点配置保存入口调用）。

校验项（2026-09-30 定案「保存时全量悬空引用校验，拒绝保存并定位到具体参数」；
同日「动作概念退场」后产出集口径收敛为参数）：
- 来源合法性：source ∈ constant/func/ref/sql；函数名在注册表
- 通配路径参数（列表.*.字段）：至多一个 * 且为独立路径段；* 只能出现在
  具体参数里（SQL/header 参数不支持通配）
- 引用节点存在且拓扑在前（防引用未执行的后置/旁支节点；环由 topo_order 拦）
- 悬空变量：引用 (节点, 变量首段) 不在该节点静态产出集 → 拒绝
  产出集 = 参数路径 ∪ 参数末段别名（旧 {{节点.末段}} 引用名兼容）∪ post_extract 提名
- 本节点自引用：指向本节点其他参数（完整路径或末段别名）；解析顺序由
  order_params 拓扑保证（成环报错）
- 参数间依赖环（order_params）
- ${} 残留扫描（旧语法已废止，防漏网）

__suite__ 白名单运行期注入，保存期放行；__dataset__ 平铺键值已随入参收敛
到数据集行而退役（2026-09-30 定案，跨节点共享值改引用上游产出）。
"""
import re
from typing import Any

from .functions import FUNCTIONS
from .variables import SUITE_NS, CycleError, extract_refs, iter_spec_refs, order_params

_LEGAL_SOURCES = {"constant", "func", "ref", "sql"}
_OLD_SYNTAX_RE = re.compile(r"\$\{")


def _as_dict_list(x: Any) -> list[dict]:
    if not x:
        return []
    if isinstance(x, dict):
        x = x.get("__root__") or []
    out = []
    for item in x:
        if item is None:
            continue
        out.append(item if isinstance(item, dict)
                   else (item.model_dump() if hasattr(item, "model_dump") else vars(item)))
    return out


def _productions(config: dict) -> set[str]:
    """节点静态产出变量名集合（参数路径 + 末段别名 + post_extract 提名）。

    通配参数（列表.*.字段）仅登记通配路径本身：运行期按具体下标注册，
    末段别名不注册（旧 iterate_set 同样不注册产出）。
    """
    out: set[str] = set()
    params = config.get("params") or {}
    for path in (params.get("body") or {}):
        out.add(path)
        if "*" not in path:
            out.add(path.rsplit(".", 1)[-1])
    for rule in _as_dict_list(config.get("post_extract")):
        if rule.get("name"):
            out.add(rule["name"])
    return out


def _spec_errors(spec: Any, where: str, *, embedded: bool = False) -> list[str]:
    """spec 树（含 constant 容器内嵌）的来源/函数名静态检查。

    embedded=True（容器内嵌 spec）时 SQL 来源报错——读库取值须声明为独立参数。
    """
    errs: list[str] = []
    if isinstance(spec, list):
        for i, item in enumerate(spec):
            errs.extend(_spec_errors(item, f"{where}[{i}]", embedded=embedded))
        return errs
    if not isinstance(spec, dict) or not spec.get("source"):
        return errs
    src = spec.get("source")
    if src not in _LEGAL_SOURCES:
        errs.append(f"{where}：未知来源 {src!r}")
    elif src == "sql" and embedded:
        errs.append(f"{where}：容器常量内嵌 SQL 来源禁用（读库取值请声明为独立参数）")
    elif src == "func" and spec.get("func") not in FUNCTIONS:
        errs.append(f"{where}：未知函数 {spec.get('func')!r}")
    if src == "constant":
        errs.extend(_spec_errors(spec.get("value"), f"{where} 常量值", embedded=True))
    return errs


def _scan_old_syntax(obj: Any, where: str, errs: list[str]) -> None:
    """递归扫描字符串值中的 ${ 残留（constant 值/SQL 全查）。"""
    if isinstance(obj, str):
        if _OLD_SYNTAX_RE.search(obj):
            errs.append(f"{where}：残留旧表达式语法 ${{...}}（已废止，请改用来源/引用配置）")
    elif isinstance(obj, dict):
        for k, v in obj.items():
            _scan_old_syntax(v, f"{where}.{k}", errs)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            _scan_old_syntax(v, f"{where}[{i}]", errs)


def _check_wildcard_path(path: str, where: str, errs: list[str]) -> None:
    """通配路径参数形态校验：至多一个 *，且为独立路径段（前后以点号或首尾为界）。"""
    if "*" not in path:
        return
    if path.count("*") > 1:
        errs.append(f"{where}：通配路径至多支持一个 *（当前 {path!r}）")
        return
    seg = [s for s in path.split(".") if s == "*"]
    if len(seg) != 1:
        errs.append(f"{where}：通配 * 必须是独立的路径段（如 list.*.field，当前 {path!r}）")


def _node_names(dag: dict | None) -> dict[str, str]:
    """dag 节点 id → 中文名（画布节点 data.label）。校验消息展示中文节点名，
    编码仅在旁注保留（同用例存在多个同名节点时仍可区分）。"""
    out: dict[str, str] = {}
    for n in (dag or {}).get("nodes", []):
        if isinstance(n, dict) and n.get("id"):
            label = (n.get("data") or {}).get("label") or n.get("label")
            if label:
                out[str(n["id"])] = str(label)
    return out


def _disp(names: dict[str, str], node_id: str) -> str:
    """消息展示名：「中文名」(编码)；无中文名（含引用不存在的节点）退化为编码。"""
    label = names.get(node_id)
    return f"「{label}」({node_id})" if label else node_id


def validate_case_configs(dag: dict | None, node_configs: Any) -> list[str]:
    """返回错误消息列表（空列表 = 通过）。

    :param dag: 用例 dag_config（nodes/edges）
    :param node_configs: 节点配置载荷列表（数据集行内 params ×
        节点结构配置的 post_extract/assertions，由调用方组装；dict/模型均可）
    """
    errs: list[str] = []
    # 键收窄为 str（node_id 缺失时 None → "None"，与旧 f-string 展示一致）
    configs = {str(c.get("node_id")): c for c in _as_dict_list(node_configs)}
    if not configs:
        return errs

    # 拓扑前置集（环由 topo_order 抛错；此处容错退化为全节点）
    order: list[str] = []
    try:
        from .topo import topo_order
        order, _ = topo_order(dag or {})
    except Exception:
        order = list(configs.keys())
    node_set = {n.get("id") for n in (dag or {}).get("nodes", []) if isinstance(n, dict)}
    names = _node_names(dag)

    productions = {nid: _productions(c) for nid, c in configs.items()}

    def _check_ref(node_id: str, self_node: str, allowed_self: set[str],
                   ref_node: str, var_path: str, where: str):
        if ref_node == self_node:
            if var_path not in allowed_self:
                errs.append(f"节点 {_disp(names, node_id)} {where}：自引用 {var_path!r} 未在本节点产出"
                            f"（本节点参数/提取；可选：{sorted(allowed_self) if allowed_self else '无'}）")
            return
        if ref_node == SUITE_NS:
            return  # 套件白名单运行期注入，保存期放行
        if ref_node not in node_set:
            errs.append(f"节点 {_disp(names, node_id)} {where}：引用了不存在的节点 {ref_node!r}")
            return
        if order and ref_node in order and self_node in order \
                and order.index(ref_node) > order.index(self_node):
            errs.append(f"节点 {_disp(names, node_id)} {where}：引用了拓扑后置节点 {_disp(names, ref_node)}"
                        f"（引用目标必须在该节点之前执行）")
            return
        if var_path.split(".")[0] not in productions.get(ref_node, set()):
            avail = sorted(productions.get(ref_node, set()))
            errs.append(f"节点 {_disp(names, node_id)} {where}：悬空引用 {_disp(names, ref_node)}.{var_path}"
                        f"（该节点产出：{avail if avail else '无'}）")

    for nid, cfg in configs.items():
        params = cfg.get("params") or {}
        body_params: dict = params.get("body") or {}
        header_params: dict = params.get("headers") or {}

        # 参数间依赖环（依赖归一与通配前缀见 order_params）
        try:
            order_params({p: s for p, s in body_params.items() if isinstance(s, dict)}, nid)
        except CycleError as e:
            errs.append(f"节点 {_disp(names, nid)}：{e}")

        # 自引用合法集：本节点全部参数路径 + 末段别名（通配路径原样可用；
        # 解析顺序由 order_params 拓扑保证，成环在上面报错）
        allowed_self = set(body_params)
        for p in body_params:
            if "*" not in p:
                allowed_self.add(p.rsplit(".", 1)[-1])

        for path, spec in body_params.items():
            _check_wildcard_path(path, f"节点 {_disp(names, nid)} 参数 {path}", errs)
            errs.extend(_spec_errors(spec, f"节点 {_disp(names, nid)} 参数 {path}"))
            _scan_old_syntax(spec.get("value") if isinstance(spec, dict) else None,
                             f"参数 {path}", errs)
            for rn, vp in iter_spec_refs(spec):
                _check_ref(nid, nid, allowed_self, rn, vp, f"参数 {path}")
        for name, spec in header_params.items():
            errs.extend(_spec_errors(spec, f"节点 {_disp(names, nid)} header {name}"))
            for rn, vp in iter_spec_refs(spec):
                _check_ref(nid, nid, allowed_self, rn, vp, f"header {name}")

        for rule in _as_dict_list(cfg.get("post_extract")):
            name = rule.get("name") or "?"
            _scan_old_syntax(rule.get("sql"), f"节点 {_disp(names, nid)} 提取 {name}", errs)
            for rn, vp in extract_refs(rule.get("sql") or ""):
                # 提取规则按序执行且实时注册：同节点引用放宽到本节点产出全集
                #（规则间顺序错配由运行期显性报错兜底）
                if rn == nid:
                    if vp.split(".")[0] not in productions[nid]:
                        errs.append(f"节点 {_disp(names, nid)} 提取 {name}：引用了本节点未产出的变量 {vp!r}")
                    continue
                _check_ref(nid, nid, allowed_self, rn, vp, f"提取 {name}")

        for rule in _as_dict_list(cfg.get("assertions")):
            at = rule.get("type") or "?"
            _scan_old_syntax(rule.get("sql"), f"节点 {_disp(names, nid)} 断言 {at}", errs)
            for rn, vp in extract_refs(rule.get("sql") or ""):
                # 断言运行期在本节点提取之后：允许引用本节点提取产出
                if rn == nid:
                    if vp.split(".")[0] not in productions[nid]:
                        errs.append(f"节点 {_disp(names, nid)} 断言 {at}：引用了本节点未产出的变量 {vp!r}")
                    continue
                _check_ref(nid, nid, allowed_self, rn, vp, f"断言 {at}")
            # 期望值若为 spec（ref/func）也检查引用
            if isinstance(rule.get("expected"), dict) and rule["expected"].get("source"):
                errs.extend(_spec_errors(rule["expected"], f"节点 {_disp(names, nid)} 断言 {at} 期望值"))
                for rn, vp in iter_spec_refs(rule["expected"]):
                    if rn == nid:
                        if vp.split(".")[0] not in productions[nid]:
                            errs.append(f"节点 {_disp(names, nid)} 断言 {at}：引用了本节点未产出的变量 {vp!r}")
                        continue
                    _check_ref(nid, nid, allowed_self, rn, vp, f"断言 {at} 期望值")

    return errs


# ============ 后置提取 SQL 基本校验 ============
# 目标是拦截"肉眼难察、运行时静默失败"的低级笔误（提取结果为空、报告里查不到原因）：
# - 列名与关键字粘连（pay_invoice_apply_idfrom —— FROM 非独立词，TiDB 直接语法错误）
# - SELECT 缺 FROM / 语句不以 SQL 关键字开头
# {{节点.变量}} 占位先替换为字面量再扫描（避免 {{x}}from 这类写法误判）
_SQL_START_RE = re.compile(r"^\s*(select|insert|update|delete|show|with|desc)\b", re.I)
# 关键字前紧贴字母/数字（无空格/括号/下划线分隔）→ 粘连。只收长关键字，避免 in/is/as/on/set
# 这类常见子串（login/visit）误报；下划线连接的合法列名（user_group/group_id）不命中
# （下划线属标识符连接，不算粘连；\b 在 group_id 的 _g 处也不成立）
_SQL_GLUED_RE = re.compile(
    r"[A-Za-z0-9](?:from|where|select|insert|update|delete|values|into|order|group|limit|"
    r"having|between|union|distinct|inner|outer)\b", re.I)


def validate_post_extract_sql(node_configs: list | None, dag: dict | None = None) -> None:
    """编排保存入口：校验各节点 post_extract 中 source=db 的 SQL 基本形态。
    兼容 dict 与 Pydantic 模型（路由入参经 schema 解析后是 NodeConfigIn 对象，
    无 .get 方法——曾致线上保存用例 500）。dag 传入时消息展示中文节点名。"""
    if not node_configs:
        return
    names = _node_names(dag)
    for nc in node_configs:
        if nc is None:
            continue
        if not isinstance(nc, dict):
            nc = nc.model_dump() if hasattr(nc, "model_dump") else vars(nc)
        node_id = nc.get("node_id") or "?"
        disp = _disp(names, node_id)
        for rule in nc.get("post_extract") or []:
            if not isinstance(rule, dict) or rule.get("source") != "db":
                continue
            sql = str(rule.get("sql") or "").strip()
            if not sql:
                continue
            name = rule.get("name") or "?"
            # {{节点.变量}} 占位 → 字面量（防占位内容干扰词法扫描；旧 ${} 已废止）
            scanned = re.sub(r"\{\{[^{}]*\}\}", "1", sql)
            if not _SQL_START_RE.match(scanned):
                raise ValueError(
                    f"节点 {disp} 后置提取「{name}」的 SQL 未以 SELECT/UPDATE/DELETE 等关键字开头，请检查")
            m = _SQL_GLUED_RE.search(scanned)
            if m:
                frag = m.group(0)
                raise ValueError(
                    f"节点 {disp} 后置提取「{name}」的 SQL 疑似标识符与关键字粘连"
                    f"（…{frag}…，缺少空格），请检查：{sql[:120]}")
            if scanned.lstrip()[:6].lower() == "select" and not re.search(r"\bfrom\b", scanned, re.I):
                raise ValueError(
                    f"节点 {disp} 后置提取「{name}」的 SELECT 缺少 FROM（可能列名与 FROM 粘连），请检查：{sql[:120]}")

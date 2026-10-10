"""请求组装 v3：四来源参数模型唯一入口（2026-09-30「动作概念退场」定案）。

节点入参的全部语义收敛到数据集行 params 的取值来源声明，前置动作引擎
（set_field/iterate_set/exec_sql/...）已删除：

1. 骨架：有字段定义 → 空 dict（模板静态值保留）；无字段 → request_template
2. 数组字段建空表占位（嵌套路径参数如 x.0.y 才能落进 list）
3. 参数解析（config.params["body"]）：按 order_params 拓扑序逐个解析
   （constant/func/ref/sql；constant 容器值内嵌 spec 递归求值；SQL 在首个
   引用它的参数之前自然执行）。解析结果注册进注册表（节点.参数路径 +
   末段别名，兼容旧 {{节点.末段}} 引用名）
4. 通配路径参数（列表.*.字段）：容器参数就位后逐元素独立求值写入
   （iterate_set 的声明式等价；同下标同步用 ref 通配表达）
5. 类型还原（coerce_json_strings）→ 字段类型强转（apply_field_types）
6. file 字段剥离 → headers 组装（环境公共头 + 接口模板覆盖 + params.headers
   逐头解析，节点参数压过模板）

引用取值失败 = 节点失败并标明引用链（ReferenceError），不再静默保留占位符。
"""
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from .param_resolver import resolve_param
from .nested_path import get_nested_value, set_nested_value
from .type_coercer import apply_field_types, coerce_json_strings
from .variables import order_params
from ..services.body_builder import pop_file_fields_from_body


@dataclass
class RequestParts:
    """组装产物：JSON body（file 字段已剥离）、最终 headers、multipart file 字段。"""

    body: Any
    headers: dict
    file_fields: list  # [(path, file_id)]


def _empty_placeholder(field_type: str) -> Any:
    """空值占位：string/file/未知 → ""；array → []（PHP 空数组语义）；其余 → None。"""
    if field_type in ("string", "file"):
        return ""
    if field_type == "array":
        return []
    return None


def _register(registry, self_node: str, path: str, value: Any) -> None:
    """参数解析结果入池：完整路径 + 末段别名（旧 {{节点.末段}} 引用名兼容；
    同名末段后写覆盖先写，与旧 set_field 注册语义一致）。"""
    registry.write(self_node, path, value)
    tail = path.rsplit(".", 1)[-1]
    if tail != path:
        registry.write(self_node, tail, value)


def _specialize(spec: Any, idx: int, self_node: str) -> Any:
    """通配下标特化：spec 树内指向本节点的通配引用（var_path 含 *）把 *
    替换为当前元素下标（含 constant 容器内嵌与 func ref 入参）。"""
    if isinstance(spec, list):
        return [_specialize(x, idx, self_node) for x in spec]
    if not isinstance(spec, dict):
        return spec
    out = dict(spec)
    if spec.get("source") == "ref" and spec.get("node_id") == self_node \
            and "*" in (spec.get("var_path") or ""):
        out["var_path"] = spec["var_path"].replace("*", str(idx))
    elif spec.get("source") == "func":
        out["args"] = [
            {**a, "var_path": a["var_path"].replace("*", str(idx))}
            if isinstance(a, dict) and a.get("kind") == "ref"
            and a.get("node_id") == self_node and "*" in (a.get("var_path") or "")
            else a
            for a in (spec.get("args") or [])
        ]
    elif spec.get("source") == "constant":
        out["value"] = _specialize(spec.get("value"), idx, self_node)
    return out


def _apply_wildcard_param(body: Any, path: str, spec: dict, *, registry,
                          self_node: str, db_client) -> None:
    """通配路径参数（列表.*.字段）逐元素展开。

    前缀容器非列表或元素非 dict 时静默跳过（与旧 iterate_set 口径一致）；
    每元素独立求值（func 每次产新值，如逐行 generate_unique_id），
    结果按具体路径（列表.下标.字段）注册。
    """
    prefix = path.split(".*", 1)[0]
    container = get_nested_value(body, prefix)
    if not isinstance(container, list):
        return
    for idx, item in enumerate(container):
        if not isinstance(item, dict):
            continue
        concrete = path.replace("*", str(idx), 1)
        val = resolve_param(concrete, _specialize(spec, idx, self_node),
                            registry=registry, self_node=self_node,
                            db_client=db_client)
        set_nested_value(body, concrete, val)
        registry.write(self_node, concrete, val)


def prepare_request(api, config, *, context, self_node: str,
                    base_headers, db_client) -> RequestParts:
    """组装一个节点的请求。

    - api：ApiDefinition（fields / request_template / headers_template）
    - config：数据集行内该节点的入参配置视图（params；None = 无配置）
    - context：ExecutionContext（v2，registry 注册表）
    - self_node：本节点 id（命名空间锚：参数解析结果 / SQL 结果归属）
    """
    registry = context.registry
    fields = getattr(api, "fields", None) or []
    params_cfg = (getattr(config, "params", None) or {}) if config else {}
    body_params: dict[str, dict] = params_cfg.get("body") or {}
    header_params: dict[str, dict] = params_cfg.get("headers") or {}

    # 1. 骨架
    if fields:
        body: Any = {}
        resolve_keys = [f.key for f in fields if f.key]
    else:
        body = deepcopy(api.request_template if api.request_template is not None else {})
        resolve_keys = list(body.keys()) if isinstance(body, dict) else []
    field_types = {f.key: (f.field_type or "string") for f in fields if f.key}

    # 2. 数组字段先建空表占位：嵌套路径参数（如 writeoff_object.0.xxx）才能落进
    #    list——set_nested_value 对不存在的中间键建 dict，会破坏数组语义
    #    （模板静态数组值保留；此时 body[key] 为 None/"" 才占位）
    for key, ft in field_types.items():
        if ft == "array" and get_nested_value(body, key) in (None, ""):
            set_nested_value(body, key, [])

    # 3. 参数解析：拓扑序（依赖本节点其他参数的先其依赖）；未配置字段空占位。
    #    通配路径参数在容器参数后逐元素展开
    for path in order_params(body_params, self_node):
        spec = body_params[path]
        if "*" in path:
            _apply_wildcard_param(body, path, spec, registry=registry,
                                  self_node=self_node, db_client=db_client)
            continue
        val = resolve_param(path, spec, registry=registry,
                            self_node=self_node, db_client=db_client)
        # 数组字段的空标量参数（constant ""/None，常见于迁移产物）不落盘：
        # 下方归一本会转 []，先写会破坏嵌套路径参数（x.0.y）所需的 list 骨架
        if val in (None, "") and field_types.get(path.split(".")[0]) == "array":
            continue  # 不写也不注册（与旧动作空值跳过语义一致，避免覆盖末段别名）
        set_nested_value(body, path, val)
        _register(registry, self_node, path, val)
    for key in dict.fromkeys(resolve_keys):
        if key in body_params:
            continue
        target = body if not (isinstance(body, list) and body and isinstance(body[0], dict)) else body[0]
        if get_nested_value(target, key) is not None:
            continue  # 模板静态值保留，不用空值占位覆盖
        set_nested_value(target, key, _empty_placeholder(field_types.get(key, "string")))

    # array 字段空标量归一（""/None → []）：空值参数落盘后，
    # 嵌套路径参数（如 writeoff_object.0.xxx）才能按数组下标建元素
    for key, ft in field_types.items():
        if ft != "array":
            continue
        if get_nested_value(body, key) in (None, ""):
            set_nested_value(body, key, [])

    # 数组请求体（字段骨架路径）：request_template 为 list 表示 body 本身是 [{...}]
    if fields and isinstance(api.request_template, list):
        body = [body]

    # 4. 类型还原与强转
    body = coerce_json_strings(body)
    body = apply_field_types(body, api)

    # 5. file 字段剥离
    body, file_fields = pop_file_fields_from_body(body, api)

    # 6. headers：环境公共头 + 接口模板（null 显式剔除）+ 节点参数覆盖
    headers = {**deepcopy(base_headers or {}),
               **deepcopy(getattr(api, "headers_template", None) or {})}
    headers = {k: v for k, v in headers.items() if v is not None}
    for name, spec in header_params.items():
        headers[name] = resolve_param(f"header:{name}", spec, registry=registry,
                                      self_node=self_node, db_client=db_client)
    return RequestParts(body=body, headers=headers, file_fields=file_fields)

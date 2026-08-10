"""请求体构建服务：从接口字段定义组装请求体。

从 DagExecutor._build_request_body / _parse_field_value / _set_nested 提取，
供 DagExecutor 执行链路与接口调试（debug_api）复用，消除 debug_api 对
DagExecutor 实例的依赖（进而删除 _DummyCase 占位对象）。

行为与原 DagExecutor 实现完全一致：
- 优先用 ApiField 组装请求体（支持点号嵌套路径）
- 无 fields 时回退到 request_template（兼容旧数据）
- request_template 为 list 时标记数组请求体，组装结果包裹为 [{...}]
"""
import json
from copy import deepcopy
from typing import Any, Dict, Optional


def build_request_body(api) -> Any:
    """按 api.fields 组装请求体；无 fields 时回退 request_template。"""
    fields = getattr(api, "fields", None) or []
    if not fields:
        return deepcopy(api.request_template or {})

    # request_template 为 list 表示数组请求体（body 本身是 [{...}]）
    is_array_body = isinstance(api.request_template, list)

    body: Dict[str, Any] = {}
    for f in fields:
        if not f.key:
            continue
        # 解析默认值：支持 JSON（array/object 类型）、表达式、纯字符串
        val = parse_field_value(f.default_value, f.field_type)
        # 按点号路径设置到嵌套 dict
        set_nested(body, f.key, val)
    return [body] if is_array_body else body


def parse_field_value(raw: Optional[str], field_type: str) -> Any:
    """解析字段默认值。

    - 空 → string 给空串，其他给 None
    - 含 ${} 表达式 → 保留原字符串，待表达式引擎求值后再由 _coerce_json_strings 还原类型
    - array/object → 尝试 JSON 解析，失败保留原值
    - int → 转整数，失败保留原值
    - bool → 按常见真值字符串判定
    - string → 保留原值（含 ${...} 表达式由后续 preprocessor 求值）
    """
    if raw is None or raw == "":
        return "" if field_type == "string" else None
    # 含 ${} 表达式的值：先保留原始字符串，待 expr.evaluate 求值后
    # 再由 _coerce_json_strings 转回 array/object 原生类型
    if "${" in raw:
        return raw
    if field_type in ("array", "object"):
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            # 非合法 JSON 字符串，保留原值
            return raw
    if field_type == "int":
        try:
            return int(raw)
        except (ValueError, TypeError):
            # 无法转为整数，保留原值
            return raw
    if field_type == "bool":
        return raw.lower() in ("true", "1", "yes")
    return raw  # string 类型，保留表达式 ${...} 由后续 preprocessor 求值


def set_nested(target: Dict[str, Any], path: str, value: Any) -> None:
    """按点号路径设置嵌套 dict 值。"""
    keys = path.split(".")
    cur = target
    for k in keys[:-1]:
        if k not in cur or not isinstance(cur[k], dict):
            cur[k] = {}
        cur = cur[k]
    cur[keys[-1]] = value

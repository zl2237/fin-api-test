"""请求体类型强转服务：表达式求值后按字段定义还原/强转类型。

从 DagExecutor._coerce_json_strings / _apply_field_types / _infer_array_elem_type /
_coerce_scalar 提取，供 DagExecutor 执行链路与后续 OrderFlow 编排器复用，消除对
DagExecutor 私有方法的依赖。行为与原 DagExecutor 实现完全一致。

依赖 engine.preprocessor 的 get_nested_value / set_nested_value 进行嵌套取值/赋值，
故置于 engine 层（而非 services 层）。
"""
import json
from typing import Any, Optional

from .preprocessor import get_nested_value, set_nested_value


def coerce_json_strings(obj: Any) -> Any:
    """递归把求值后形如 JSON 的字符串转回原生类型。

    例如 array 字段 "[${id}]" 求值后为 "[123]" 字符串，转回 [123] 列表。
    仅对形如 [...] / {...} 的字符串尝试，失败则原样返回（留给 apply_field_types 兜底）。
    """
    if isinstance(obj, dict):
        return {k: coerce_json_strings(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [coerce_json_strings(v) for v in obj]
    if isinstance(obj, str):
        s = obj.strip()
        if (s.startswith("[") and s.endswith("]")) or (s.startswith("{") and s.endswith("}")):
            try:
                return json.loads(s)
            except (json.JSONDecodeError, TypeError):
                # 形似 JSON 但解析失败（如 "[abc]" 非法 JSON），保留原字符串，
                # 由 apply_field_types 依据字段类型兜底恢复为 list
                return obj
    return obj


def string_to_array(s: str) -> list:
    """把形如 "[a, b, c]" / "a, b, c" / "[a]" 的字符串按数组语义拆分为 list。

    用于表达式 [${bl_no}] 求值后得到 "[somestring]" 的兜底恢复：
    coerce_json_strings 仅能处理合法 JSON（如 "[123]" / '["abc"]'），
    对于 "[非引号字符串]" 会解析失败，此处按逗号拆分为字符串列表，
    后续由 apply_field_types 依据字段 elem_type 再做标量强转。
    """
    s = s.strip()
    if s.startswith("[") and s.endswith("]"):
        inner = s[1:-1].strip()
    else:
        inner = s
    if not inner:
        return []
    return [part.strip() for part in inner.split(",")]


def apply_field_types(body: Any, api) -> Any:
    """按 ApiField.field_type 强转标量值。

    解决表达式求值后类型丢失的问题：
    - 标量字段：${order_id} 从响应提取为 int，但字段定义为 string 时应转字符串
      （否则下游接口用字符串方式处理 order_id 时会出错，如 orderNotice 构造 IN() 集合失败）
    - array 字段：${xxx} 经 coerce_json_strings 后元素变 int，但字段定义是字符串数组时
      应转回字符串数组（如 order_fee_real_ids 期望 ["123"] 而非 [123]）
    object 字段不处理（结构复杂，保留求值后的原生类型）。
    数组请求体（body 为 list）时对首元素应用字段类型。
    """
    # 数组请求体：对第一个 dict 元素应用字段类型转换
    if isinstance(body, list):
        if body and isinstance(body[0], dict):
            body[0] = apply_field_types(body[0], api)
        return body

    fields = getattr(api, "fields", None) or []
    if not fields:
        return body
    for f in fields:
        if not f.key:
            continue
        val = get_nested_value(body, f.key)
        if val is None:
            continue
        if f.field_type == "array":
            # 从 default_value 推断元素类型，强转每个元素
            elem_type = infer_array_elem_type(f.default_value)
            # 兜底：表达式 [${bl_no}] 求值后得到 "[somestring]"，coerce_json_strings
            # 因非合法 JSON 无法转回 list。此处仅对 [...] 形式的字符串按数组语义恢复为 list；
            # 无括号的普通字符串（如误配的标量值）保持原样，避免误转
            if isinstance(val, str):
                s = val.strip()
                if s.startswith("[") and s.endswith("]"):
                    val = string_to_array(val)
            if not isinstance(val, list):
                continue
            if elem_type:
                new_list = []
                for v in val:
                    converted = coerce_scalar(v, elem_type)
                    new_list.append(converted if converted is not None else v)
                set_nested_value(body, f.key, new_list)
            else:
                # 无 elem_type 推断（如 default_value 为空数组），仍需把恢复的 list 写回
                set_nested_value(body, f.key, val)
            continue
        if f.field_type == "object":
            continue
        converted = coerce_scalar(val, f.field_type)
        if converted is not None:
            set_nested_value(body, f.key, converted)
    return body


def infer_array_elem_type(default_value: Optional[str]) -> Optional[str]:
    """从 array 字段的 default_value 推断元素标量类型。

    default_value 形如 '["343928144446619648"]' → string；
    '[1, 2, 3]' → int；'[true, false]' → bool。
    空数组 / 嵌套结构（元素为 dict/list）返回 None，表示不处理。
    """
    if not default_value:
        return None
    try:
        arr = json.loads(default_value)
    except (json.JSONDecodeError, TypeError):
        # 非合法 JSON 数组字符串，无法推断元素类型
        return None
    if not isinstance(arr, list) or not arr:
        return None
    first = arr[0]
    if isinstance(first, bool):
        return "bool"
    if isinstance(first, int):
        return "int"
    if isinstance(first, str):
        return "string"
    # 元素是 dict/list 等嵌套结构，不处理
    return None


def coerce_scalar(val: Any, field_type: str) -> Any:
    """按字段类型强转标量值，转换失败返回 None 表示不修改原值。"""
    if field_type == "string":
        if isinstance(val, str):
            return val
        # 布尔值转小写字符串（与 body_builder.parse_field_value 的处理保持一致）
        if isinstance(val, bool):
            return "true" if val else "false"
        return str(val)
    if field_type == "int":
        if isinstance(val, bool):
            return 1 if val else 0
        if isinstance(val, int):
            return val
        try:
            # 兼容 "123" / "123.0" / 123.0
            return int(float(val))
        except (ValueError, TypeError):
            return None
    if field_type == "bool":
        if isinstance(val, bool):
            return val
        if isinstance(val, str):
            return val.lower() in ("true", "1", "yes")
        return bool(val)
    return val

"""请求体构建服务：从接口字段定义组装请求体。

从 DagExecutor._build_request_body / _parse_field_value / _set_nested 提取，
供 DagExecutor 执行链路与接口调试（debug_api）复用，消除 debug_api 对
DagExecutor 实例的依赖（进而删除 _DummyCase 占位对象）。

行为与原 DagExecutor 实现完全一致：
- 优先用 ApiField 组装请求体（支持点号嵌套路径）
- 无 fields 时回退到 request_template（兼容旧数据）
- request_template 为 list 时标记数组请求体，组装结果包裹为 [{...}]
- file 类型字段值存 file_id（字符串），执行时由 dag_executor 转 multipart
"""
import json
from copy import deepcopy
from typing import Any


def build_request_body(api) -> Any:
    """按 api.fields 组装请求体；无 fields 时回退 request_template。"""
    fields = getattr(api, "fields", None) or []
    if not fields:
        return deepcopy(api.request_template if api.request_template is not None else {})

    # request_template 为 list 表示数组请求体（body 本身是 [{...}]）
    is_array_body = isinstance(api.request_template, list)

    body: dict[str, Any] = {}
    for f in fields:
        if not f.key:
            continue
        # 解析默认值：支持 JSON（array/object 类型）、表达式、纯字符串
        val = parse_field_value(f.default_value, f.field_type)
        # 按点号路径设置到嵌套 dict
        set_nested(body, f.key, val)
    return [body] if is_array_body else body


def parse_field_value(raw: str | None, field_type: str) -> Any:
    """解析字段默认值。

    - 空 → string 给空串，其他给 None
    - 含 ${} 表达式 → 保留原字符串，待表达式引擎求值后再由 _coerce_json_strings 还原类型
    - array/object → 尝试 JSON 解析，失败保留原值
    - int → 转整数，失败保留原值
    - bool → 按常见真值字符串判定
    - string → 保留原值（含 ${...} 表达式由后续 preprocessor 求值）
    - file → 原样保留（值是 file_id 字符串，由 extract_file_fields 提取）
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
    # file / string 类型，保留原值
    return raw


def set_nested(target: dict[str, Any], path: str, value: Any) -> None:
    """按点号路径设置嵌套 dict 值。"""
    keys = path.split(".")
    cur = target
    for k in keys[:-1]:
        if k not in cur or not isinstance(cur[k], dict):
            cur[k] = {}
        cur = cur[k]
    cur[keys[-1]] = value


def apply_row_overrides(body: Any, row_vars: dict[str, Any] | None) -> Any:
    """数据驱动（优先级 1）：行值覆盖请求体中同名的顶层字段。

    请求体参数三级取值优先级（引擎定案）：
    1. 数据集行值（本函数）：覆盖除动态绑定外的所有字段
    2. 用例编排（pre_process set_field 字面量，见 PreProcessor）
    3. 接口字段默认值（build_request_body 组装的兜底值）

    - 只覆盖请求中已存在的字段（不新增参数）；数组请求体作用于首元素（与前置处理数组语义一致）
    - 字段值为 ${}（动态绑定）不覆盖：动态注入字段不在数据集覆盖范围，交给表达式引擎
    - 行值为空（None/""，单元格未配置）不覆盖：未配置 = 让位下一优先级
    - 覆盖发生在表达式求值之前：行值若含 ${} 表达式同样会被求值
    - 嵌套路径字段（如 to_customer.xxx）列名无法含点号：整对象列覆盖或 ${列名} 表达式注入
    """
    if not row_vars:
        return body
    target = body[0] if isinstance(body, list) and body and isinstance(body[0], dict) else body
    if isinstance(target, dict):
        for k, v in row_vars.items():
            if v is None or v == "":
                continue
            if k in target and not (isinstance(target[k], str) and "${" in target[k]):
                target[k] = v
    return body


def extract_file_fields(api) -> list[tuple[str, str]]:
    """提取接口中 file 类型字段的 (path, file_id) 列表。

    返回值供 dag_executor 构建 multipart files 参数：
    - path：字段路径（如 'id_card' 或 'to_customer.id_card'），作为 multipart 字段名
    - file_id：文件中心文件 ID（字符串），用于查询物理文件
    """
    fields = getattr(api, "fields", None) or []
    result: list[tuple[str, str]] = []
    for f in fields:
        if not f.key or f.field_type != "file":
            continue
        val = (f.default_value or "").strip()
        if not val or "${" in val:
            # 空值或表达式（file 类型暂不支持表达式注入）跳过
            continue
        result.append((f.key, val))
    return result


def pop_file_fields_from_body(body: Any, api) -> tuple[Any, list[tuple[str, str]]]:
    """从请求体中剔除 file 类型字段，返回 (剩余body, file字段列表)。

    file 字段不参与 JSON body，由 dag_executor 单独组装到 multipart files 参数。
    支持点号嵌套路径（如 to_customer.id_card）。
    """
    fields = getattr(api, "fields", None) or []
    file_keys = {f.key for f in fields if f.field_type == "file"}
    if not file_keys:
        return body, []

    file_list: list[tuple[str, str]] = []

    def _pop_from_dict(d: dict[str, Any], prefix: str = "") -> None:
        for k in list(d.keys()):
            full_path = f"{prefix}.{k}" if prefix else k
            if full_path in file_keys:
                val = d.pop(k, None)
                if val is not None and str(val).strip():
                    file_list.append((full_path, str(val).strip()))
            elif isinstance(d.get(k), dict):
                _pop_from_dict(d[k], full_path)

    if isinstance(body, dict):
        _pop_from_dict(body)
    elif isinstance(body, list):
        for item in body:
            if isinstance(item, dict):
                _pop_from_dict(item)
    return body, file_list

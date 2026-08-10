"""接口定义解析服务：从 Swagger/OpenAPI/HAR 提取字段、生成接口编码。

从 routers/apis.py 提取，消除路由层过载。被 apis.py 和 har_parser.py 共用。
"""
import json
from typing import Any

from .. import schemas


def path_to_code(path: str, method: str) -> str:
    """路径转接口编码：/api/order/create -> order_create_post

    取最后两段路径拼接，附加 method 后缀。跳过 {param} 形式的路径参数段。
    """
    parts = [p for p in path.strip("/").split("/") if p and not p.startswith("{")]
    if len(parts) >= 2:
        code = "_".join(parts[-2:])
    elif parts:
        code = parts[-1]
    else:
        code = "api"
    return f"{code}_{method.lower()}"


def resolve_ref(ref: str, spec: dict) -> dict:
    """解析 $ref 引用，支持 #/components/schemas、#/components/parameters、#/definitions"""
    if not ref:
        return {}
    parts = ref.lstrip("#/").split("/")
    cur: Any = spec
    for p in parts:
        if p in ("components", "schemas", "parameters", "definitions"):
            cur = cur.get(p, {}) if isinstance(cur, dict) else {}
            continue
        cur = cur.get(p, {}) if isinstance(cur, dict) else {}
    return cur if isinstance(cur, dict) else {}


def swagger_type_to_field_type(swagger_type: str) -> str:
    """Swagger type 映射到平台 field_type"""
    mapping = {
        "string": "string",
        "integer": "int",
        "number": "string",
        "boolean": "bool",
        "array": "array",
        "object": "object",
    }
    return mapping.get(swagger_type, "string")


def pick_default_value(node: dict) -> Any:
    """从 OpenAPI schema/parameter 节点按优先级提取默认值：
    default > example(单数) > examples(复数,取第一个value) > enum[0] > ""
    覆盖 OpenAPI 3.0 的多种示例写法。
    """
    if not isinstance(node, dict):
        return ""
    val = node.get("default")
    if val is not None:
        return val
    val = node.get("example")
    if val is not None:
        return val
    # OpenAPI 3.0 examples（复数）：{"examples": {"foo": {"value": ...}}}
    examples = node.get("examples")
    if isinstance(examples, dict) and examples:
        first = next(iter(examples.values()))
        if isinstance(first, dict) and "value" in first:
            return first["value"]
        if first is not None:
            return first
    # 枚举类型取第一个值作为示例
    enum_vals = node.get("enum")
    if isinstance(enum_vals, list) and enum_vals:
        return enum_vals[0]
    return ""


def coerce_default(default_value: Any, field_type: str) -> str:
    """将默认值统一为字符串；array/object 用 JSON 序列化"""
    if default_value == "" or default_value is None:
        return ""
    if field_type in ("array", "object") and not isinstance(default_value, str):
        return json.dumps(default_value, ensure_ascii=False)
    return str(default_value)


def extract_fields_from_spec(info: dict, spec: dict, is_v3: bool) -> tuple:
    """从 OpenAPI/Swagger 操作定义中提取字段：
    1. parameters（query/path/cookie/formData，跳过 header）→ 有默认值才导入
    2. requestBody body schema 的 properties → 有默认值才导入
    默认值来源优先级：
      property 自身: default > example(单数) > examples(复数) > enum[0]
      body 字段额外回退: schema 顶层 example（完整请求体示例对象）中对应 key 的值
    无默认值（空字符串/None）的字段不导入。
    返回 (fields, is_array_body)：is_array_body 标记请求体本身是否为数组类型。
    """
    fields: list = []
    sort_order = 0
    seen_keys: set = set()
    is_array_body = False

    # ---- 1. 提取 parameters（query/path/cookie/formData，跳过 header）----
    for param in info.get("parameters", []) or []:
        if not isinstance(param, dict):
            continue
        # v3: parameter 可能 $ref 引用 #/components/parameters/{name}
        if "$ref" in param:
            param = resolve_ref(param["$ref"], spec)
            if not param:
                continue
        loc = param.get("in", "query")
        # 跳过 header 参数（由环境配置/headers_template 管理，不作为业务字段导入）
        if loc == "header":
            continue
        name = param.get("name")
        if not name or name in seen_keys:
            continue
        # schema 来源：v3 在 param.schema（可能 $ref），v2 直接平铺在 param 上
        if is_v3:
            pschema = param.get("schema", {}) or {}
            if "$ref" in pschema:
                pschema = resolve_ref(pschema["$ref"], spec)
            swagger_type = pschema.get("type", "string")
            # 默认值：优先 parameter 顶层 example/examples，再回退 schema
            default_value = pick_default_value(param)
            if default_value == "":
                default_value = pick_default_value(pschema)
        else:
            # Swagger 2.0: type/default/example 直接在 param 上
            swagger_type = param.get("type", "string")
            default_value = pick_default_value(param)
        field_type = swagger_type_to_field_type(swagger_type)
        coerced = coerce_default(default_value, field_type)
        # 只导入有默认值的参数
        if not coerced:
            continue
        description = param.get("description", "") or ""
        fields.append(schemas.ApiFieldIn(
            key=name,
            label=description or param.get("title", ""),
            field_type=field_type,
            required=bool(param.get("required", False)),
            default_value=coerced,
            remark=f"{loc}参数" + (f"：{description}" if description else ""),
            sort_order=sort_order,
        ))
        seen_keys.add(name)
        sort_order += 1

    # ---- 2. 提取 requestBody body 字段 ----
    schema = None
    json_content = None
    if is_v3:
        request_body = info.get("requestBody", {}) or {}
        content = request_body.get("content", {}) or {}
        # 优先 application/json，回退第一个 media type
        json_content = content.get("application/json")
        if not json_content:
            for _mc in content.values():
                json_content = _mc
                break
        if json_content:
            schema = json_content.get("schema", {}) or {}
    else:
        for param in info.get("parameters", []) or []:
            if isinstance(param, dict) and param.get("in") == "body":
                schema = param.get("schema", {}) or {}
                break

    if schema:
        if "$ref" in schema:
            schema = resolve_ref(schema["$ref"], spec)
        # body 本身是数组时（type=array），字段定义在 items.properties 中
        # 例如：POST /api/finance/receiveInvoice/invoiceAdd 的 body 是 [{...}]
        if schema.get("type") == "array" and "items" in schema:
            is_array_body = True
            items = schema["items"]
            if "$ref" in items:
                items = resolve_ref(items["$ref"], spec)
            schema = items
        properties = schema.get("properties", {}) or {}
        required_keys = set(schema.get("required", []) or [])
        # schema 顶层 example（完整请求体示例对象）作为字段默认值回退源
        # body 是数组时，example 也可能是数组，取第一个元素作为回退源
        schema_example = schema.get("example")
        if not isinstance(schema_example, dict):
            schema_example = {}
        # v3 media type 级别的 example 也作为回退源，同样处理数组情况
        media_example = json_content.get("example") if json_content else None
        if isinstance(media_example, list) and media_example:
            media_example = media_example[0] if isinstance(media_example[0], dict) else {}
        elif not isinstance(media_example, dict):
            media_example = {}
        for key, prop in properties.items():
            if key in seen_keys:
                continue
            if "$ref" in prop:
                prop = resolve_ref(prop["$ref"], spec)
            field_type = swagger_type_to_field_type(prop.get("type", "string"))
            # 默认值：property 自身 > schema 顶层 example[key] > media type example[key]
            default_value = pick_default_value(prop)
            if default_value == "" and key in schema_example:
                default_value = schema_example[key]
            if default_value == "" and key in media_example:
                default_value = media_example[key]
            coerced = coerce_default(default_value, field_type)
            # body 字段是请求体核心结构，无论是否有默认值都导入（默认值可空）；
            # query/path 等参数才适用"有默认值才导入"规则
            description = prop.get("description", "") or prop.get("title", "") or ""
            fields.append(schemas.ApiFieldIn(
                key=key,
                label=description,
                field_type=field_type,
                required=key in required_keys,
                default_value=coerced,
                remark=prop.get("description", ""),
                sort_order=sort_order,
            ))
            seen_keys.add(key)
            sort_order += 1

    return fields, is_array_body

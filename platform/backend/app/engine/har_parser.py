"""
HAR 文件解析器：将 HAR (HTTP Archive) 转换为平台可识别的接口预览结构。

HAR 1.2 规范核心结构：
    log.entries[].request = {
        method: "POST",
        url: "http://host/api/order/create",
        queryString: [{name, value}, ...],
        postData: { mimeType: "application/json", text: '{"key":"value"}' },
        headers: [{name, value}, ...]
    }

解析策略：
    1. 从 url 提取 path（去掉 protocol://host 部分）
    2. 从 postData.text 解析 JSON 请求体（仅处理 application/json）
    3. 请求体字段全部作为 body 字段导入（带实际值作为默认值）
    4. query 参数有值才导入
    5. 跳过静态资源请求（.js/.css/.png 等）
"""
import json
from typing import Any, Dict, List
from urllib.parse import urlparse

from .. import schemas


# 静态资源后缀，导入时跳过
_STATIC_EXTENSIONS = {
    ".js", ".css", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico",
    ".woff", ".woff2", ".ttf", ".eot", ".map", ".html", ".htm",
}

# 非业务 HTTP 方法，跳过
_SKIP_METHODS = {"OPTIONS", "HEAD", "CONNECT", "TRACE"}


def _is_static_resource(path: str) -> bool:
    """判断是否为静态资源请求（按路径后缀）"""
    path_lower = path.lower().split("?")[0]
    return any(path_lower.endswith(ext) for ext in _STATIC_EXTENSIONS)


def _extract_path(url: str) -> str:
    """从完整 URL 提取 path 部分：http://host/api/order/create → /api/order/create"""
    parsed = urlparse(url)
    path = parsed.path or "/"
    # 保留 query string 作为 path 的一部分？不，query 参数单独处理
    return path if path.startswith("/") else "/" + path


def _infer_field_type(value: Any) -> str:
    """根据 Python 值推断字段类型"""
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "string"  # 金额等用 string 避免精度问题
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "string"


def _coerce_default_value(value: Any, field_type: str) -> str:
    """将默认值统一为字符串；array/object 用 JSON 序列化"""
    if value is None:
        return ""
    if field_type in ("array", "object"):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def parse_har_to_previews(har_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """解析 HAR JSON，返回接口预览列表。

    每个预览项结构：
        {
            "method": "POST",
            "path": "/api/order/create",
            "url": "http://host/api/order/create",  # 完整 URL，便于用户识别
            "name": "/api/order/create",            # 接口名（默认用 path，前端可编辑）
            "field_count": 5,                        # 字段数
            "fields": [                              # 已解析的字段列表
                {"key": "bl_no", "field_type": "string", "default_value": "BL001", "in": "body"},
                ...
            ],
            "is_array_body": False,                  # 请求体是否为数组
            "content_type": "application/json",      # 请求体类型
        }

    过滤规则：
        - 跳过静态资源（.js/.css/.png 等）
        - 跳过非业务方法（OPTIONS/HEAD 等）
        - 同 method+path 去重（保留第一次出现）
    """
    entries = har_data.get("log", {}).get("entries", [])
    if not isinstance(entries, list):
        return []

    previews: List[Dict[str, Any]] = []
    seen: set = set()  # (method, path) 去重

    for entry in entries:
        if not isinstance(entry, dict):
            continue
        request = entry.get("request", {})
        if not isinstance(request, dict):
            continue

        method = (request.get("method") or "GET").upper()
        if method in _SKIP_METHODS:
            continue

        url = request.get("url", "")
        if not url:
            continue
        path = _extract_path(url)

        # 跳过静态资源
        if _is_static_resource(path):
            continue

        # 去重
        dedup_key = (method, path)
        if dedup_key in seen:
            continue
        seen.add(dedup_key)

        # 解析字段
        fields, is_array_body, content_type = _parse_request_fields(request)

        previews.append({
            "method": method,
            "path": path,
            "url": url,
            "name": path,  # 默认用 path 作为名称，前端可编辑
            "field_count": len(fields),
            "fields": fields,
            "is_array_body": is_array_body,
            "content_type": content_type,
        })

    return previews


def _parse_request_fields(request: Dict[str, Any]) -> tuple:
    """解析单个 HAR request 的字段。

    返回 (fields, is_array_body, content_type)
    fields 是 ApiFieldIn 兼容的 dict 列表（含 key/field_type/default_value/in）。
    """
    fields: List[Dict[str, Any]] = []
    seen_keys: set = set()
    is_array_body = False
    content_type = ""

    # ---- 1. query 参数 ----
    for qs in request.get("queryString", []) or []:
        if not isinstance(qs, dict):
            continue
        name = qs.get("name")
        if not name or name in seen_keys:
            continue
        value = qs.get("value", "")
        fields.append({
            "key": name,
            "field_type": "string",
            "default_value": str(value),
            "in": "query",
            "required": False,
        })
        seen_keys.add(name)

    # ---- 2. 请求体字段 ----
    post_data = request.get("postData", {})
    if isinstance(post_data, dict):
        content_type = post_data.get("mimeType", "")
        text = post_data.get("text", "")

        # 仅处理 JSON 请求体
        if text and "json" in content_type.lower():
            try:
                body = json.loads(text)
            except (json.JSONDecodeError, ValueError):
                body = None

            if body is not None:
                # 数组请求体：body 是 [{...}]，取第一个元素的字段
                if isinstance(body, list) and body:
                    is_array_body = True
                    first_item = body[0] if isinstance(body[0], dict) else {}
                    _extract_body_fields(first_item, fields, seen_keys)
                elif isinstance(body, dict):
                    _extract_body_fields(body, fields, seen_keys)

    return fields, is_array_body, content_type


def _extract_body_fields(body: Dict[str, Any], fields: List[Dict[str, Any]], seen_keys: set):
    """从请求体 dict 提取顶层字段"""
    for key, value in body.items():
        if key in seen_keys:
            continue
        field_type = _infer_field_type(value)
        default_value = _coerce_default_value(value, field_type)
        fields.append({
            "key": key,
            "field_type": field_type,
            "default_value": default_value,
            "in": "body",
            "required": False,
        })
        seen_keys.add(key)


def previews_to_api_create(
    previews: List[Dict[str, Any]],
    project_id: int,
    group_id: int | None,
    existing_codes: set,
) -> tuple:
    """将用户勾选的预览项转换为 ApiCreate 列表。

    返回 (to_create, skipped)
    to_create: [(api_data, preview) ...] 待创建的接口数据
    skipped: [原因字符串 ...] 跳过的接口及原因
    """
    to_create = []
    skipped = []

    for preview in previews:
        method = preview["method"]
        path = preview["path"]
        code = _path_to_code(path, method)

        if code in existing_codes:
            skipped.append(f"{method} {path}（编码 {code} 已存在）")
            continue

        # 转换字段格式
        api_fields = []
        for idx, f in enumerate(preview.get("fields", [])):
            api_fields.append(schemas.ApiFieldIn(
                key=f["key"],
                label="",
                field_type=f.get("field_type", "string"),
                required=f.get("required", False),
                default_value=f.get("default_value", ""),
                remark=f.get("in", "body") + "参数",
                sort_order=idx,
            ))

        api_data = schemas.ApiCreate(
            project_id=project_id,
            group_id=group_id,
            name=preview.get("name") or path,
            code=code,
            method=method,
            path=path,
            description="",
            request_template=[] if preview.get("is_array_body") else {},
            headers_template={},
            fields=api_fields,
        )
        to_create.append((api_data, preview))

    return to_create, skipped


def _path_to_code(path: str, method: str) -> str:
    """路径转接口编码：/api/order/create -> order_create_post"""
    parts = [p for p in path.strip("/").split("/") if p and not p.startswith("{")]
    if len(parts) >= 2:
        code = "_".join(parts[-2:])
    elif parts:
        code = parts[-1]
    else:
        code = "api"
    return f"{code}_{method.lower()}"

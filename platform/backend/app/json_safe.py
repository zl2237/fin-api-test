"""JSON 序列化工具：处理 JS 大整数精度丢失。

雪花算法 ID（如 343557272766513152）超出 JS Number.MAX_SAFE_INTEGER (2^53-1)，
前端 JSON.parse 会截断末几位（152 → 150）。本模块提供：
- sanitize_bigints: 递归把 dict/list 中的大 int 转为 str
- BigintSafeJSONResponse: 自定义 JSONResponse，序列化前预处理大整数
"""
import json
import math
from typing import Any

from fastapi.responses import JSONResponse

# JS Number.MAX_SAFE_INTEGER = 2^53 - 1 = 9007199254740991
JS_MAX_SAFE_INT = 9007199254740991
JS_MIN_SAFE_INT = -9007199254740991


def _is_big_int(v: Any) -> bool:
    """判断是否为超出 JS 安全整数范围的 int（排除 bool）"""
    if isinstance(v, bool):
        return False
    if isinstance(v, int):
        return v > JS_MAX_SAFE_INT or v < JS_MIN_SAFE_INT
    if isinstance(v, float) and math.isfinite(v) and v.is_integer():
        iv = int(v)
        return iv > JS_MAX_SAFE_INT or iv < JS_MIN_SAFE_INT
    return False


def sanitize_bigints(obj: Any) -> Any:
    """递归把 dict/list 中超出 JS 安全范围的大整数转为字符串。

    用于在返回响应前预处理 request_body / response_body 等 JSON 字段，
    保证前端 JSON.parse 不丢精度。返回处理后的新对象（不修改原始对象）。
    """
    if isinstance(obj, dict):
        return {k: sanitize_bigints(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitize_bigints(v) for v in obj]
    if _is_big_int(obj):
        return str(obj)
    return obj


class BigintSafeJSONResponse(JSONResponse):
    """自定义 JSONResponse：序列化前把大整数转为字符串，避免前端精度丢失。

    用法：FastAPI(default_response_class=BigintSafeJSONResponse)
    或在路由级 response_class=BigintSafeJSONResponse
    """
    def render(self, content: Any) -> bytes:
        return json.dumps(
            sanitize_bigints(content),
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")

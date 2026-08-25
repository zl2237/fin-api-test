"""cURL 命令解析器：将一条或多条 cURL 命令转换为平台可识别的接口预览结构。

复用 HAR 的预览结构（HarPreviewItem），使后续落库链路（previews_to_api_create）完全一致。

支持的 cURL 语法：
    curl -X POST 'http://host/api/order/create' \\
          -H 'Content-Type: application/json' \\
          -H 'Authorization: Bearer xxx' \\
          -d '{"bl_no":"BL001","amount":100}'

    curl 'http://host/api/list?page=1&size=10'

解析策略：
    1. 用 shlex 按 shell 词法拆分，正确处理单/双引号、续行符（\\n）
    2. 提取 URL → path（去掉 protocol://host）
    3. -X / --request 指定方法，缺省按 -d 有无推断 POST/GET
    4. -H / --header 解析请求头（仅用于识别 Content-Type，不导入 header 字段）
    5. -d / --data / --data-raw / --data-binary 解析请求体（仅 application/json）
    6. query 参数从 URL 解析，有值才导入
    7. 请求体字段全部作为 body 字段导入（带实际值作为默认值）

多条 cURL 命令以空行分隔；也可一行一条。解析失败的命令跳过并记录错误。
"""
import json
import re
import shlex
from typing import Any
from urllib.parse import parse_qs, urlparse

# cURL 数据参数，命中其一即认为该 token 后跟请求体
_DATA_FLAGS = {"-d", "--data", "--data-raw", "--data-binary", "--data-ascii"}


def _preprocess_ansi_c_quoting(text: str) -> str:
    """预处理 bash 的 $'...' ANSI-C quoting 语法。

    shlex 不支持 $'...'，会把 $ 当普通字符拼到后面，导致 body 变成 ${...} 无法 json.loads。
    处理方式：把 $'...' 转成普通 '...'（去掉 $ 前缀）。
    内部的 \\u0021 / \\n / \\t 等转义序列原样保留，后续 json.loads 能正确解析。
    """
    return re.sub(r"\$'", "'", text)

# 非业务 HTTP 方法，跳过
_SKIP_METHODS = {"OPTIONS", "HEAD", "CONNECT", "TRACE"}


def _split_curl_commands(text: str) -> list[str]:
    """把用户粘贴的文本拆分为多条 cURL 命令。

    规则：
    1. 以"curl "开头的行作为新命令起点
    2. 续行符（行尾 \\）连接到下一条
    3. 空行作为命令分隔
    """
    # 统一换行符
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # 把续行符（\ 后跟换行）替换为空格，先合并物理行
    text = re.sub(r"\\\n", " ", text)
    lines = text.split("\n")

    commands: list[str] = []
    current: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            # 空行：结束当前命令
            if current:
                commands.append(" ".join(current))
                current = []
            continue
        # 以 curl 开头（忽略前导空白）且当前已有命令积累 → 新命令起点
        if stripped.lower().startswith("curl ") and current:
            commands.append(" ".join(current))
            current = [stripped]
        elif stripped.lower().startswith("curl "):
            current = [stripped]
        else:
            if current:
                current.append(stripped)
            # 非 curl 开头且无积累 → 忽略（注释/说明文字）
    if current:
        commands.append(" ".join(current))
    return commands


def _parse_single_curl(cmd: str) -> tuple[dict[str, Any] | None, str | None]:
    """解析单条 cURL 命令为预览项。

    返回 (preview, error_msg)。解析失败时 preview=None。
    """
    try:
        tokens = shlex.split(_preprocess_ansi_c_quoting(cmd), posix=True)
    except ValueError as e:
        return None, f"词法解析失败：{e}"

    if not tokens or tokens[0].lower() != "curl":
        return None, "非 cURL 命令（不以 curl 开头）"

    method = ""
    url = ""
    headers: dict[str, str] = {}
    body_text = ""

    i = 1
    while i < len(tokens):
        tok = tokens[i]

        if tok in ("-X", "--request"):
            if i + 1 < len(tokens):
                method = tokens[i + 1].upper()
                i += 2
                continue
        elif tok in ("--url",):
            # --url 'https://...' 显式指定 URL
            if i + 1 < len(tokens):
                url = tokens[i + 1]
                i += 2
                continue
        elif tok in ("-H", "--header"):
            if i + 1 < len(tokens):
                header_val = tokens[i + 1]
                # Header 形如 "Content-Type: application/json"
                if ":" in header_val:
                    k, v = header_val.split(":", 1)
                    headers[k.strip()] = v.strip()
                i += 2
                continue
        elif tok in _DATA_FLAGS:
            if i + 1 < len(tokens):
                body_text = tokens[i + 1]
                i += 2
                continue
        elif tok in ("--compressed", "-k", "--insecure", "-L", "--location", "-v", "--verbose", "-s", "--silent"):
            # 常见无参数标志，跳过
            i += 1
            continue
        elif tok.startswith("-"):
            # 未知参数，尝试跳过其后的值（如果是 -Xxx=value 形式则单 token）
            if "=" in tok:
                i += 1
            elif i + 1 < len(tokens) and not tokens[i + 1].startswith("-") and not _looks_like_url(tokens[i + 1]):
                i += 2
            else:
                i += 1
            continue
        else:
            # 非 flag token → 视为 URL（取第一个）
            if not url and _looks_like_url(tok):
                url = tok

        i += 1

    if not url:
        return None, "未识别到 URL"

    # 方法缺省推断：有 body 默认 POST，否则 GET
    if not method:
        method = "POST" if body_text else "GET"

    if method in _SKIP_METHODS:
        return None, f"跳过非业务方法 {method}"

    # 解析 URL
    parsed = urlparse(url)
    path = parsed.path or "/"
    if not path.startswith("/"):
        path = "/" + path

    # query 参数
    fields: list[dict[str, Any]] = []
    seen_keys: set = set()
    if parsed.query:
        for name, values in parse_qs(parsed.query, keep_blank_values=True).items():
            if name in seen_keys:
                continue
            # parse_qs 返回 list，取第一个值
            value = values[0] if values else ""
            fields.append({
                "key": name,
                "field_type": "string",
                "default_value": str(value),
                "in": "query",
                "required": False,
            })
            seen_keys.add(name)

    # 请求体字段
    is_array_body = False
    content_type = ""
    for hk, hv in headers.items():
        if hk.lower() == "content-type":
            content_type = hv
            break
    # 无 Content-Type 头但有 body，默认尝试按 JSON 解析
    if body_text:
        if "json" in content_type.lower() or not content_type:
            try:
                body = json.loads(body_text)
                if isinstance(body, list) and body:
                    is_array_body = True
                    first_item = body[0] if isinstance(body[0], dict) else {}
                    _extract_body_fields(first_item, fields, seen_keys)
                elif isinstance(body, dict):
                    _extract_body_fields(body, fields, seen_keys)
                # 解析成功后补全 content_type
                if not content_type:
                    content_type = "application/json"
            except (json.JSONDecodeError, ValueError):
                # 非 JSON body（如 form-urlencoded），不提取字段
                if not content_type:
                    content_type = "text/plain"

    preview = {
        "method": method,
        "path": path,
        "url": url,
        "name": path,
        "field_count": len(fields),
        "fields": fields,
        "is_array_body": is_array_body,
        "content_type": content_type,
    }
    return preview, None


def _looks_like_url(token: str) -> bool:
    """判断 token 是否像 URL（http(s):// 或以 / 开头的路径）"""
    return token.startswith("http://") or token.startswith("https://") or token.startswith("/")


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


def _extract_body_fields(body: dict[str, Any], fields: list[dict[str, Any]], seen_keys: set):
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


def parse_curl_to_previews(text: str) -> tuple[list[dict[str, Any]], list[str]]:
    """解析多条 cURL 命令文本，返回 (预览列表, 错误列表)。

    预览项结构与 HAR 完全一致，可复用 previews_to_api_create 落库。
    同 method+path 去重（保留第一次）。
    """
    commands = _split_curl_commands(text)
    previews: list[dict[str, Any]] = []
    errors: list[str] = []
    seen: set = set()

    for idx, cmd in enumerate(commands, 1):
        if not cmd.strip():
            continue
        preview, err = _parse_single_curl(cmd)
        if err:
            errors.append(f"第 {idx} 条：{err}")
            continue
        if preview is None:
            continue
        dedup_key = (preview["method"], preview["path"])
        if dedup_key in seen:
            errors.append(f"第 {idx} 条：{preview['method']} {preview['path']} 重复，已跳过")
            continue
        seen.add(dedup_key)
        previews.append(preview)

    return previews, errors


def preview_to_fields_for_override(preview: dict[str, Any]) -> list[dict[str, Any]]:
    """供 ApiEdit 覆盖字段场景使用：从单个预览项提取字段列表。

    与 HAR 覆盖字段的前端逻辑保持一致：返回原始字段 dict 列表，
    由前端转换为 ApiField[] 展示对比。
    """
    return preview.get("fields", [])


# 复用 har_parser.previews_to_api_create，避免重复落库逻辑
from .har_parser import previews_to_api_create  # noqa: F401

"""共享请求发送器：单接口一次 HTTP 请求的完整通道。

此前同一逻辑存在两份平行实现（engine/dag_executor._send_request 与
routers/apis.debug_api 内联），本模块归一为单一事实来源：
- GET/POST 分发；含 file 字段时走 multipart（Content-Type 剥离/恢复、form_data 组装）
- 异常四分类：HttpStatusError(status) / BusinessError(200+业务码)
  / Auth|Timeout|JsonParse(0) / 其他(0)
- multipart 文件句柄用后关闭

调用方：DagExecutor._send_request（执行主链路）、apis.debug_api（单接口调试）。
"""
from typing import Any

import json

from utils.exceptions import (
    AuthError,
    BusinessError,
    HttpStatusError,
    HttpTimeoutError,
    JsonParseError,
)

from .. import (
    models,
    path_setup,  # noqa: F401  确保 utils 可导入（sys.path 指向本仓根）
)
from ..services.file_helpers import resolve_physical_path


def build_multipart_files(db, file_fields: list[tuple[str, str]]) -> list:
    """将 file_id 列表转为 requests 的 files 参数格式。

    返回 [(field_name, (filename, fileobj, content_type)), ...]
    文件不存在或读取失败的字段跳过并打印日志。
    """
    files_payload: list = []
    for field_name, file_id_str in file_fields:
        try:
            file_id = int(file_id_str)
        except (ValueError, TypeError):
            print(f"[文件上传] file_id 非法: {file_id_str}，跳过")
            continue
        f = db.query(models.TestFile).filter(models.TestFile.id == file_id).first()
        if not f:
            print(f"[文件上传] file_id={file_id} 不存在，跳过")
            continue
        physical = resolve_physical_path(f.storage_path)
        if not physical.exists():
            print(f"[文件上传] 物理文件丢失: {f.storage_path}，跳过")
            continue
        fileobj = open(physical, "rb")
        files_payload.append((field_name, (f.name, fileobj, f.content_type)))
    return files_payload


def close_multipart_files(files_payload: list) -> None:
    """关闭 multipart 请求中打开的文件句柄"""
    for item in files_payload:
        try:
            fileobj = item[1][1] if isinstance(item[1], tuple) else None
            if fileobj:
                fileobj.close()
        except Exception:
            pass


def _is_form_urlencoded(headers: dict) -> bool:
    """headers 声明 Content-Type 为 x-www-form-urlencoded（curl 导入的表单接口）"""
    ct = (headers or {}).get("Content-Type") or (headers or {}).get("content-type") or ""
    return "x-www-form-urlencoded" in ct.lower()


def send_request(db, client, api, body: Any,
                 file_fields: list[tuple[str, str]] | None = None,
                 timeout: int = 15,
                 headers: dict | None = None) -> tuple[int, Any, str | None]:
    """发送一次接口请求。返回 (status_code, response_body, error_msg)。

    :param file_fields: file 类型字段列表 [(field_name, file_id), ...]
                        非空时构建 multipart 请求，文件从文件中心按 file_id 取
    :param headers: 本次请求的 headers（prepare_request 组装产物：环境公共头 +
                    接口 headers_template 覆盖 + ${} 求值）。None 用 client.headers。
                    发送期间临时替换 client.headers，结束恢复（不污染登录态等会话头）
    """
    files_payload: list = []
    saved_client_headers = client.headers if headers is not None else None
    if headers is not None:
        client.headers = headers
    try:
        if api.method.upper() == "GET":
            # 数组请求体（is_array_body）取首元素作 query 参数，
            # 避免整个 list 传给 requests.params 触发 k-v 解包异常
            params = body
            if isinstance(body, list) and body and isinstance(body[0], dict):
                params = body[0]
            resp = client.get(api.path, params=params, timeout=timeout)
        elif file_fields:
            # 含文件字段：构建 multipart/form-data
            files_payload = build_multipart_files(db, file_fields)
            if files_payload:
                # multipart 请求去掉 Content-Type，让 requests 自动生成 boundary
                saved_headers = client.headers
                multipart_headers = {k: v for k, v in saved_headers.items()
                                     if k.lower() != "content-type"}
                client.headers = multipart_headers
                # multipart form_data：dict 直接用，list（数组请求体）取首元素
                if isinstance(body, dict):
                    form_data = body
                elif isinstance(body, list) and body and isinstance(body[0], dict):
                    form_data = body[0]
                else:
                    form_data = None
                try:
                    resp = client.post_multipart(
                        api.path, data=form_data, files=files_payload, timeout=timeout
                    )
                finally:
                    client.headers = saved_headers
            elif _is_form_urlencoded(client.headers):
                # 无有效文件可发 + 表单接口：按声明编码发送（与下方 POST 主分支同口径）
                form_data = body[0] if isinstance(body, list) and body and isinstance(body[0], dict) else body
                resp = client.post_form(api.path, data=form_data, timeout=timeout)
            else:
                resp = client.post(api.path, json=body, timeout=timeout)
        elif _is_form_urlencoded(client.headers):
            # 表单接口（curl 导入声明 x-www-form-urlencoded）：必须用表单编码发送。
            # 此前统一走 json= 且 headers 已声明 form 时 requests 不会改写 Content-Type，
            # 形成「form 声明 + JSON 文本」的错配请求，服务端按表单解析取不到任何字段
            # （如 precheckSyncFiles.html 的 order_no）。数组请求体取首元素（与 GET/multipart 同口径）
            form_data = body[0] if isinstance(body, list) and body and isinstance(body[0], dict) else body
            resp = client.post_form(api.path, data=form_data, timeout=timeout)
        else:
            resp = client.post(api.path, json=body, timeout=timeout)
        # HttpClient 成功返回即 HTTP 200 且业务码 200
        return 200, resp, None
    except HttpStatusError as e:
        return e.status_code, {"error": str(e)}, str(e)
    except BusinessError as e:
        # HTTP 200 但业务码非 200（平台约定 {code:200}）：响应体仍是真实数据
        # （如 ThinkPHP 系统成功响应 code:null），原样返回供调试展示与断言取值；
        # error 保留业务码差异说明，通过与否仍由断言判定。
        # 优先取已解析的 resp_json（resp_text 超 2000 字符会被截断致解析失败）
        body = e.resp_json if isinstance(e.resp_json, dict) else None
        if body is None:
            try:
                body = json.loads(e.resp_text) if e.resp_text else None
            except Exception:
                body = None
        if not isinstance(body, dict):
            body = {"text": (e.resp_text or "")[:2000]}
        return 200, body, str(e)
    except JsonParseError as e:
        # HTTP 200 已收到，仅响应体非 JSON（HTML/纯文本等）：请求本身未失败，
        # 状态码保留 200，原文放 text 字段，通过与否交给断言判定
        return 200, {"text": e.resp_text[:2000]}, None
    except (AuthError, HttpTimeoutError) as e:
        return 0, {"error": str(e)}, str(e)
    except Exception as e:
        # 未预期的请求异常（如连接错误、SSL 错误等），记录日志便于排查
        print(f"[请求异常] {api.method} {api.path} 未预期异常: {e}")
        return 0, {"error": str(e)}, str(e)
    finally:
        if files_payload:
            close_multipart_files(files_payload)
        if saved_client_headers is not None:
            client.headers = saved_client_headers

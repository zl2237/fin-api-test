"""共享请求发送器：单接口一次 HTTP 请求的完整通道。

此前同一逻辑存在两份平行实现（engine/dag_executor._send_request 与
routers/apis.debug_api 内联），本模块归一为单一事实来源：
- GET/POST 分发；含 file 字段时走 multipart（Content-Type 剥离/恢复、form_data 组装）
- 异常四分类：HttpStatusError(status) / BusinessError(200+业务码)
  / Auth|Timeout|JsonParse(0) / 其他(0)
- 加密传输/参数签名（接口 crypto_config.request.mode）：mode="encrypt"（缺省，
  海关 requestCipher 协议）明文参数统一加密为 {wrapper_field: 密文} 信封发送；
  mode="sign"（亿海融协议）载荷 JSON→Base64 不加密，外加私钥 RSA-MD5 签名的
  sign 字段（三条链路执行/调试/重放天然全覆盖）；
  响应解密经 client.response_decoder 在业务码校验之前介入。实际密文/信封经
  可选参 cipher_out（收集盒）带回调用方落 step_records.cipher_snapshot；传入的
  body dict 不被原地修改——request_body 列保持明文语义，重放按配置重新加密。
- multipart 文件句柄用后关闭

调用方：DagExecutor._send_request（执行主链路）、apis.debug_api（单接口调试）、
replay_service.replay_step（报告页步骤重放）。
"""
import base64
import json
from typing import Any

from utils.exceptions import (
    AuthError,
    BusinessError,
    CipherError,
    HttpStatusError,
    HttpTimeoutError,
    JsonParseError,
)

from .. import (
    models,
    path_setup,  # noqa: F401  确保 utils 可导入（sys.path 指向本仓根）
)
from ..engine.nested_path import get_nested_value
from ..services.cipher_service import (
    DEFAULT_SEGMENT_SIZE,
    decrypt_from_base64,
    encrypt_json_body,
    resolve_key_pair,
    sign_to_base64,
)
from ..services.file_helpers import resolve_physical_path


def build_multipart_files(db, file_fields: list[tuple[str, str]]) -> list:
    """将 file_id 列表转为 requests 的 files 参数格式。

    返回 [(field_name, (filename, bytes, content_type)), ...]。
    文件内容整体读入 bytes 而非传句柄：HttpClient 鉴权失效（异地登录/过期）
    自动重登重试时，句柄已被首次请求读空（EOF），重发的 file part 会是
    0 字节，服务端报「请选择文件或者文件内容为空」（执行记录 614：
    每步都触发重登的清晨互踢场景）；bytes 不可变，重试天然幂等。
    file 字段值非空即视为「必须带上文件」：ID 非法 / 文件中心无记录 /
    物理文件缺失时抛 ValueError 使步骤失败——静默跳过会让错误难以定位
    （多机部署时文件中心物理目录不共享即触发）。
    """
    files_payload: list = []
    for field_name, file_id_str in file_fields:
        try:
            file_id = int(file_id_str)
        except (ValueError, TypeError):
            raise ValueError(
                f"file 字段「{field_name}」的文件 ID 非法: {file_id_str!r}，"
                f"请填文件中心里的文件 ID")
        f = db.query(models.TestFile).filter(models.TestFile.id == file_id).first()
        if not f:
            raise ValueError(
                f"file 字段「{field_name}」的文件不存在（文件中心 id={file_id}），"
                f"请到文件中心确认该文件仍在")
        physical = resolve_physical_path(f.storage_path)
        if not physical.exists():
            raise ValueError(
                f"file 字段「{field_name}」的物理文件丢失（id={file_id}「{f.name}」，"
                f"路径 {f.storage_path}）。多机部署时文件中心目录需共享存储，"
                f"或在本机文件中心重新上传后更新节点配置")
        files_payload.append((field_name, (f.name, physical.read_bytes(), f.content_type)))
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


def _is_form_urlencoded(headers: dict | None) -> bool:
    """headers 声明 Content-Type 为 x-www-form-urlencoded（curl 导入的表单接口）"""
    ct = (headers or {}).get("Content-Type") or (headers or {}).get("content-type") or ""
    return "x-www-form-urlencoded" in ct.lower()


def _build_response_decoder(resp_cfg: dict, req_cfg: dict,
                            cipher_keys: dict, cipher_out: dict | None):
    """构造响应解密 decoder（挂 client.response_decoder，HttpClient 在鉴权失效
    判定/业务码校验之前调用）。

    - mode="field"（默认）：响应是 JSON 信封，取 field（默认 responseCipher）的
      密文串解密，解密结果【整体替换】响应——与请求侧对称（编辑/断言的都是内层
      业务 JSON，路径直接打业务字段，无需穿过包裹字段）
    - mode="body"：响应整体是一个 Base64 密文字符串（JSON 字符串形态），解密后
      整体替换；裸非 JSON 的 Base64 文本响应在 HttpClient 层就落 JsonParseError
      原路径（decoder 拿不到），属已知边界
    - 字段守卫：密文字段不在 / 值非非空字符串 → 原样返回——重登请求走同一
      client（decoder 尚在挂载窗口内）、明文错误响应都靠它分毫不动
    """
    mode = str(resp_cfg.get("mode") or "field").strip()
    field = str(resp_cfg.get("field") or "responseCipher").strip()
    key_name = str(resp_cfg.get("key") or req_cfg.get("key") or "").strip()
    if not key_name:
        raise CipherError(
            "开启了响应解密但未指定密钥对名称，请到「接口编辑 → 加密配置」填写"
            "（未单独配置时默认复用请求加密的密钥对名称）")
    pair = resolve_key_pair(cipher_keys, key_name)
    private_material = pair.get("private_key")
    if not private_material:
        raise CipherError(
            f"密钥对「{key_name}」缺少私钥，响应解密需要私钥，"
            "请到「环境编辑 → 加密配置」补录")

    def decoder(resp_json):
        # 字段守卫：非预期形态一律原样返回（明文响应零影响）
        raw: Any
        if mode == "body":
            if not isinstance(resp_json, str) or not resp_json.strip():
                return resp_json
            raw = resp_json
        else:
            if not isinstance(resp_json, dict):
                return resp_json
            raw = resp_json.get(field)
            if not isinstance(raw, str) or not raw.strip():
                return resp_json
        plain = decrypt_from_base64(raw, private_material)
        try:
            decoded = json.loads(plain.decode("utf-8"))
        except Exception as e:
            raise CipherError(
                f"响应解密后的明文不是合法 JSON：{e}。请确认密文字段/模式配置"
                "与对方返回格式一致，或公私钥不配对（OpenSSL≥3.6 下不配对解出"
                "的是乱码而非报错，测试/生产密钥不可混用）", stage="response")
        if cipher_out is not None:
            cipher_out["response"] = raw
        return decoded

    return decoder


def _build_signed_envelope(api, req_cfg: dict, pair: dict, body: Any,
                           cipher_out: dict | None) -> dict:
    """亿海融参数签名模式：载荷 → data=Base64(JSON)（不加密）+ sign=私钥
    RSA-MD5 签名（PHP openssl_sign 语义，对 data 原始字符串签名）。

    - 载荷取值：source_field 空 → 整个 body；非空 → 按点号路径取字段
      （字段 UI 无法表达根节点字符串数组，亿海融的信用代码列表存于
      array 类型字段，如 credit_codes）；取不到值报中文错
    - 不强制载荷类型（数组/对象/标量均可——误配由对端 503 拒绝暴露）
    - 不改传入 body（明文落库语义与 encrypt 模式一致）；cipher_out["request"]
      存整个 {data,sign} 信封的紧凑 JSON 串——sign 是排障第一物证，
      而 wire body 本身从不落库
    """
    key_name = str(req_cfg.get("key") or "").strip()
    private_material = pair.get("private_key")
    if not private_material:
        raise CipherError(
            f"密钥对「{key_name}」缺少私钥：参数签名需要私钥（响应对端还会用你的"
            "公钥加密回包，解密也需要它），请到「环境编辑 → 加密配置」补录")
    source_field = str(req_cfg.get("source_field") or "").strip()
    if source_field:
        payload = get_nested_value(body, source_field)
        if payload is None:
            raise CipherError(
                f"接口【{api.name}】参数签名配置的取值字段「{source_field}」在请求体中"
                "取不到值，请检查字段 key 拼写与示例值（亿海融的统一社会信用代码列表"
                "一般放在 array 类型字段里，示例值须为 JSON 数组且非空）")
    else:
        payload = body
    data_b64 = base64.b64encode(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).decode("ascii")
    sign_b64 = sign_to_base64(
        data_b64.encode("utf-8"), private_material,
        str(req_cfg.get("sign_algorithm") or "md5"))
    data_field = str(req_cfg.get("data_field") or "data").strip() or "data"
    sign_field = str(req_cfg.get("sign_field") or "sign").strip() or "sign"
    envelope = {data_field: data_b64, sign_field: sign_b64}
    if cipher_out is not None:
        cipher_out["request"] = json.dumps(
            envelope, ensure_ascii=False, separators=(",", ":"))
    return envelope


def send_request(db, client, api, body: Any,
                 file_fields: list[tuple[str, str]] | None = None,
                 timeout: int = 15,
                 headers: dict | None = None,
                 cipher_out: dict | None = None) -> tuple[int, Any, str | None]:
    """发送一次接口请求。返回 (status_code, response_body, error_msg)。

    :param file_fields: file 类型字段列表 [(field_name, file_id), ...]
                        非空时构建 multipart 请求，文件从文件中心按 file_id 取
    :param headers: 本次请求的 headers（prepare_request 组装产物：环境公共头 +
                    接口 headers_template 覆盖 + ${} 求值）。None 用 client.headers。
                    发送期间临时替换 client.headers，结束恢复（不污染登录态等会话头）
    :param cipher_out: 加密传输密文收集盒（可选）。约定键："request"=实际发出的
                        报文物证（encrypt 模式=整体 Base64 密文；sign 模式=含
                        data/sign 的信封 JSON 串）；"response"=解密前的原始密文。
                        DAG 重试循环中每次 attempt 覆盖（PKCS1v1.5 加密填充随机，
                        每发一次密文必不同），最终留最后一次尝试——与
                        retry_history「主行=最终尝试」语义一致。
    """
    # —— 加密配置解析（getattr 防御 SimpleNamespace 测试桩）——
    crypto = getattr(api, "crypto_config", None) or {}
    req_cfg = crypto.get("request") or {}
    resp_cfg = crypto.get("response") or {}
    req_on = bool(req_cfg.get("enabled"))
    resp_on = bool(resp_cfg.get("enabled"))
    cipher_keys = getattr(client, "cipher_keys", None) or {}

    wire_body = body
    files_payload: list = []
    saved_client_headers = client.headers if headers is not None else None
    # —— 响应解密 decoder（发送窗口临时挂载，finally 恢复；在 HttpClient 内部
    # 于鉴权失效判定/业务码校验之前介入，解密后的明文与明文协议同口径）——
    saved_decoder = getattr(client, "response_decoder", None)
    decoder_installed = False
    try:
        # —— 请求加密：配置/密钥问题抛 CipherError(stage=request)，由下方 except
        # 统一分流为 (0, error) 元组——三条链路（DAG 重试循环/调试/重放）均按
        # 返回值驱动，不接异常 ——
        if req_on:
            req_mode = str(req_cfg.get("mode") or "encrypt").strip().lower()
            if api.method.upper() == "GET":
                raise CipherError(
                    f"接口【{api.name}】开启了请求加密/参数签名，但 GET 请求的参数"
                    "在 URL 上无法承载，请关闭加密配置或改用 POST")
            if file_fields or _is_form_urlencoded(headers if headers is not None
                                                  else getattr(client, "headers", None)):
                raise CipherError(
                    f"接口【{api.name}】开启了请求加密/参数签名，仅支持 JSON 请求体，"
                    "请移除 file 字段 / 去掉 form-urlencoded 的 Content-Type 声明，"
                    "或关闭加密配置")
            key_name = str(req_cfg.get("key") or "").strip()
            if not key_name:
                raise CipherError(
                    f"接口【{api.name}】开启了请求加密/签名但未指定密钥对名称，"
                    "请到「接口编辑 → 加密配置」填写（须与环境「加密配置」里的名称一致）")
            pair = resolve_key_pair(cipher_keys, key_name)
            if req_mode == "sign":
                # 亿海融参数签名：data=Base64(JSON) 不加密 + sign=私钥签名
                wire_body = _build_signed_envelope(api, req_cfg, pair, body, cipher_out)
            elif req_mode == "encrypt":
                # 海关 requestCipher 信封（缺省模式，行为与历史版本完全一致）
                public_material = pair.get("public_key")
                if not public_material:
                    raise CipherError(
                        f"密钥对「{key_name}」缺少公钥，请到「环境编辑 → 加密配置」补录")
                segment_size = int(req_cfg.get("segment_size") or DEFAULT_SEGMENT_SIZE)
                wrapper_field = str(req_cfg.get("wrapper_field") or "requestCipher")
                cipher_b64 = encrypt_json_body(body, public_material, segment_size)
                if cipher_out is not None:
                    cipher_out["request"] = cipher_b64
                # 新建信封 dict，绝不改传入 body——调用方的 request_body 变量保持明文落库
                wire_body = {wrapper_field: cipher_b64}
            else:
                raise CipherError(
                    f"接口【{api.name}】加密配置的请求模式无效：{req_mode!r}"
                    "（支持：encrypt 加密信封 / sign 参数签名），请到"
                    "「接口编辑 → 加密配置」修正")
        if resp_on:
            client.response_decoder = _build_response_decoder(
                resp_cfg, req_cfg, cipher_keys, cipher_out)
            decoder_installed = True
        if headers is not None:
            client.headers = headers
        if api.method.upper() == "GET":
            # 数组请求体（is_array_body）取首元素作 query 参数，
            # 避免整个 list 传给 requests.params 触发 k-v 解包异常
            params = wire_body
            if isinstance(wire_body, list) and wire_body and isinstance(wire_body[0], dict):
                params = wire_body[0]
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
                if isinstance(wire_body, dict):
                    form_data = wire_body
                elif isinstance(wire_body, list) and wire_body and isinstance(wire_body[0], dict):
                    form_data = wire_body[0]
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
                form_data = wire_body[0] if isinstance(wire_body, list) and wire_body and isinstance(wire_body[0], dict) else wire_body
                resp = client.post_form(api.path, data=form_data, timeout=timeout)
            else:
                resp = client.post(api.path, json=wire_body, timeout=timeout)
        elif _is_form_urlencoded(client.headers):
            # 表单接口（curl 导入声明 x-www-form-urlencoded）：必须用表单编码发送。
            # 此前统一走 json= 且 headers 已声明 form 时 requests 不会改写 Content-Type，
            # 形成「form 声明 + JSON 文本」的错配请求，服务端按表单解析取不到任何字段
            # （如 precheckSyncFiles.html 的 order_no）。数组请求体取首元素（与 GET/multipart 同口径）
            form_data = wire_body[0] if isinstance(wire_body, list) and wire_body and isinstance(wire_body[0], dict) else wire_body
            resp = client.post_form(api.path, data=form_data, timeout=timeout)
        else:
            resp = client.post(api.path, json=wire_body, timeout=timeout)
        # HttpClient 成功返回即 HTTP 200 且业务码 200
        return 200, resp, None
    except HttpStatusError as e:
        return e.status_code, {"error": str(e)}, str(e)
    except CipherError as e:
        # 请求侧（未发出）status=0；响应侧（HTTP 已 200 收到报文）status=200 且
        # err 非空使步骤判负可见。注意：非空 err 会消耗 DAG 节点级重试额度（见
        # CipherError docstring——确定性配置错误重试必然复现，加密环境保持
        # node_retry_count=0）
        status = 0 if e.stage == "request" else 200
        return status, {"error": str(e)}, str(e)
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
        if decoder_installed:
            client.response_decoder = saved_decoder

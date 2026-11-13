import requests
from requests.exceptions import Timeout
from typing import Dict, Optional, Callable
from utils.exceptions import HttpStatusError, JsonParseError, AuthError, HttpTimeoutError, BusinessError
from utils.log_util import get_logger

logger = get_logger()


def _trunc_long_strings(obj, limit: int = 200):
    """日志用：递归缩短超长字符串（加密传输的 Base64 密文可达数十 KB，防日志爆量）。

    仅影响日志展示，不改变发送内容。
    """
    if isinstance(obj, str):
        return obj if len(obj) <= limit else obj[:limit] + f"...(共{len(obj)}字符,截断)"
    if isinstance(obj, dict):
        return {k: _trunc_long_strings(v, limit) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_trunc_long_strings(v, limit) for v in obj]
    return obj


class HttpClient:
    def __init__(self, base_url: str = ""):
        """
        HTTP请求客户端
        :param base_url: 接口基础地址
        """
        self.base_url = base_url
        self.session = requests.Session()
        self.headers: Dict[str, str] = {}
        self._token_refresh_callback: Optional[Callable[[], None]] = None
        # 业务成功码集合（响应 code 命中任一即成功）：不同系统约定不同
        # （物流系统 200 / ThinkPHP 系 1 / 部分系统 0），由环境配置注入，默认平台约定 200
        self.success_codes: set = {"200"}
        # 鉴权失效业务码集合（HTTP 200 + code 命中任一视为登录态失效，触发重登重试）：
        # 405 账号异地登录为平台默认；407 登录已过期等系统特有码由环境 login_config 注入
        self.auth_expire_codes: set = {"401", "405"}
        # 加密传输响应解码器（接口级加密配置注入，与 success_codes 注入同构）：
        # 在鉴权失效判定/业务码校验之前解密密文信封，解密后的明文与明文协议同口径
        # 参与全部校验；decoder 自带字段守卫，密文字段不在（重登请求、明文错误响应）
        # 时原样返回。send_request 发送窗口临时挂载、finally 恢复。
        self.response_decoder: Optional[Callable[[object], object]] = None
        # 环境加密密钥材料表 {名称: {public_key, private_key}}（runtime_service
        # build_http_client 按环境 cipher_config 挂载；懒校验——发送时用到哪把
        # 才解析哪把，无加密接口的环境不被坏密钥拖垮）
        self.cipher_keys: Dict[str, Dict[str, Optional[str]]] = {}

    def set_success_codes(self, codes) -> None:
        """配置业务成功码集合，兼容 '200,1' 字符串 / list / 单值；空值忽略保持现值"""
        if codes is None:
            return
        if isinstance(codes, str):
            parts = codes.split(",")
        elif isinstance(codes, (list, tuple, set)):
            parts = list(codes)
        else:
            parts = [codes]
        normalized = {str(p).strip() for p in parts if str(p).strip() != ""}
        if normalized:
            self.success_codes = normalized

    def set_auth_expire_codes(self, codes) -> None:
        """配置鉴权失效业务码集合（与 set_success_codes 同一归一化口径）；空值忽略保持现值"""
        if codes is None:
            return
        if isinstance(codes, str):
            parts = codes.split(",")
        elif isinstance(codes, (list, tuple, set)):
            parts = list(codes)
        else:
            parts = [codes]
        normalized = {str(p).strip() for p in parts if str(p).strip() != ""}
        if normalized:
            self.auth_expire_codes = normalized

    def set_header(self, key: str, value: str):
        """设置单个请求头"""
        self.headers[key] = value

    def clear_headers(self):
        """清空所有headers"""
        self.headers.clear()

    def set_token_refresh_callback(self, callback: Callable[[], None]):
        """
        注册Token刷新回调函数
        回调内部完成登录并全局更新Authorization header
        """
        self._token_refresh_callback = callback

    def get(self, url: str, params: Optional[Dict] = None, timeout=10) -> Dict:
        return self._request("GET", url, params=params, timeout=timeout)

    def post(self, url: str, json: Optional[Dict] = None, timeout=10) -> Dict:
        return self._request("POST", url, json=json, timeout=timeout)

    def post_form(self, url: str, data: Optional[Dict] = None, timeout=10) -> Dict:
        """发送 application/x-www-form-urlencoded 请求（data 会被 requests 表单编码）。

        调用方须保证 self.headers 的 Content-Type 是 form-urlencoded
        （headers 已有时 requests 不会改写，与 data 编码方式一致）
        """
        return self._request("POST", url, data=data, timeout=timeout)

    def post_multipart(self, url: str, data: Optional[Dict] = None, files: Optional[list] = None, timeout=20) -> Dict:
        """发送 multipart/form-data 请求（文件上传场景）。

        :param data: 表单普通字段（dict）
        :param files: 文件字段列表，元素格式 (field_name, (filename, fileobj, content_type))
                      与 requests 的 files 参数一致
        """
        return self._request("POST", url, data=data, files=files, timeout=timeout)

    def _request(self, method: str, url: str, params=None, json=None, data=None, files=None, timeout=20, retry_401: bool = True) -> Dict:
        full_url = self.base_url + url

        # 日志脱敏
        log_headers = self.headers.copy()
        if "Authorization" in log_headers:
            log_headers["Authorization"] = "******"

        logger.info(f"【HTTP请求】{method} {full_url}")
        logger.info(f"【请求头】{log_headers}")
        logger.info(f"【请求体】{_trunc_long_strings(json)} params={_trunc_long_strings(params)} "
                    f"data={_trunc_long_strings(data)} files={len(files) if files else 0}")

        try:
            resp = self.session.request(
                method=method,
                url=full_url,
                headers=self.headers,
                params=params,
                json=json,
                data=data,
                files=files,
                timeout=timeout
            )
        except Timeout:
            raise HttpTimeoutError(full_url, timeout)

        resp_text = resp.text[:2000] if len(resp.text) > 2000 else resp.text
        logger.info(f"【HTTP响应】status={resp.status_code} body={resp_text}")

        # 只解析一次json，复用结果
        resp_json = None
        try:
            resp_json = resp.json()
        except Exception:
            pass

        # ========== 加密传输响应解码 ==========
        # 在鉴权失效判定/业务码校验/非 dict 判定之前介入：密文信封里的 code 405/407
        # 也能触发自动重登，解密后明文与明文协议完全同口径。鉴权重登的递归重发读取
        # 同一实例属性，decoder 天然重挂。
        if self.response_decoder is not None and resp_json is not None:
            resp_json = self.response_decoder(resp_json)

        # ========== 鉴权失效判定 ==========
        auth_expire = False
        if resp.status_code == 401:
            auth_expire = True
        # HTTP 200 + 业务码命中鉴权失效集合（字符串化统一比较，兼容 int/str）：
        # 默认 401/405；407 登录已过期等系统特有码经 set_auth_expire_codes 注入
        if resp_json and isinstance(resp_json, dict):
            code_str = str(resp_json.get("code", "")).strip()
            if code_str and code_str in self.auth_expire_codes:
                auth_expire = True

        if auth_expire and retry_401:
            if not self._token_refresh_callback:
                logger.error("检测到鉴权失效，但未配置token刷新回调，无法自动重登！")
                raise AuthError(full_url, resp_text)

            logger.warning("检测到鉴权失效(账号异地登录/token过期)，执行自动重新登录...")
            try:
                self._token_refresh_callback()
                logger.info("Token刷新完成，重试当前请求")
            except Exception as e:
                logger.error(f"自动刷新Token失败: {str(e)}")
                raise AuthError(full_url, resp_text) from e

            return self._request(
                method=method,
                url=url,
                params=params,
                json=json,
                data=data,
                files=files,
                timeout=timeout,
                retry_401=False
            )
        # =================================

        # 非200状态码异常
        if resp.status_code not in (200,):
            raise HttpStatusError(resp.status_code, full_url, resp_text)

        # JSON解析失败 / 非对象 JSON（如 ThinkPHP 裸标量响应 "-404"、JSON 数组）
        # 无法从中读业务码，与"解析失败"同等对待：原文交回上层（断言/调试展示）判定
        if not isinstance(resp_json, dict):
            raise JsonParseError(full_url, resp_text)

        # 业务码异常：仅当响应携带 code 且不在环境配置的成功码集合时判定
        # （平台默认 {200}；环境 success_codes 可适配不同系统约定，如 ThinkPHP 成功 code:1）。
        # code 缺失/为 null（如 ThinkPHP 系统成功响应 {"code":null,...}）时无约定
        # 可依，不视为业务失败，原样返回交断言裁决
        code = resp_json.get("code")
        if code is not None and str(code).strip() not in self.success_codes:
            raise BusinessError(
                code=code,
                msg=resp_json.get("msg", ""),
                url=full_url,
                resp_text=resp_text,
                resp_json=resp_json
            )

        return resp_json

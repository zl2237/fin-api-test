import requests
from requests.exceptions import Timeout
from typing import Dict, Optional, Callable
from utils.exceptions import HttpStatusError, JsonParseError, AuthError, HttpTimeoutError, BusinessError
from utils.log_util import get_logger

logger = get_logger()


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
        logger.info(f"【请求体】{json} params={params} data={data} files={len(files) if files else 0}")

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

        # ========== 鉴权失效判定 ==========
        auth_expire = False
        if resp.status_code == 401:
            auth_expire = True
        if resp_json and isinstance(resp_json, dict) and resp_json.get("code") == 405:
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

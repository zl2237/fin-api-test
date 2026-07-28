class HttpStatusError(Exception):
    """HTTP响应状态码异常（非200）"""
    def __init__(self, status_code: int, url: str, resp_text: str):
        self.status_code = status_code
        self.url = url
        self.resp_text = resp_text
        super().__init__(
            f"请求异常，状态码:{status_code}，url:{url}，响应内容:{resp_text}"
        )


class HttpTimeoutError(Exception):
    """HTTP请求超时异常"""
    def __init__(self, url: str, timeout: int):
        self.url = url
        self.timeout = timeout
        super().__init__(
            f"接口请求超时，url:{url}，设置超时时间：{timeout}s"
        )


class AuthError(Exception):
    """鉴权失效异常：401 / code=405账号异地登录、token过期"""
    def __init__(self, url: str, resp_text: str):
        self.url = url
        self.resp_text = resp_text
        super().__init__(
            f"鉴权失败，请重新登录，url:{url}，响应内容:{resp_text}"
        )


class JsonParseError(Exception):
    """响应JSON解析失败异常"""
    def __init__(self, url: str, resp_text: str):
        self.url = url
        self.resp_text = resp_text
        super().__init__(
            f"JSON解析失败，url:{url}，原始响应:{resp_text}"
        )


class BusinessError(Exception):
    """后端业务逻辑异常：http 200，但业务code非成功"""
    def __init__(self, code: int, msg: str, url: str, resp_text: str):
        self.code = code
        self.msg = msg
        self.url = url
        self.resp_text = resp_text
        super().__init__(
            f"业务执行失败，code:{code}, msg:{msg}, url:{url}，完整响应:{resp_text}"
        )


class DBQueryError(Exception):
    """数据库执行/查询异常"""
    def __init__(self, sql: str, args: tuple, error_msg: str):
        self.sql = sql
        self.args = args
        self.error_msg = error_msg
        super().__init__(
            f"数据库执行异常，sql:{sql}, 参数:{args}, 错误信息:{error_msg}"
        )
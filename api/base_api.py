from utils.http_client import HttpClient


class BaseApi:
    def __init__(self, http_client: HttpClient):
        """
        API顶层父类
        :param http_client: HTTP请求客户端实例，由工厂传入
        """
        self.http = http_client
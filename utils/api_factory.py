import copy
from typing import Dict, Type, TypeVar, Optional, Callable
from api.base_api import BaseApi
from utils.http_client import HttpClient

T = TypeVar("T", bound=BaseApi)


class ApiFactory:
    def __init__(self, base_url: str, base_headers: Dict = None):
        self.base_url = base_url
        self.base_headers = base_headers or {}
        self._instance_cache: Dict[Type[BaseApi], BaseApi] = {}
        # 新增：保存token刷新回调
        self._token_refresh_callback: Optional[Callable[[], None]] = None

    def set_global_token_refresh_callback(self, callback: Callable[[], None]):
        """设置全局token刷新回调，新建HttpClient自动绑定"""
        self._token_refresh_callback = callback

    def get_api(self, api_cls: Type[T]) -> T:
        if api_cls not in self._instance_cache:
            client = HttpClient(base_url=self.base_url)
            client.headers = copy.deepcopy(self.base_headers)
            # 关键：创建时直接绑定工厂保存的刷新回调
            if self._token_refresh_callback:
                client.set_token_refresh_callback(self._token_refresh_callback)
            api_inst = api_cls(client)
            self._instance_cache[api_cls] = api_inst
        return self._instance_cache[api_cls]

    def update_global_header(self, key: str, value: str):
        """统一更新全局header，并同步刷新所有已缓存API实例的http header"""
        self.base_headers[key] = value
        for api_inst in self._instance_cache.values():
            api_inst.http.set_header(key, value)

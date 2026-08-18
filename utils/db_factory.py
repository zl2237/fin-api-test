from typing import Dict, Type
from db.base_db import BaseDB
from db.db_client import DBClient


class DbFactory:
    def __init__(self, db_config: Dict):
        """
        DB懒加载工厂
        :param db_config: mysql连接配置字典
        """
        self.db_config = db_config
        self._instance_cache: Dict[Type[BaseDB], BaseDB] = {}

    def get_db(self, db_cls: Type[BaseDB]) -> BaseDB:
        """
        懒加载获取DB业务实例，缓存复用
        :param db_cls: 业务DB类，继承BaseDB
        :return: DB实例
        """
        if db_cls not in self._instance_cache:
            client = DBClient(**self.db_config)
            db_instance = db_cls(client)
            self._instance_cache[db_cls] = db_instance
        return self._instance_cache[db_cls]

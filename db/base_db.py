from db.db_client import DBClient


class BaseDB:
    def __init__(self, db_client: DBClient):
        """
        DB业务顶层父类
        :param db_client: mysql客户端实例
        """
        self.db = db_client

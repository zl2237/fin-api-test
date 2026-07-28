import pymysql
from pymysql.cursors import DictCursor
from utils.log_util import get_logger
from utils.exceptions import DBQueryError

logger = get_logger()


class DBClient:
    def __init__(self, host, port, user, password, database):
        """
        MySQL数据库客户端
        :param host: 数据库地址
        :param port: 端口
        :param user: 账号
        :param password: 密码
        :param database: 库名
        """
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.database = database
        self.conn = None

    def _ping_alive(self) -> bool:
        """
        心跳检测连接是否存活
        :return: True 存活 / False 已断开
        """
        if self.conn is None or not self.conn.open:
            return False
        try:
            # ping 探测，检查TCP连接有效性
            self.conn.ping(reconnect=False)
            return True
        except Exception:
            return False

    def connect(self):
        """
        【增强版】连接保活入口
        连接不存在 / 连接失效 → 重建连接
        """
        # 连接存在且存活，直接返回
        if self._ping_alive():
            return

        # 旧连接失效，先关闭
        if self.conn is not None:
            try:
                self.conn.close()
            except Exception:
                pass

        # 创建新连接
        try:
            self.conn = pymysql.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.database,
                cursorclass=DictCursor,
                autocommit=True
            )
            logger.info("数据库连接创建成功")
        except Exception as e:
            raise DBQueryError(sql="数据库连接", args=(), error_msg=str(e)) from e

    def query(self, sql: str, args=None):
        """
        查询多条记录
        :param sql: 查询sql
        :param args: sql占位参数
        :return: list[dict]
        """
        self.connect()
        args = args or []
        logger.info(f"执行SQL查询:\n{sql}, args:{args}")
        try:
            with self.conn.cursor() as cur:
                cur.execute(sql, args)
                return cur.fetchall()
        except Exception as e:
            raise DBQueryError(sql=sql, args=tuple(args), error_msg=str(e)) from e

    def query_one(self, sql: str, args=None):
        """
        查询单条记录
        :param sql: 查询sql
        :param args: sql占位参数
        :return: dict / None
        """
        rows = self.query(sql, args)
        return rows[0] if rows else None

    def execute(self, sql: str, args=None):
        """
        执行增删改语句
        :param sql: DML语句
        :param args: sql占位参数
        :return: 影响行数
        """
        self.connect()
        args = args or []
        logger.info(f"执行SQL:\n{sql}, args:{args}")
        try:
            with self.conn.cursor() as cur:
                return cur.execute(sql, args)
        except Exception as e:
            raise DBQueryError(sql=sql, args=tuple(args), error_msg=str(e)) from e

    def close(self):
        """关闭数据库连接"""
        if self.conn and self.conn.open:
            try:
                self.conn.close()
            except Exception:
                pass

    def __enter__(self):
        """支持with上下文进入"""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """支持with上下文退出，自动关闭"""
        self.close()
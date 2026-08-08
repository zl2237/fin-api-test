"""
SQLAlchemy 引擎与会话工厂（仅支持 MySQL）。

环境变量：
    DB_HOST（默认 127.0.0.1）
    DB_PORT（默认 3306）
    DB_USER（默认 root）
    DB_PASSWORD（必填）
    DB_NAME（默认 fin_api_test）
"""
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


def _build_mysql_url() -> str:
    """MySQL 连接 URL，使用 PyMySQL 驱动（utf8mb4 支持完整 Unicode 与 emoji）"""
    host = os.getenv("DB_HOST", "127.0.0.1")
    port = os.getenv("DB_PORT", "3306")
    user = os.getenv("DB_USER", "root")
    password = os.getenv("DB_PASSWORD", "")
    name = os.getenv("DB_NAME", "fin_api_test")
    if not password:
        raise RuntimeError(
            "[database] 未设置 DB_PASSWORD 环境变量，请配置后重启"
        )
    return f"mysql+pymysql://{user}:{password}@{host}:{port}/{name}?charset=utf8mb4"


DATABASE_URL = _build_mysql_url()

# MySQL 连接池配置：避免长连接被 server 端断开（wait_timeout 默认 8h，这里 1h 主动回收）
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,      # 取连接前 ping 一下，失效则重建
    pool_recycle=3600,       # 1 小时回收
    pool_size=10,            # 连接池大小
    max_overflow=20,         # 突发可额外创建的连接数
    echo=False,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    """所有 ORM 模型的基类"""
    pass


def get_db():
    """FastAPI 依赖：提供数据库会话，请求结束自动关闭"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """建表：导入所有模型后调用 Base.metadata.create_all。
    表结构变更由 Alembic 管理（alembic upgrade head），不再用硬编码 ALTER。"""
    from . import models  # noqa: F401  触发模型注册
    Base.metadata.create_all(engine)

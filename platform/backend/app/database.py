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
from urllib.parse import quote_plus
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
    # 对用户名和密码做 URL 编码，避免 %、@、: 等特殊字符破坏连接串
    return f"mysql+pymysql://{quote_plus(user)}:{quote_plus(password)}@{host}:{port}/{name}?charset=utf8mb4"


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
    """数据库初始化：智能 Alembic 迁移。

    三种场景自动处理：
    - 旧库（有表无 alembic_version 表）：自动 stamp head，标记当前 schema 到位，不执行 DDL
    - 全新库（无表）：执行 alembic upgrade head，create_all 建表
    - 已迁移库（有 alembic_version 表）：执行 alembic upgrade head，应用增量迁移
    """
    from pathlib import Path
    from sqlalchemy import inspect
    from alembic.config import Config
    from alembic import command

    from . import models  # noqa: F401  触发模型注册

    alembic_cfg = Config(str(Path(__file__).parent.parent / "alembic.ini"))
    existing_tables = set(inspect(engine).get_table_names())

    if existing_tables and "alembic_version" not in existing_tables:
        # 旧库迁移：已有表但未纳入 Alembic 管理，标记当前为 head
        command.stamp(alembic_cfg, "head")
    else:
        # 全新库或已迁移库：执行迁移
        command.upgrade(alembic_cfg, "head")

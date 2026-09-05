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

from sqlalchemy import URL, create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


def _build_mysql_url() -> URL:
    """MySQL 连接 URL，使用 PyMySQL 驱动（utf8mb4 支持完整 Unicode 与 emoji）。

    URL.create 以结构化字段传参，无需手动 URL 编码——用户名/密码中的
    特殊字符（空格、@、:、%、/ 等）由 SQLAlchemy 正确处理。
    """
    password = os.getenv("DB_PASSWORD", "")
    if not password:
        raise RuntimeError(
            "[database] 未设置 DB_PASSWORD 环境变量，请配置后重启"
        )
    return URL.create(
        "mysql+pymysql",
        username=os.getenv("DB_USER", "root"),
        password=password,  # 原始字符串直接传入，无需转义
        host=os.getenv("DB_HOST", "127.0.0.1"),
        port=int(os.getenv("DB_PORT", "3306")),
        database=os.getenv("DB_NAME", "fin_api_test"),
        query={"charset": "utf8mb4"},
    )


DATABASE_URL = _build_mysql_url()


def _connect_args() -> dict:
    """TiDB Cloud 等 TLS-only 云数据库：DB_SSL=true 时启用系统 CA 校验的 TLS 连接"""
    if os.getenv("DB_SSL", "").strip().lower() in {"1", "true", "yes"}:
        import ssl

        return {"ssl": ssl.create_default_context()}
    return {}


# MySQL 连接池配置：避免长连接被 server 端断开（wait_timeout 默认 8h，这里 1h 主动回收）
engine = create_engine(
    DATABASE_URL,
    connect_args=_connect_args(),
    pool_pre_ping=True,      # 取连接前 ping 一下，失效则重建
    pool_recycle=3600,       # 1 小时回收
    pool_size=10,            # 连接池大小
    max_overflow=20,         # 突发可额外创建的连接数
    echo=False,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    """所有 ORM 模型的基类"""


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

    from alembic.config import Config
    from sqlalchemy import inspect

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

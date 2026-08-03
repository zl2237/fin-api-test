"""
SQLite schema 迁移：给已有表补齐缺失的列。
SQLite 支持 ALTER TABLE ADD COLUMN，但不支持删列/改列类型，够用。

幂等：每列加之前先检查是否已存在。
"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "platform.db"


def get_existing_columns(conn, table: str) -> set:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def get_existing_tables(conn) -> set:
    return {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def add_column_if_missing(conn, table: str, column_def: str):
    """column_def 形如 'group_id INTEGER'"""
    col_name = column_def.split()[0]
    existing = get_existing_columns(conn, table)
    if col_name in existing:
        return False
    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column_def}")
    print(f"  + {table}.{col_name}")
    return True


def create_table_if_missing(conn, table: str, ddl: str):
    tables = get_existing_tables(conn)
    if table in tables:
        return False
    conn.executescript(ddl)
    print(f"  + 新建表 {table}")
    return True


def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    print(f"迁移 {DB_PATH}")

    # ===== 1. 新建缺失的表 =====
    new_tables = {
        "api_groups": """
            CREATE TABLE api_groups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL REFERENCES projects(id),
                name VARCHAR(100) NOT NULL,
                sort_order INTEGER DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """,
        "case_groups": """
            CREATE TABLE case_groups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL REFERENCES projects(id),
                name VARCHAR(100) NOT NULL,
                sort_order INTEGER DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """,
        "api_fields": """
            CREATE TABLE api_fields (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                api_id INTEGER NOT NULL REFERENCES api_definitions(id),
                key VARCHAR(200) NOT NULL,
                label VARCHAR(100),
                field_type VARCHAR(20) DEFAULT 'string',
                required BOOLEAN DEFAULT 0,
                default_value TEXT,
                remark TEXT,
                sort_order INTEGER DEFAULT 0
            )
        """,
    }
    for name, ddl in new_tables.items():
        create_table_if_missing(conn, name, ddl)

    # ===== 2. 给已有表补列 =====
    # api_definitions: 加 group_id
    add_column_if_missing(conn, "api_definitions", "group_id INTEGER")

    # test_cases: 加 group_id
    add_column_if_missing(conn, "test_cases", "group_id INTEGER")

    # environments: 拆分 variables 为 login_config / notify_config / variables
    # 旧 variables 保留不动，新加三列
    add_column_if_missing(conn, "environments", "login_config TEXT")
    add_column_if_missing(conn, "environments", "notify_config TEXT")
    add_column_if_missing(conn, "environments", "variables TEXT")

    # 旧 variables 字段的数据迁移到新 variables（如果旧字段存在且新字段为空）
    existing_env_cols = get_existing_columns(conn, "environments")
    # SQLAlchemy 旧模型用 variables 存所有变量；新模型也用 variables 存业务变量
    # 旧的 variables 列如果存在，数据保留；新的 login_config/notify_config 默认空 dict
    # 这里不自动迁移旧数据（避免误判），让用户用 migrate_legacy.py 重新同步

    # ===== 3. 数据修复：NULL → '{}'，避免 schema 验证失败 =====
    for col in ("login_config", "notify_config", "variables", "common_headers", "db_config"):
        if col in existing_env_cols:
            n = conn.execute(
                f"UPDATE environments SET {col}='{{}}' WHERE {col} IS NULL"
            ).rowcount
            if n:
                print(f"  ~ environments.{col}: {n} 行 NULL → '{{}}'")

    conn.commit()
    conn.close()
    print("迁移完成")


if __name__ == "__main__":
    main()

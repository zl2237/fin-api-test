"""
SQLite -> MySQL 全量数据迁移脚本。

用法（在 platform/backend 目录下执行）：
    python ../migrate_sqlite_to_mysql.py

说明：
- 源：platform/backend/platform.db (SQLite)
- 目标：MySQL fin_api_test 库（通过环境变量配置连接）
- 保持原主键 ID 不变，保证外键关系正确
- 迁移前清空 MySQL 目标表数据（保留表结构）
- 关闭外键检查，避免插入顺序约束
"""
import os
import sqlite3
import json
import sys
from pathlib import Path

# 确保能读取 app 模块
sys.path.insert(0, str(Path(__file__).resolve().parent / "backend"))

# 显式加载 backend/.env，使 MySQL 连接配置与后端一致（家里密码可能不同）
BACKEND_DIR = Path(__file__).resolve().parent / "backend"
_env_file = BACKEND_DIR / ".env"
if _env_file.exists():
    with open(_env_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

# MySQL 连接配置（优先用 .env 的值，缺省时回退默认）
os.environ.setdefault("DB_TYPE", "mysql")
os.environ.setdefault("DB_HOST", "127.0.0.1")
os.environ.setdefault("DB_PORT", "3306")
os.environ.setdefault("DB_USER", "root")
os.environ.setdefault("DB_PASSWORD", "123456")
os.environ.setdefault("DB_NAME", "fin_api_test")

import pymysql

SQLITE_PATH = Path(__file__).resolve().parent / "backend" / "platform.db"

# 迁移表顺序（按外键依赖拓扑排序）
TABLES = [
    "users",
    "projects",
    "environments",
    "api_groups",
    "api_definitions",
    "api_fields",
    "case_groups",
    "test_cases",
    "case_node_configs",
    "execution_records",
    "step_records",
    "assertion_records",
    "operation_logs",
]

# 各表的 JSON 字段（SQLite 存 TEXT，MySQL 存 JSON，需要确保是合法 JSON 字符串）
JSON_FIELDS = {
    "environments": ["db_config", "login_config", "notify_config", "variables", "common_headers"],
    "api_definitions": ["request_template", "headers_template"],
    "case_node_configs": ["pre_process", "post_extract", "assertions"],
    "test_cases": ["dag_config"],
    "execution_records": ["summary"],
    "step_records": ["request_headers", "request_body", "response_body"],
    "assertion_records": ["rule_config"],
}


def _normalize_json(value):
    """SQLite 中 JSON 字段可能为 None / 字符串 / 已是 dict（经 SQLAlchemy 写入）。
    统一转为 MySQL JSON 可接受的字符串。None 保持 None。"""
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, str):
        # 已经是字符串，校验是否合法 JSON；不合法则当普通字符串处理（包成 JSON 字符串）
        try:
            json.loads(value)
            return value
        except (json.JSONDecodeError, ValueError):
            return json.dumps(value, ensure_ascii=False)
    return json.dumps(value, ensure_ascii=False)


def migrate():
    if not SQLITE_PATH.exists():
        print(f"[ERROR] SQLite 文件不存在: {SQLITE_PATH}")
        sys.exit(1)

    src = sqlite3.connect(str(SQLITE_PATH))
    src.row_factory = sqlite3.Row

    dst = pymysql.connect(
        host=os.environ["DB_HOST"],
        port=int(os.environ["DB_PORT"]),
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        database=os.environ["DB_NAME"],
        charset="utf8mb4",
        autocommit=False,
    )

    try:
        # 关闭外键检查，清空目标表
        with dst.cursor() as cur:
            cur.execute("SET FOREIGN_KEY_CHECKS=0")
            for t in TABLES:
                cur.execute(f"TRUNCATE TABLE `{t}`")
                print(f"  [清空] {t}")
            dst.commit()
            print("[OK] MySQL 目标表已清空\n")

        total = 0
        for table in TABLES:
            rows = src.execute(f"SELECT * FROM {table}").fetchall()
            if not rows:
                print(f"[跳过] {table}: 无数据")
                continue

            cols = rows[0].keys()
            json_cols = set(JSON_FIELDS.get(table, []))
            # 构造批量 INSERT
            placeholders = ",".join(["%s"] * len(cols))
            col_list = ",".join(f"`{c}`" for c in cols)
            sql = f"INSERT INTO `{table}` ({col_list}) VALUES ({placeholders})"

            batch = []
            for row in rows:
                values = []
                for c in cols:
                    v = row[c]
                    if c in json_cols:
                        v = _normalize_json(v)
                    values.append(v)
                batch.append(values)

            with dst.cursor() as cur:
                cur.executemany(sql, batch)
            dst.commit()
            print(f"[OK] {table}: 迁移 {len(rows)} 条")
            total += len(rows)

        # 重新开启外键检查
        with dst.cursor() as cur:
            cur.execute("SET FOREIGN_KEY_CHECKS=1")
        dst.commit()

        print(f"\n>>> 迁移完成，共迁移 {total} 条记录 <<<")

        # 校验
        print("\n=== 校验 MySQL 各表行数 ===")
        with dst.cursor() as cur:
            for t in TABLES:
                cur.execute(f"SELECT COUNT(*) FROM `{t}`")
                cnt = cur.fetchone()[0]
                print(f"  {t}: {cnt}")

    finally:
        src.close()
        dst.close()


if __name__ == "__main__":
    migrate()

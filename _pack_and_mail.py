"""一次性打包：导出数据库 + 压缩项目代码 + 发送邮件。执行后自删。"""
import os
import sys
import zipfile
import smtplib
import tempfile
from datetime import datetime, date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

import pymysql

PROJECT_ROOT = r"c:\Users\zl\Desktop\fin-api-test"
DB_CONFIG = dict(
    host="127.0.0.1", port=3306, user="root",
    password="123456", database="fin_api_test", charset="utf8mb4",
)
SMTP_HOST = "smtp.qq.com"
SMTP_PORT = 465
SMTP_USER = "zl2237@qq.com"
SMTP_PASS = "ueefiurejsstebbb"
TO_ADDR = "zl2237@qq.com"

EXCLUDE_DIRS = {"venv", "node_modules", "__pycache__", ".git",
                ".pytest_cache", ".idea", "dist"}
EXCLUDE_EXTS = {".pyc", ".pyo"}


def dump_database(out_path: str) -> int:
    """导出全部表结构+数据为 SQL，返回总行数"""
    conn = pymysql.connect(**DB_CONFIG)
    cur = conn.cursor()
    cur.execute("SHOW TABLES")
    tables = [r[0] for r in cur.fetchall()]
    lines = [
        f"-- fin_api_test 数据库导出 生成时间 {datetime.now()}",
        f"-- 表数量: {len(tables)}",
        "SET NAMES utf8mb4;",
        "SET FOREIGN_KEY_CHECKS=0;",
        "",
    ]
    total_rows = 0
    for t in tables:
        cur.execute(f"SHOW CREATE TABLE `{t}`")
        ddl = cur.fetchone()[1]
        lines.append(f"-- ---------- 表 {t} 结构 ----------")
        lines.append(f"DROP TABLE IF EXISTS `{t}`;")
        lines.append(ddl + ";")
        lines.append("")
        cur.execute(f"SELECT * FROM `{t}`")
        rows = cur.fetchall()
        if not rows:
            continue
        total_rows += len(rows)
        cols = [d[0] for d in cur.description]
        col_list = ", ".join(f"`{c}`" for c in cols)
        lines.append(f"-- ---------- 表 {t} 数据: {len(rows)} 行 ----------")
        for row in rows:
            vals = []
            for v in row:
                if v is None:
                    vals.append("NULL")
                elif isinstance(v, bool):
                    vals.append("1" if v else "0")
                elif isinstance(v, (int, float)):
                    vals.append(str(v))
                elif isinstance(v, (datetime, date)):
                    vals.append(f"'{v.isoformat(sep=' ')}'")
                elif isinstance(v, bytes):
                    vals.append("0x" + v.hex())
                else:
                    s = str(v).replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n").replace("\r", "\\r")
                    vals.append(f"'{s}'")
            lines.append(f"INSERT INTO `{t}` ({col_list}) VALUES ({', '.join(vals)});")
        lines.append("")
    lines.append("SET FOREIGN_KEY_CHECKS=1;")
    cur.close()
    conn.close()
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return total_rows


def zip_project(zip_path: str) -> int:
    """压缩项目代码（排除大目录），返回文件数"""
    count = 0
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(PROJECT_ROOT):
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
            for f in files:
                if os.path.splitext(f)[1] in EXCLUDE_EXTS:
                    continue
                full = os.path.join(root, f)
                arc = os.path.relpath(full, PROJECT_ROOT)
                zf.write(full, arc)
                count += 1
    return count


def send_email(sql_path: str, zip_path: str, table_count: int, row_count: int, file_count: int):
    msg = MIMEMultipart()
    msg["From"] = SMTP_USER
    msg["To"] = TO_ADDR
    msg["Subject"] = "fin-api-test 项目代码+数据库打包"
    body = (
        f"fin-api-test 项目打包备份\n\n"
        f"【数据库】fin_api_test：{table_count} 张表，共 {row_count} 行数据\n"
        f"【代码】{file_count} 个文件（已排除 venv/node_modules/dist/__pycache__/.git 等）\n\n"
        f"恢复方式：\n"
        f"1. 创建空数据库 fin_api_test 后执行 fin_api_test_db.sql 导入结构和数据\n"
        f"2. 解压代码 zip，后端依赖见 platform/backend/requirements.txt，前端 npm install\n"
        f"3. .env 已包含在内（含真实配置），请妥善保管\n"
    )
    msg.attach(MIMEText(body, "plain", "utf-8"))
    for path, name in [
        (sql_path, "fin_api_test_db.sql"),
        (zip_path, "fin-api-test-code.zip"),
    ]:
        with open(path, "rb") as f:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header("Content-Disposition", f'attachment; filename="{name}"')
            msg.attach(part)
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as s:
        s.login(SMTP_USER, SMTP_PASS)
        s.sendmail(SMTP_USER, [TO_ADDR], msg.as_string())


if __name__ == "__main__":
    tmp = tempfile.mkdtemp(prefix="fin_mail_")
    sql_path = os.path.join(tmp, "fin_api_test_db.sql")
    zip_path = os.path.join(tmp, "fin-api-test-code.zip")
    print(f"[1/3] 导出数据库...", flush=True)
    rows = dump_database(sql_path)
    # 统计表数
    conn = pymysql.connect(**DB_CONFIG)
    cur = conn.cursor()
    cur.execute("SHOW TABLES")
    tables = len(cur.fetchall())
    cur.close()
    conn.close()
    print(f"  {tables} 张表, {rows} 行数据, SQL {os.path.getsize(sql_path)/1024:.1f} KB", flush=True)
    print(f"[2/3] 打包项目代码...", flush=True)
    files = zip_project(zip_path)
    print(f"  {files} 个文件, zip {os.path.getsize(zip_path)/1024/1024:.1f} MB", flush=True)
    print(f"[3/3] 发送邮件到 {TO_ADDR}...", flush=True)
    send_email(sql_path, zip_path, tables, rows, files)
    print("完成！", flush=True)

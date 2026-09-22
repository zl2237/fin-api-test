# UI 相关表备份：结构 + 数据 → backups/ui_tables_backup_YYYYMMDD.sql
# 密码经 MYSQL_PWD 环境变量传给 mysqldump，不出现在命令行/输出中
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, '.')
from dotenv import dotenv_values  # noqa: E402

cfg = dotenv_values('.env')
user = cfg.get('DB_USER', 'root')
password = cfg.get('DB_PASSWORD', '')
host = cfg.get('DB_HOST', '127.0.0.1')
port = cfg.get('DB_PORT', '3306')
name = cfg.get('DB_NAME', 'fin_api_test')

TABLES = ["ui_elements", "custom_actions", "ui_action_docs", "file_tags", "file_tag_relations"]
out_dir = Path('backups')
out_dir.mkdir(exist_ok=True)
out = out_dir / f"ui_tables_backup_{datetime.now():%Y%m%d}.sql"

env = {**os.environ, 'MYSQL_PWD': password}
dump = subprocess.run(
    ['mysqldump', f'-h{host}', f'-P{port}', f'-u{user}',
     '--single-transaction', '--default-character-set=utf8mb4',
     '--add-drop-table', '--routines=false', '--triggers=false', name, *TABLES],
    env=env, capture_output=True, text=True, encoding='utf-8')
if dump.returncode != 0:
    print('mysqldump failed:', dump.stderr[:500])
    sys.exit(1)

header = f"""-- UI 分支相关表备份（结构 + 数据）
-- 备份时间：{datetime.now():%Y-%m-%d %H:%M:%S}  库：{name}  表：{', '.join(TABLES)}
-- 恢复方法（任一 MySQL 客户端执行本文件即可，如 mysql -u<user> -p {name} < 本文件）：
--   1. 本文件含 DROP TABLE IF EXISTS + CREATE TABLE + INSERT，幂等覆盖恢复
--   2. 恢复后若要跑 UI 分支代码，还需把迁移版本盖章回 UI 链头（dev 头无需回退）：
--        UPDATE alembic_version SET version_num = 'dd44ee55ff66';
--      回 dev 时反向盖章：UPDATE alembic_version SET version_num = 'e9f0a1b2c3d4';

"""
out.write_text(header + dump.stdout, encoding='utf-8')
size_kb = out.stat().st_size / 1024
inserts = dump.stdout.count('INSERT INTO')
print(f"已备份: {out.resolve()}")
print(f"大小 {size_kb:.1f} KB | INSERT 语句 {inserts} 组 | 表 {len(TABLES)} 张")

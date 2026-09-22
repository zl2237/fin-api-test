# 线上（eline 开发库）副本导入本地：
# 1) 先 mysqldump 全量备份本地当前库（覆盖前快照）
# 2) mysql 客户端导入 fin_api_test.sql（DROP+CREATE+INSERT 幂等覆盖）
# 密码经 MYSQL_PWD 环境变量传递，不落命令行
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

env = {**os.environ, 'MYSQL_PWD': password}
mysql_bin = Path(r'D:\CODE\MySQL\MySQL Server 8.0\bin')

# 1. 本地库覆盖前备份
snap = Path('backups') / f'local_before_import_{datetime.now():%Y%m%d_%H%M%S}.sql'
r = subprocess.run([str(mysql_bin / 'mysqldump'), f'-h{host}', f'-P{port}', f'-u{user}',
                    '--single-transaction', '--default-character-set=utf8mb4', name],
                   env=env, capture_output=True, text=True, encoding='utf-8')
if r.returncode != 0:
    print('本地备份失败:', r.stderr[:300])
    sys.exit(1)
snap.write_text(r.stdout, encoding='utf-8')
print(f"本地库已备份: {snap} ({snap.stat().st_size / 1024:.0f} KB)")

# 2. 导入线上副本（覆盖）
dump_file = Path('backups') / 'fin_api_test.sql'
with dump_file.open(encoding='utf-8') as f:
    imp = subprocess.run([str(mysql_bin / 'mysql'), f'-h{host}', f'-P{port}', f'-u{user}',
                          '--default-character-set=utf8mb4', name],
                         env=env, stdin=f, capture_output=True, text=True, encoding='utf-8')
if imp.returncode != 0:
    print('导入失败:', imp.stderr[:500])
    sys.exit(1)
print('导入完成')

"""平台后端测试全局配置。

在导入 app 模块前设置必要环境变量，避免 database.py / auth.py 模块加载失败。
"""
import os
import sys
from pathlib import Path

# auth.py 模块加载时读取 JWT_SECRET_KEY
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-unit-test-only")
# database.py 模块加载时构建 DATABASE_URL 需要 DB_PASSWORD（不会实际连库）
os.environ.setdefault("DB_PASSWORD", "test")

# 仓库根加入 sys.path（与 app/path_setup.py 同法）：app.services.notifier 等模块
# 延迟 import 的 utils.wecom_util 依赖根目录在路径上；不注入的话测试环境下
# `utils` 可能解析到其他项目的同名包（命名空间包），patch 目标解析会失败
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

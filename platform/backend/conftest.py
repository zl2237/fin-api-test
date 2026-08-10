"""平台后端测试全局配置。

在导入 app 模块前设置必要环境变量，避免 database.py / auth.py 模块加载失败。
"""
import os

# auth.py 模块加载时读取 JWT_SECRET_KEY
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-unit-test-only")
# database.py 模块加载时构建 DATABASE_URL 需要 DB_PASSWORD（不会实际连库）
os.environ.setdefault("DB_PASSWORD", "test")

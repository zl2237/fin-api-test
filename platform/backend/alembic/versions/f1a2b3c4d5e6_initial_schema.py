"""initial schema

首版迁移：基于现有 models 创建全部表。
- 全新库：alembic upgrade head 执行本迁移，create_all 建表
- 旧库（已有表）：init_db 自动 stamp head 标记到位，不执行 DDL

Revision ID: f1a2b3c4d5e6
Revises:
Create Date: 2026-08-08 22:00:00
"""
from alembic import op

# revision identifiers, used by Alembic.
revision = "f1a2b3c4d5e6"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """创建全部表（首版 baseline）"""
    # 延迟导入：避免迁移文件加载时触发 database.py 的 DB_PASSWORD 检查
    from app.database import Base
    from app import models  # noqa: F401  触发所有模型注册到 metadata
    Base.metadata.create_all(op.get_bind())


def downgrade() -> None:
    """删除全部表"""
    from app.database import Base
    from app import models  # noqa: F401
    Base.metadata.drop_all(op.get_bind())

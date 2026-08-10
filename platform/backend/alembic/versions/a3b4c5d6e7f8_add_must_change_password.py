"""add must_change_password column

新增 users.must_change_password 字段，用于默认 admin 首次登录强制改密。
- 全新库：alembic upgrade head 时本迁移建列，默认 False
- 旧库：已有 users 表，本迁移加列；同时把 username='admin' 的用户标记为 True，
  强制其首次登录后改密（admin123 是弱密码）

Revision ID: a3b4c5d6e7f8
Revises: f1a2b3c4d5e6
Create Date: 2026-08-08 23:00:00
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "a3b4c5d6e7f8"
down_revision = "f1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """新增 must_change_password 列，并把现有 admin 用户标记为 True。"""
    op.add_column(
        "users",
        sa.Column("must_change_password", sa.Boolean(), nullable=False, server_default=sa.text("0")),
    )
    # 旧库已存在的默认 admin（username='admin'）强制改密，消除 admin123 弱密码风险
    op.execute("UPDATE users SET must_change_password = 1 WHERE username = 'admin'")


def downgrade() -> None:
    op.drop_column("users", "must_change_password")

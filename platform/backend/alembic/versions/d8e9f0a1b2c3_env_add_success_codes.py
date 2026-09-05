"""environments 增加业务成功码列

Revision ID: d8e9f0a1b2c3
Revises: c6d7e8f9a0b1
Create Date: 2026-09-04

不同系统的业务成功码约定不同（物流系统 200 / ThinkPHP 系 1 / 部分系统 0），
此前引擎硬编码 200 导致 ThinkPHP 系的成功响应（code:1, msg:获取成功）被
误判为业务失败，阻塞后续节点。
"""
from alembic import op
import sqlalchemy as sa

revision = "d8e9f0a1b2c3"
down_revision = "c6d7e8f9a0b1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "environments",
        sa.Column("success_codes", sa.String(100), nullable=False,
                  server_default="200",
                  comment="业务成功码（逗号分隔，响应 code 命中任一即成功；不同系统约定不同，如 ThinkPHP 成功 code:1）"),
    )


def downgrade() -> None:
    op.drop_column("environments", "success_codes")

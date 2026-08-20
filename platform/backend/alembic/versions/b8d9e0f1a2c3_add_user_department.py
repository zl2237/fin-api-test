"""add user department column

Revision ID: b8d9e0f1a2c3
Revises: c7d8e9f0a1b2
Create Date: 2026-08-20 19:00:00.000000

新增 users.department 字段：自由文本，可选，用于用户列表展示与筛选。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'b8d9e0f1a2c3'
down_revision: Union[str, Sequence[str], None] = 'c7d8e9f0a1b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """新增 users.department 字段：可选，自由文本。"""
    op.add_column('users', sa.Column('department', sa.String(50), nullable=True, comment='部门，可选，自由文本'))


def downgrade() -> None:
    """移除 users.department 字段。"""
    op.drop_column('users', 'department')

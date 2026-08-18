"""add user phone and email columns

Revision ID: c7d8e9f0a1b2
Revises: b1c2d3e4f5a6
Create Date: 2026-08-17 10:00:00.000000

新增 users.phone / users.email 字段：可选填写，填写时全局唯一。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c7d8e9f0a1b2'
down_revision: Union[str, Sequence[str], None] = 'b1c2d3e4f5a6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """新增 users.phone / users.email 字段，均为可选 + 唯一索引。"""
    op.add_column('users', sa.Column('phone', sa.String(20), nullable=True, comment='手机号，可选，填写时全局唯一'))
    op.add_column('users', sa.Column('email', sa.String(100), nullable=True, comment='邮箱，可选，填写时全局唯一'))
    op.create_index('uq_users_phone', 'users', ['phone'], unique=True)
    op.create_index('uq_users_email', 'users', ['email'], unique=True)


def downgrade() -> None:
    """移除 users.phone / users.email 字段及其唯一索引。"""
    op.drop_index('uq_users_email', table_name='users')
    op.drop_index('uq_users_phone', table_name='users')
    op.drop_column('users', 'email')
    op.drop_column('users', 'phone')

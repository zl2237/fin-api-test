"""add user avatar column

Revision ID: 9555ad43e3ac
Revises: c5d6e7f8a9b0
Create Date: 2026-08-09 15:31:57.046113

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '9555ad43e3ac'
down_revision: Union[str, Sequence[str], None] = 'c5d6e7f8a9b0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """新增 users.avatar 字段，存储前端压缩后的 base64 头像。"""
    op.add_column('users', sa.Column('avatar', sa.Text(), nullable=True, comment='头像 base64 data URL，前端压缩后上传'))


def downgrade() -> None:
    """移除 users.avatar 字段。"""
    op.drop_column('users', 'avatar')

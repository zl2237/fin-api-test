"""drop file tags

文件中心移除标签概念（全量下线）：
1. 删 file_tag_relations（文件-标签关联）
2. 删 file_tags（标签）

Revision ID: e5f6a7b8c9d0
Revises: d3e4f5a6b7c8
Create Date: 2026-08-25 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, Sequence[str], None] = 'd3e4f5a6b7c8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 先删关联再删标签（外键依赖）
    op.drop_table('file_tag_relations')
    op.drop_table('file_tags')


def downgrade() -> None:
    # 还原 b1c2d3e4f5a6 的原始建表结构
    op.create_table(
        'file_tags',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('project_id', sa.Integer(), sa.ForeignKey('projects.id'), nullable=False, index=True),
        sa.Column('name', sa.String(50), nullable=False),
        sa.Column('color', sa.String(20), server_default=''),
        sa.Column('created_at', sa.DateTime()),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.UniqueConstraint('project_id', 'name', name='uq_file_tag_project_name'),
    )
    op.create_table(
        'file_tag_relations',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('file_id', sa.Integer(), sa.ForeignKey('test_files.id'), nullable=False, index=True),
        sa.Column('tag_id', sa.Integer(), sa.ForeignKey('file_tags.id'), nullable=False, index=True),
        sa.UniqueConstraint('file_id', 'tag_id', name='uq_file_tag_relation'),
    )

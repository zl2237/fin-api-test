"""add sort_order to projects and environments

为 projects 和 environments 新增 sort_order 字段，支持列表拖拽排序。
- 默认值为 0，现有数据按 created_at/id 倒序保持稳定
- 列表查询改为 order_by(sort_order, id.desc())

Revision ID: f9a0b1c2d3e4
Revises: e8f9a0b1c2d3
Create Date: 2026-08-11 23:30:00
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f9a0b1c2d3e4'
down_revision = 'e8f9a0b1c2d3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'projects',
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0',
                  comment='排序序号（支持拖拽排序）'),
    )
    op.add_column(
        'environments',
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0',
                  comment='排序序号（支持拖拽排序）'),
    )


def downgrade() -> None:
    op.drop_column('environments', 'sort_order')
    op.drop_column('projects', 'sort_order')

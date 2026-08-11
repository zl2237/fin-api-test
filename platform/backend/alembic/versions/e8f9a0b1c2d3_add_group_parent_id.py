"""add parent_id to api_groups and case_groups

为 api_groups 和 case_groups 新增 parent_id 自引用外键，支持多级分组。
- parent_id 为 NULL 表示顶层分组（兼容现有数据，全部为顶层）
- 父分组删除时级联删除子分组（由 ORM relationship cascade 控制）

Revision ID: e8f9a0b1c2d3
Revises: d2e3f4a5b6c7
Create Date: 2026-08-11 00:30:00
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e8f9a0b1c2d3'
down_revision = 'd2e3f4a5b6c7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'api_groups',
        sa.Column('parent_id', sa.Integer(),
                  sa.ForeignKey('api_groups.id'), nullable=True,
                  comment='父分组ID，NULL表示顶层分组'),
    )
    op.add_column(
        'case_groups',
        sa.Column('parent_id', sa.Integer(),
                  sa.ForeignKey('case_groups.id'), nullable=True,
                  comment='父分组ID，NULL表示顶层分组'),
    )


def downgrade() -> None:
    op.drop_column('case_groups', 'parent_id')
    op.drop_column('api_groups', 'parent_id')

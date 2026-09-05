"""step_records add pre_process/post_extract/extracted_vars

步骤记录新增 3 列，用于执行报告展示节点的前置处理与响应提取情况：
- pre_process     前置处理快照（执行时规则原文）
- post_extract    后置提取规则快照（执行时规则原文）
- extracted_vars  后置提取实际结果 {name: value}

Revision ID: c6d7e8f9a0b1
Revises: e5f6a7b8c9d0
Create Date: 2026-09-04 10:00:00
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c6d7e8f9a0b1'
down_revision = 'e5f6a7b8c9d0'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('step_records', sa.Column('pre_process', sa.JSON(), nullable=True,
                  comment='前置处理快照：[{type, path, value}]'))
    op.add_column('step_records', sa.Column('post_extract', sa.JSON(), nullable=True,
                  comment='后置提取规则快照：[{name, source, jsonpath, sql, field}]'))
    op.add_column('step_records', sa.Column('extracted_vars', sa.JSON(), nullable=True,
                  comment='后置提取实际结果：{name: value}'))


def downgrade() -> None:
    op.drop_column('step_records', 'extracted_vars')
    op.drop_column('step_records', 'post_extract')
    op.drop_column('step_records', 'pre_process')

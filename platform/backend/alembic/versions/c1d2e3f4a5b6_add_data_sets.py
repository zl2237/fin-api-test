"""add data_sets and data_set_rows

数据驱动测试（周期1+5），设计决策见 docs/specs/data-driven-testing.md
1. data_sets      数据集（项目级共享）：列定义 [{key, label, type}]，key 即执行时变量名
2. data_set_rows  数据集行：一行 = 一次执行的变量组 {列key: 值}，row_index 删行后重排保持连续
3. test_cases + dataset_id        用例绑定数据集（NULL=普通用例）
4. execution_records + dataset_id / dataset_row  执行时的数据集与行快照（失败溯源）

Revision ID: c1d2e3f4a5b6
Revises: a9b0c1d2e3f4
Create Date: 2026-08-24 21:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c1d2e3f4a5b6'
down_revision: Union[str, Sequence[str], None] = 'a9b0c1d2e3f4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. 数据集表
    op.create_table(
        'data_sets',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True, comment='主键ID'),
        sa.Column('project_id', sa.Integer(), sa.ForeignKey('projects.id'), nullable=False, comment='所属项目ID'),
        sa.Column('name', sa.String(100), nullable=False, comment='数据集名称'),
        sa.Column('description', sa.Text(), nullable=True, comment='描述'),
        sa.Column('columns', sa.JSON(), nullable=True, comment='列定义：[{key, label, type}]，key 即执行时变量名'),
        sa.Column('created_at', sa.DateTime(), nullable=True, comment='创建时间'),
        sa.Column('updated_at', sa.DateTime(), nullable=True, comment='最近更新时间'),
        sa.Column('created_by', sa.Integer(), nullable=True, comment='创建人 user_id'),
        sa.Column('updated_by', sa.Integer(), nullable=True, comment='更新人 user_id'),
        comment='数据集（项目级共享）：数据驱动测试的多组数据容器',
        mysql_charset='utf8mb4',
    )
    op.create_index('ix_data_sets_id', 'data_sets', ['id'])
    op.create_index('ix_data_sets_project_id', 'data_sets', ['project_id'])

    # 2. 数据集行表
    op.create_table(
        'data_set_rows',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True, comment='主键ID'),
        sa.Column('dataset_id', sa.Integer(), sa.ForeignKey('data_sets.id'), nullable=False, comment='所属数据集ID'),
        sa.Column('row_index', sa.Integer(), nullable=False, comment='行序（1 起，删行后重排保持连续）'),
        sa.Column('data', sa.JSON(), nullable=True, comment='行数据：{列key: 值}'),
        comment='数据集行：一行 = 一次执行的变量组',
        mysql_charset='utf8mb4',
    )
    op.create_index('ix_data_set_rows_id', 'data_set_rows', ['id'])
    op.create_index('ix_data_set_rows_dataset_id', 'data_set_rows', ['dataset_id'])

    # 3. 用例绑定数据集（周期6 的绑定 API 依赖此列）
    op.add_column('test_cases', sa.Column(
        'dataset_id', sa.Integer(), sa.ForeignKey('data_sets.id'), nullable=True,
        comment='绑定的数据集ID，NULL=普通用例；绑定时执行按数据行展开（数据驱动）'))

    # 4. 执行记录快照（周期5：每行一条记录，dataset_row 不回写不更新）
    #    dataset_id 为纯溯源编号不加外键：历史记录靠 dataset_row JSON 自包含，
    #    数据集删除不因执行记录引用被外键卡住（与"快照解耦"定案一致）
    op.add_column('execution_records', sa.Column(
        'dataset_id', sa.Integer(), nullable=True,
        comment='执行时使用的数据集ID（快照解耦：纯溯源编号，无外键，数据集可删；数据以 dataset_row 为准）'))
    op.add_column('execution_records', sa.Column(
        'dataset_row', sa.JSON(), nullable=True,
        comment='该次执行对应的数据行快照：{row_index, data, label}，不回写不更新'))


def downgrade() -> None:
    op.drop_column('execution_records', 'dataset_row')
    op.drop_column('execution_records', 'dataset_id')
    op.drop_column('test_cases', 'dataset_id')
    op.drop_index('ix_data_set_rows_dataset_id', table_name='data_set_rows')
    op.drop_index('ix_data_set_rows_id', table_name='data_set_rows')
    op.drop_table('data_set_rows')
    op.drop_index('ix_data_sets_project_id', table_name='data_sets')
    op.drop_index('ix_data_sets_id', table_name='data_sets')
    op.drop_table('data_sets')

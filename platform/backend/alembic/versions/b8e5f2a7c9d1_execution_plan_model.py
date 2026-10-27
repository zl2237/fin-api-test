"""execution_plan_model

执行方案实体：新增 execution_plans / execution_plan_items 两表（选用例+成员级数据集换绑/次数+
内嵌定时），execution_records 加 plan_id 溯源列（无外键，方案可删、执行历史存活）。
与 fin-ui-test 同构，差异：API 平台数据集为单套语义（恒第 1 行），items 无 dataset_row_index 列。

Revision ID: b8e5f2a7c9d1
Revises: dd77ee88ff99
Create Date: 2026-10-27 16:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'b8e5f2a7c9d1'
down_revision: Union[str, Sequence[str], None] = 'dd77ee88ff99'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('execution_plans',
        sa.Column('id', sa.Integer(), nullable=False, comment='主键ID'),
        sa.Column('project_id', sa.Integer(), nullable=True, comment='所属项目ID'),
        sa.Column('name', sa.String(length=200), nullable=False, comment='方案名称'),
        sa.Column('description', sa.Text(), nullable=True, comment='方案描述'),
        sa.Column('concurrency', sa.Integer(), nullable=False, server_default='4',
                  comment='执行并发数（1~16，提交线程池 max_workers）'),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default='1',
                  comment='方案总开关：禁用时定时触发跳过本轮（手动一键不受限）'),
        sa.Column('schedule_type', sa.String(length=20), nullable=True,
                  comment='调度类型：interval 间隔分钟 / daily 每日固定时刻；NULL=未配置定时'),
        sa.Column('schedule_interval_minutes', sa.Integer(), nullable=True,
                  comment='interval 类型：间隔分钟数（≥1）'),
        sa.Column('schedule_daily_time', sa.String(length=5), nullable=True,
                  comment='daily 类型：每日执行时刻 HH:MM（24小时制）'),
        sa.Column('schedule_enabled', sa.Boolean(), nullable=False, server_default='1',
                  comment='定时启停（schedule_type 非空才有意义；关闭时调度器跳过本轮）'),
        sa.Column('last_run_at', sa.DateTime(), nullable=True, comment='最近一次执行时间（手动/定时均回写）'),
        sa.Column('next_run_at', sa.DateTime(), nullable=True, comment='下次预计触发时间（调度器计算，冗余展示用）'),
        sa.Column('created_at', sa.DateTime(), nullable=True, comment='创建时间'),
        sa.Column('updated_at', sa.DateTime(), nullable=True, comment='最近更新时间'),
        sa.Column('created_by', sa.Integer(), nullable=True, comment='创建人 user_id'),
        sa.Column('updated_by', sa.Integer(), nullable=True, comment='更新人 user_id'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
        sa.PrimaryKeyConstraint('id'))
    op.create_index(op.f('ix_execution_plans_id'), 'execution_plans', ['id'], unique=False)

    op.create_table('execution_plan_items',
        sa.Column('id', sa.Integer(), nullable=False, comment='主键ID'),
        sa.Column('plan_id', sa.Integer(), nullable=False, comment='所属方案ID'),
        sa.Column('case_id', sa.Integer(), nullable=False,
                  comment='成员用例ID（普通用例或套件均可；可跨项目引用，删除成员用例时级联清理本行）'),
        sa.Column('dataset_id', sa.Integer(), nullable=True,
                  comment='成员级数据集换绑（须属于该成员用例；NULL=用例自身绑定；纯引用无外键，悬空在执行预检报错）'),
        sa.Column('run_count', sa.Integer(), nullable=False, server_default='1', comment='该成员执行次数（1~9999）'),
        sa.Column('sort_order', sa.Integer(), nullable=False, comment='成员顺序（展示/执行提交序；并行语义下仅影响记录生成序）'),
        sa.ForeignKeyConstraint(['plan_id'], ['execution_plans.id'], ),
        sa.ForeignKeyConstraint(['case_id'], ['test_cases.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'))
    op.create_index(op.f('ix_execution_plan_items_id'), 'execution_plan_items', ['id'], unique=False)
    op.create_index(op.f('ix_execution_plan_items_plan_id'), 'execution_plan_items', ['plan_id'], unique=False)

    # 执行记录溯源列：纯编号无外键（方案删除后执行历史存活，同 dataset_id/suite_execution_id 惯例）
    op.add_column('execution_records', sa.Column('plan_id', sa.Integer(), nullable=True,
                  comment='执行方案来源：非空表示由方案触发（一键/定时，含方案内套件成员）；纯溯源编号无外键，方案可删，展示时尽力回查名称'))
    op.create_index(op.f('ix_execution_records_plan_id'), 'execution_records', ['plan_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_execution_records_plan_id'), table_name='execution_records')
    op.drop_column('execution_records', 'plan_id')
    # drop_table 连表带索引与 FK 一起删；单独 drop plan_id 索引会被 MySQL 拒（FK 依赖该索引）
    op.drop_table('execution_plan_items')
    op.drop_table('execution_plans')

"""add test_schedules and execution trigger_type

定时任务功能两张变更：
1. 新建 test_schedules 表：用例定时任务（interval 间隔分钟 / daily 每日固定时刻）
   - 设计决策见 app/services/scheduler.py 模块注释（grilling 定稿）
2. execution_records 加 trigger_type 字段：manual 手动 / schedule 定时，
   区分执行记录来源，前端执行列表可按来源筛选展示

Revision ID: a9b0c1d2e3f4
Revises: b8d9e0f1a2c3
Create Date: 2026-08-20 21:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a9b0c1d2e3f4'
down_revision: Union[str, Sequence[str], None] = 'b8d9e0f1a2c3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. 执行记录来源：manual 手动（默认）/ schedule 定时任务
    op.add_column(
        'execution_records',
        sa.Column('trigger_type', sa.String(20), nullable=False, server_default='manual',
                  comment='触发方式：manual 手动 / schedule 定时任务'),
    )

    # 2. 定时任务表
    op.create_table(
        'test_schedules',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True, comment='主键ID'),
        sa.Column('case_id', sa.Integer(), sa.ForeignKey('test_cases.id'), nullable=False, comment='所属用例ID'),
        sa.Column('env_id', sa.Integer(), sa.ForeignKey('environments.id'), nullable=False, comment='执行环境ID'),
        sa.Column('schedule_type', sa.String(20), nullable=False, comment='调度类型：interval 间隔分钟 / daily 每日固定时刻'),
        sa.Column('interval_minutes', sa.Integer(), nullable=True, comment='interval 类型：间隔分钟数（≥1）'),
        sa.Column('daily_time', sa.String(5), nullable=True, comment='daily 类型：每日执行时刻 HH:MM（24小时制）'),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default=sa.text('1'),
                  comment='是否启用'),
        sa.Column('last_run_at', sa.DateTime(), nullable=True, comment='最近一次实际触发时间'),
        sa.Column('next_run_at', sa.DateTime(), nullable=True, comment='下次预计触发时间（调度器计算，冗余展示用）'),
        sa.Column('created_at', sa.DateTime(), nullable=True, comment='创建时间'),
        sa.Column('updated_at', sa.DateTime(), nullable=True, comment='最近更新时间'),
        sa.Column('created_by', sa.Integer(), nullable=True, comment='创建人 user_id'),
        sa.Column('updated_by', sa.Integer(), nullable=True, comment='更新人 user_id'),
        mysql_charset='utf8mb4',
    )
    op.create_index('ix_test_schedules_id', 'test_schedules', ['id'])
    op.create_index('ix_test_schedules_case_id', 'test_schedules', ['case_id'])


def downgrade() -> None:
    op.drop_index('ix_test_schedules_case_id', table_name='test_schedules')
    op.drop_index('ix_test_schedules_id', table_name='test_schedules')
    op.drop_table('test_schedules')
    op.drop_column('execution_records', 'trigger_type')

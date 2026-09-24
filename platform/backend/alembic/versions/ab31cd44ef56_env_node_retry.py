"""环境节点失败重试配置 + 步骤重试次数列

Revision ID: ab31cd44ef56
Revises: dd44ee55ff66
Create Date: 2026-09-24

被测系统存在分钟级异步同步（如 ES 费用数据）场景：节点执行时业务系统尚未
同步完成返回 406，稍后重发同一请求即可成功。环境级「失败重试次数 + 重试间隔」
让执行引擎在此类瞬时异常下自动重试；step_records.retry_count 记录实际重试
次数（0/NULL=未重试），报告页可辨识「重试后成功」。
"""
from alembic import op
import sqlalchemy as sa

revision = "ab31cd44ef56"
down_revision = "dd44ee55ff66"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "environments",
        sa.Column("node_retry_count", sa.Integer(), nullable=False, server_default="0",
                  comment="节点请求层失败自动重试次数（0=不重试；仅 HTTP 状态码/业务码失败、超时、连接异常触发，断言失败不重试）"),
    )
    op.add_column(
        "environments",
        sa.Column("node_retry_interval", sa.Integer(), nullable=False, server_default="1",
                  comment="节点重试间隔（秒），两次尝试之间的等待时间"),
    )
    op.add_column(
        "step_records",
        sa.Column("retry_count", sa.Integer(), nullable=True,
                  comment="环境级失败重试实际发生的次数（0/NULL=未重试；仅请求层失败触发）"),
    )


def downgrade() -> None:
    op.drop_column("step_records", "retry_count")
    op.drop_column("environments", "node_retry_interval")
    op.drop_column("environments", "node_retry_count")

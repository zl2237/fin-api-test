"""断点续跑：编排结构指纹 + 步骤续跑/重放通过标记

Revision ID: c2e9f8a4b6d8
Revises: ab31cd44ef56
Create Date: 2026-09-24

断点续跑设计定稿（报告页调试循环）：
- execution_records.orchestration_fingerprint：执行时写入结构级指纹
  （节点/边/接口绑定，不含参数配置）；续跑前重算比对，结构变了拒绝。
  参数配置（pre_process 等）刻意不入指纹——改参数后续跑用当前配置，
  正是「改完参数不用整个重跑」的核心场景。
- step_records.resumed：续跑段产出的步骤标记（同 node 重跑成功顶替旧失败记录）
- step_records.replay_passed_at：手改请求体重放断言全过时打点，
  报告页显示「已重放通过」徽标，不改变步骤内容。
"""
from alembic import op
import sqlalchemy as sa

revision = "c2e9f8a4b6d8"
down_revision = "ab31cd44ef56"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "execution_records",
        sa.Column("orchestration_fingerprint", sa.String(64), nullable=True,
                  comment="编排结构指纹（执行时快照：节点/边/接口绑定，不含参数配置）；续跑前重算比对，结构变了拒绝续跑；旧报告 NULL=不可续跑"),
    )
    op.add_column(
        "step_records",
        sa.Column("resumed", sa.Boolean(), nullable=False, server_default="0",
                  comment="断点续跑标记：本步骤由续跑段产出（同 node 重跑成功后顶替旧失败记录）"),
    )
    op.add_column(
        "step_records",
        sa.Column("replay_passed_at", sa.DateTime(), nullable=True,
                  comment="重放验证通过时间：手改请求体重放断言全过时打点，报告页显示「已重放通过」徽标；不改变步骤内容"),
    )


def downgrade() -> None:
    op.drop_column("step_records", "replay_passed_at")
    op.drop_column("step_records", "resumed")
    op.drop_column("execution_records", "orchestration_fingerprint")

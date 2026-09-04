"""测试套件：用例类型列 + 共享变量白名单 + 套件成员表 + 执行记录套件来源

Revision ID: e9f0a1b2c3d4
Revises: d8e9f0a1b2c3
Create Date: 2026-09-04

跨系统用例链（如 物流系统"融资数据" → 亿海融"发起融资"）：
- test_cases.case_type 区分普通 DAG 用例（normal）与套件（suite），
  套件复用用例的分组/复制/定时/批量执行等全部管理能力
- test_cases.shared_vars 共享变量白名单：上游成员行结束按名单快照，
  下游以最高优先级注入（套件执行时），单独执行用例不受影响
- suite_members 有序成员引用（可跨项目，逐成员绑定环境，串行执行）
- execution_records.suite_execution_id 标记套件链成员执行的来源
"""
import sqlalchemy as sa
from alembic import op

revision = "e9f0a1b2c3d4"
down_revision = "d8e9f0a1b2c3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "test_cases",
        sa.Column("case_type", sa.String(20), nullable=False, server_default="normal",
                  comment="用例类型：normal 普通 DAG 用例 / suite 套件（成员为其他用例的跨系统链）"),
    )
    op.add_column(
        "test_cases",
        sa.Column("shared_vars", sa.JSON(), nullable=True,
                  comment="套件专用：共享变量白名单，上游成员行执行结束时按名单快照，下游成员执行时以最高优先级注入变量池"),
    )
    op.add_column(
        "execution_records",
        sa.Column("suite_execution_id", sa.Integer(), nullable=True,
                  comment="套件来源：非空表示本记录是套件链中某成员的一次执行，指向套件主执行记录ID"),
    )
    op.create_index(op.f("ix_execution_records_suite_execution_id"),
                    "execution_records", ["suite_execution_id"])
    op.create_table(
        "suite_members",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, comment="主键ID"),
        sa.Column("suite_case_id", sa.Integer(), sa.ForeignKey("test_cases.id"), nullable=False,
                  comment="套件用例ID（case_type=suite）"),
        sa.Column("member_case_id", sa.Integer(), sa.ForeignKey("test_cases.id"), nullable=False,
                  comment="成员用例ID（可跨项目；禁止引用套件自身形成环）"),
        sa.Column("env_id", sa.Integer(), sa.ForeignKey("environments.id"), nullable=False,
                  comment="该成员执行所用环境ID"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0",
                  comment="执行顺序（0 起，串行）"),
        comment="套件成员：套件用例到成员用例的有序引用（跨项目，逐成员绑定环境）",
    )
    op.create_index(op.f("ix_suite_members_suite_case_id"), "suite_members", ["suite_case_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_suite_members_suite_case_id"), table_name="suite_members")
    op.drop_table("suite_members")
    op.drop_index(op.f("ix_execution_records_suite_execution_id"), table_name="execution_records")
    op.drop_column("execution_records", "suite_execution_id")
    op.drop_column("test_cases", "shared_vars")
    op.drop_column("test_cases", "case_type")

"""B3 删链与多选数据集绑定（2026-11-12）

- data_sets.bound：绑定标志（多选绑定取代 test_cases.dataset_id 单选）
- execution_plan_items.dataset_ids JSON 取代 dataset_id 单列；pass_vars 随链删
- execution_plans.mode/rounds 随链删（方案只保留并行组合语义）
- 数据迁移：bound = 曾被 test_cases.dataset_id 引用；dataset_ids = [旧 dataset_id]
- test_cases.dataset_id（FK，自动命名约束）按 information_schema 探名后删

Revision ID: b3a4b5c6d7e8
Revises: a1b2c3d4e5f7
Create Date: 2026-11-12
"""
from alembic import op
import sqlalchemy as sa

revision = 'b3a4b5c6d7e8'
down_revision = 'a1b2c3d4e5f7'
branch_labels = None
depends_on = None


def _fk_name(bind, table: str, column: str) -> str | None:
    """从 information_schema 探自动命名的 FK 约束名（MySQL）。"""
    row = bind.execute(sa.text(
        "SELECT CONSTRAINT_NAME FROM information_schema.KEY_COLUMN_USAGE "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t AND COLUMN_NAME = :c "
        "AND REFERENCED_TABLE_NAME IS NOT NULL LIMIT 1"), {"t": table, "c": column}).fetchone()
    return row[0] if row else None


def upgrade() -> None:
    # 1) data_sets.bound + 回填（曾绑定即置位）
    op.add_column('data_sets', sa.Column('bound', sa.Boolean(), nullable=False,
                                         server_default=sa.text('0')))
    op.execute(sa.text(
        "UPDATE data_sets SET bound = 1 "
        "WHERE id IN (SELECT dataset_id FROM test_cases WHERE dataset_id IS NOT NULL)"))

    # 2) execution_plan_items.dataset_ids JSON + 回填
    op.add_column('execution_plan_items',
                  sa.Column('dataset_ids', sa.JSON(), nullable=True))
    op.execute(sa.text(
        "UPDATE execution_plan_items SET dataset_ids = JSON_ARRAY(dataset_id) "
        "WHERE dataset_id IS NOT NULL"))

    # 3) 列清理（test_cases.dataset_id 先探 FK 名再删列）
    bind = op.get_bind()
    fk = _fk_name(bind, 'test_cases', 'dataset_id')
    if fk:
        op.drop_constraint(fk, 'test_cases', type_='foreignkey')
    op.drop_column('test_cases', 'dataset_id')
    op.drop_column('execution_plan_items', 'dataset_id')
    op.drop_column('execution_plan_items', 'pass_vars')
    op.drop_column('execution_plans', 'mode')
    op.drop_column('execution_plans', 'rounds')


def downgrade() -> None:
    """尽力回滚：多选信息有损（每用例只回填最早绑定的数据集）。"""
    op.add_column('execution_plans', sa.Column('mode', sa.String(20), nullable=False,
                                               server_default='combo'))
    op.add_column('execution_plans', sa.Column('rounds', sa.Integer(), nullable=False,
                                               server_default=sa.text('1')))
    op.add_column('execution_plan_items', sa.Column('dataset_id', sa.Integer(), nullable=True))
    op.add_column('execution_plan_items', sa.Column('pass_vars', sa.JSON(), nullable=True))
    op.execute(sa.text(
        "UPDATE execution_plan_items SET dataset_id = CAST(JSON_UNQUOTE(JSON_EXTRACT("
        "dataset_ids, '$[0]')) AS UNSIGNED) WHERE JSON_LENGTH(dataset_ids) > 0"))
    op.add_column('test_cases', sa.Column('dataset_id', sa.Integer(),
                                          sa.ForeignKey('data_sets.id'), nullable=True))
    op.execute(sa.text(
        "UPDATE test_cases tc SET dataset_id = ("
        "  SELECT MIN(ds.id) FROM data_sets ds WHERE ds.case_id = tc.id AND ds.bound = 1) "
        "WHERE EXISTS (SELECT 1 FROM data_sets ds WHERE ds.case_id = tc.id AND ds.bound = 1)"))
    op.drop_column('data_sets', 'bound')

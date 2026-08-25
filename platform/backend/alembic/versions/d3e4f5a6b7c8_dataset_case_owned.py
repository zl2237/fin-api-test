"""dataset refactor: case-level ownership + node config snapshot

数据集概念重构（docs/specs/data-driven-testing.md）：
1. data_sets.case_id      归属用例（1:N，用例间隔离，复用靠复制）；project_id 降级为冗余
2. data_sets.node_configs 编排配置快照（前置/后置/断言按节点），执行时整块覆盖用例节点配置
3. columns[].label 废除：列中文名实时引用项目字段字典（FieldDictionary），不再落库快照

存量迁移（33 个）：
- 被用例绑定的（test_cases.dataset_id）→ 归绑定用例
- 名字以「{用例名}-参数集」结尾/前缀匹配源用例的 → 归源用例
- 其余（手建未绑定）→ 删除（连同行数据，定案：未绑定的直接删）

Revision ID: d3e4f5a6b7c8
Revises: 9555ad43e3ac
Create Date: 2026-08-25 10:00:00.000000
"""
import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'd3e4f5a6b7c8'
down_revision: Union[str, Sequence[str], None] = 'c1d2e3f4a5b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    # 1. 新列（先 nullable，数据回填后再收紧）
    op.add_column('data_sets', sa.Column(
        'case_id', sa.Integer(), sa.ForeignKey('test_cases.id'), nullable=True,
        comment='归属用例ID（1:N，用例间隔离）'))
    op.add_column('data_sets', sa.Column(
        'node_configs', sa.JSON(), nullable=True,
        comment='编排配置快照：[{node_id, api_id, pre_process, post_extract, assertions, wait_after_ms}]，执行时整块覆盖用例节点配置'))
    op.create_index('ix_data_sets_case_id', 'data_sets', ['case_id'])

    # 2. 存量归属迁移
    cases = bind.execute(sa.text(
        "SELECT id, project_id, name FROM test_cases")).fetchall()
    bound_map = dict(bind.execute(sa.text(
        "SELECT dataset_id, id FROM test_cases WHERE dataset_id IS NOT NULL")).fetchall())

    def match_case_by_name(ds_name: str, project_id):
        # 「{用例名}-参数集」生成命名回溯（支持截断后缀「…-参数集」）
        for cid, pid, cname in cases:
            if pid != project_id:
                continue
            if ds_name == f"{cname}-参数集" or ds_name.endswith("…-参数集") and ds_name.startswith(cname[:10]):
                return cid
        return None

    to_delete = []
    for ds_id, ds_project, ds_name in bind.execute(
            sa.text("SELECT id, project_id, name FROM data_sets")).fetchall():
        target = bound_map.get(ds_id) or match_case_by_name(ds_name, ds_project)
        if target:
            bind.execute(sa.text(
                "UPDATE data_sets SET case_id = :cid WHERE id = :did"),
                {"cid": target, "did": ds_id})
        else:
            to_delete.append(ds_id)
    if to_delete:
        ids = ",".join(str(i) for i in to_delete)
        bind.execute(sa.text(f"DELETE FROM data_set_rows WHERE dataset_id IN ({ids})"))
        bind.execute(sa.text(f"DELETE FROM data_sets WHERE id IN ({ids})"))
        # 指向已删数据集的用例绑定清空
        bind.execute(sa.text(
            "UPDATE test_cases SET dataset_id = NULL WHERE dataset_id IS NOT NULL "
            "AND dataset_id NOT IN (SELECT id FROM data_sets)"))

    # 3. case_id 收紧 NOT NULL
    op.alter_column('data_sets', 'case_id', existing_type=sa.Integer(), nullable=False)

    # 4. 列定义剥离 label（中文名改为实时引用字段字典）
    for ds_id, cols_json in bind.execute(
            sa.text("SELECT id, columns FROM data_sets WHERE columns IS NOT NULL")).fetchall():
        cols = json.loads(cols_json) if isinstance(cols_json, str) else (cols_json or [])
        stripped = [{k: v for k, v in c.items() if k != "label"} for c in cols]
        bind.execute(sa.text("UPDATE data_sets SET columns = :cols WHERE id = :did"),
                     {"cols": json.dumps(stripped, ensure_ascii=False), "did": ds_id})

    # 5. node_configs 回填空数组（响应 schema 要求 list，NULL 会导致接口 500）
    bind.execute(sa.text("UPDATE data_sets SET node_configs = '[]' WHERE node_configs IS NULL"))

    # 6. 注释同步
    op.alter_column('data_sets', 'project_id', existing_type=sa.Integer(),
                    comment='所属项目ID（冗余，归属以 case_id 为准）')
    op.alter_column('data_sets', 'columns', existing_type=sa.JSON(),
                    comment='列定义：[{key, type}]，key 即执行时变量名；中文名实时引用字段字典')


def downgrade() -> None:
    op.drop_index('ix_data_sets_case_id', table_name='data_sets')
    op.drop_column('data_sets', 'node_configs')
    op.drop_column('data_sets', 'case_id')

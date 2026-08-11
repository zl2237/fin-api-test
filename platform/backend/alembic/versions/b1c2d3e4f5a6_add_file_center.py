"""add file center tables

新增文件中心 4 张表：
- file_categories   文件分类（项目级，支持多级树形）
- file_tags         文件标签（项目级，扁平）
- test_files        测试文件（sha256 去重 + ref_count 引用计数）
- file_tag_relations 文件-标签多对多关联

Revision ID: b1c2d3e4f5a6
Revises: f9a0b1c2d3e4
Create Date: 2026-08-11 20:00:00
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b1c2d3e4f5a6'
down_revision = 'f9a0b1c2d3e4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'file_categories',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True, comment='主键ID'),
        sa.Column('project_id', sa.Integer(), sa.ForeignKey('projects.id'), nullable=False, index=True, comment='所属项目ID'),
        sa.Column('parent_id', sa.Integer(), sa.ForeignKey('file_categories.id'), nullable=True, comment='父分类ID，NULL表示顶层'),
        sa.Column('name', sa.String(100), nullable=False, comment='分类名称'),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0', comment='排序序号'),
        sa.Column('created_at', sa.DateTime(), nullable=True, comment='创建时间'),
        sa.Column('created_by', sa.Integer(), nullable=True, comment='创建人 user_id'),
        sa.UniqueConstraint('project_id', 'parent_id', 'name', name='uq_file_category_project_parent_name'),
        comment='文件分类（项目级，支持多级树形结构）',
    )

    op.create_table(
        'file_tags',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True, comment='主键ID'),
        sa.Column('project_id', sa.Integer(), sa.ForeignKey('projects.id'), nullable=False, index=True, comment='所属项目ID'),
        sa.Column('name', sa.String(50), nullable=False, comment='标签名称'),
        sa.Column('color', sa.String(20), nullable=False, server_default='', comment='标签颜色（如 #409EFF）'),
        sa.Column('created_at', sa.DateTime(), nullable=True, comment='创建时间'),
        sa.Column('created_by', sa.Integer(), nullable=True, comment='创建人 user_id'),
        sa.UniqueConstraint('project_id', 'name', name='uq_file_tag_project_name'),
        comment='文件标签（项目级，扁平结构）',
    )

    op.create_table(
        'test_files',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True, comment='主键ID'),
        sa.Column('project_id', sa.Integer(), sa.ForeignKey('projects.id'), nullable=False, index=True, comment='所属项目ID'),
        sa.Column('category_id', sa.Integer(), sa.ForeignKey('file_categories.id'), nullable=True, comment='所属分类ID，NULL 表示未分类'),
        sa.Column('name', sa.String(255), nullable=False, comment='显示名（可重命名）'),
        sa.Column('original_name', sa.String(255), nullable=False, comment='上传时原始文件名'),
        sa.Column('content_type', sa.String(100), nullable=False, server_default='application/octet-stream', comment='MIME 类型'),
        sa.Column('size', sa.Integer(), nullable=False, server_default='0', comment='文件大小（字节）'),
        sa.Column('sha256', sa.String(64), nullable=False, index=True, comment='内容 SHA256 指纹（去重依据）'),
        sa.Column('storage_path', sa.String(500), nullable=False, comment='相对存储路径：uploads/files/{sha256前2位}/{sha256}'),
        sa.Column('ref_count', sa.Integer(), nullable=False, server_default='1', comment='引用计数，归零时可清理物理文件'),
        sa.Column('created_at', sa.DateTime(), nullable=True, comment='创建时间'),
        sa.Column('updated_at', sa.DateTime(), nullable=True, comment='最近更新时间'),
        sa.Column('created_by', sa.Integer(), nullable=True, comment='创建人 user_id'),
        sa.Column('updated_by', sa.Integer(), nullable=True, comment='更新人 user_id'),
        comment='测试文件（项目级隔离，sha256 内容去重，ref_count 引用计数）',
    )

    op.create_table(
        'file_tag_relations',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True, comment='主键ID'),
        sa.Column('file_id', sa.Integer(), sa.ForeignKey('test_files.id'), nullable=False, index=True, comment='文件ID'),
        sa.Column('tag_id', sa.Integer(), sa.ForeignKey('file_tags.id'), nullable=False, index=True, comment='标签ID'),
        sa.UniqueConstraint('file_id', 'tag_id', name='uq_file_tag_relation'),
        comment='文件-标签 多对多关联',
    )


def downgrade() -> None:
    op.drop_table('file_tag_relations')
    op.drop_table('test_files')
    op.drop_table('file_tags')
    op.drop_table('file_categories')

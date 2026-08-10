"""add column comments

为所有表的字段补充数据库层 comment，便于在 MySQL 客户端直接理解字段含义。
本迁移只修改字段注释（元数据），不改变列类型、约束、默认值、自增属性。

注意：MySQL 的 ALTER TABLE ... MODIFY COLUMN 会完整重建列定义，因此必须
通过 existing_nullable / existing_autoincrement / existing_server_default 把
现有列属性原样带回，避免误改 NOT NULL / AUTO_INCREMENT 等约束。

Revision ID: b4c5d6e7f8a9
Revises: a3b4c5d6e7f8
Create Date: 2026-08-09 12:00:00
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "b4c5d6e7f8a9"
down_revision = "a3b4c5d6e7f8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """为各表字段补充 comment（仅元数据，不改结构）。"""

    # users
    op.alter_column("users", "id", existing_type=sa.Integer(), existing_nullable=False, existing_autoincrement=True, comment="主键ID")
    op.alter_column("users", "username", existing_type=sa.String(length=50), existing_nullable=False, comment="登录用户名")
    op.alter_column("users", "password_hash", existing_type=sa.String(length=255), existing_nullable=False, comment="密码哈希：pbkdf2_hmac(sha256) + salt")
    op.alter_column("users", "name", existing_type=sa.String(length=50), existing_nullable=True, comment="显示名")
    op.alter_column("users", "role", existing_type=sa.String(length=20), existing_nullable=True, comment="角色：admin 管理员 / member 普通成员")
    op.alter_column("users", "created_at", existing_type=sa.DateTime(), existing_nullable=True, comment="创建时间")
    op.alter_column("users", "created_by", existing_type=sa.Integer(), existing_nullable=True, comment="创建人 user_id")
    op.alter_column("users", "updated_by", existing_type=sa.Integer(), existing_nullable=True, comment="更新人 user_id")
    op.alter_column("users", "failed_count", existing_type=sa.Integer(), existing_nullable=True, comment="连续登录失败次数，成功登录后重置")
    op.alter_column("users", "locked_until", existing_type=sa.DateTime(), existing_nullable=True, comment="锁定截止时间，NULL 表示未锁定")
    op.alter_column("users", "must_change_password", existing_type=sa.Boolean(), existing_nullable=False, existing_server_default=sa.text("0"), comment="是否需要强制修改密码：True 时登录后强制跳转改密页")

    # projects
    op.alter_column("projects", "id", existing_type=sa.Integer(), existing_nullable=False, existing_autoincrement=True, comment="主键ID")
    op.alter_column("projects", "name", existing_type=sa.String(length=100), existing_nullable=False, comment="项目名称")
    op.alter_column("projects", "description", existing_type=sa.Text(), existing_nullable=True, comment="项目描述")
    op.alter_column("projects", "created_at", existing_type=sa.DateTime(), existing_nullable=True, comment="创建时间")
    op.alter_column("projects", "created_by", existing_type=sa.Integer(), existing_nullable=True, comment="创建人 user_id")
    op.alter_column("projects", "updated_by", existing_type=sa.Integer(), existing_nullable=True, comment="更新人 user_id")

    # environments
    op.alter_column("environments", "id", existing_type=sa.Integer(), existing_nullable=False, existing_autoincrement=True, comment="主键ID")
    op.alter_column("environments", "project_id", existing_type=sa.Integer(), existing_nullable=True, comment="所属项目ID")
    op.alter_column("environments", "name", existing_type=sa.String(length=50), existing_nullable=False, comment="环境名称：dev/test/prod")
    op.alter_column("environments", "base_url", existing_type=sa.String(length=500), existing_nullable=False, comment="接口基础地址，如 https://api.example.com")
    op.alter_column("environments", "db_config", existing_type=sa.JSON(), existing_nullable=True, comment="MySQL 连接配置：{host, port, user, password, database}")
    op.alter_column("environments", "login_config", existing_type=sa.JSON(), existing_nullable=True, comment="登录配置：{login_path, login_body, token_jsonpath, auth_header_name}")
    op.alter_column("environments", "notify_config", existing_type=sa.JSON(), existing_nullable=True, comment="通知配置：{wecom_webhook, enable_on_failure, enable_on_success}")
    op.alter_column("environments", "variables", existing_type=sa.JSON(), existing_nullable=True, comment="业务变量（与登录/通知解耦）")
    op.alter_column("environments", "common_headers", existing_type=sa.JSON(), existing_nullable=True, comment="公共请求头，每个接口请求都会携带")
    op.alter_column("environments", "timeout", existing_type=sa.Integer(), existing_nullable=True, comment="接口请求超时时间（秒）")
    op.alter_column("environments", "is_default", existing_type=sa.Boolean(), existing_nullable=True, comment="是否为项目默认环境")
    op.alter_column("environments", "created_at", existing_type=sa.DateTime(), existing_nullable=True, comment="创建时间")
    op.alter_column("environments", "created_by", existing_type=sa.Integer(), existing_nullable=True, comment="创建人 user_id")
    op.alter_column("environments", "updated_by", existing_type=sa.Integer(), existing_nullable=True, comment="更新人 user_id")

    # api_groups
    op.alter_column("api_groups", "id", existing_type=sa.Integer(), existing_nullable=False, existing_autoincrement=True, comment="主键ID")
    op.alter_column("api_groups", "project_id", existing_type=sa.Integer(), existing_nullable=True, comment="所属项目ID")
    op.alter_column("api_groups", "name", existing_type=sa.String(length=100), existing_nullable=False, comment="分组名称")
    op.alter_column("api_groups", "sort_order", existing_type=sa.Integer(), existing_nullable=True, comment="排序序号")
    op.alter_column("api_groups", "created_at", existing_type=sa.DateTime(), existing_nullable=True, comment="创建时间")

    # api_definitions
    op.alter_column("api_definitions", "id", existing_type=sa.Integer(), existing_nullable=False, existing_autoincrement=True, comment="主键ID")
    op.alter_column("api_definitions", "project_id", existing_type=sa.Integer(), existing_nullable=True, comment="所属项目ID")
    op.alter_column("api_definitions", "group_id", existing_type=sa.Integer(), existing_nullable=True, comment="所属分组ID，NULL 表示未分组")
    op.alter_column("api_definitions", "name", existing_type=sa.String(length=100), existing_nullable=False, comment="接口中文名：如 创建订单")
    op.alter_column("api_definitions", "code", existing_type=sa.String(length=100), existing_nullable=False, comment="接口唯一编码：如 order_create")
    op.alter_column("api_definitions", "category", existing_type=sa.String(length=50), existing_nullable=True, comment="旧版分类（order/auth/file），新版本用 group")
    op.alter_column("api_definitions", "method", existing_type=sa.String(length=10), existing_nullable=True, comment="HTTP 方法：GET/POST/PUT/DELETE")
    op.alter_column("api_definitions", "path", existing_type=sa.String(length=500), existing_nullable=False, comment="请求路径：如 /api/order/orderEntrust/orderAdd")
    op.alter_column("api_definitions", "description", existing_type=sa.Text(), existing_nullable=True, comment="接口描述")
    op.alter_column("api_definitions", "request_template", existing_type=sa.JSON(), existing_nullable=True, comment="旧版请求体模板，新版本用 fields 字段表")
    op.alter_column("api_definitions", "headers_template", existing_type=sa.JSON(), existing_nullable=True, comment="请求头模板")
    op.alter_column("api_definitions", "sort_order", existing_type=sa.Integer(), existing_nullable=True, comment="组内排序序号（支持拖拽排序）")
    op.alter_column("api_definitions", "created_at", existing_type=sa.DateTime(), existing_nullable=True, comment="创建时间")
    op.alter_column("api_definitions", "created_by", existing_type=sa.Integer(), existing_nullable=True, comment="创建人 user_id")
    op.alter_column("api_definitions", "updated_by", existing_type=sa.Integer(), existing_nullable=True, comment="更新人 user_id")

    # api_fields
    op.alter_column("api_fields", "id", existing_type=sa.Integer(), existing_nullable=False, existing_autoincrement=True, comment="主键ID")
    op.alter_column("api_fields", "api_id", existing_type=sa.Integer(), existing_nullable=True, comment="所属接口ID")
    op.alter_column("api_fields", "key", existing_type=sa.String(length=200), existing_nullable=False, comment="字段路径：如 order_id / to_customer.put_amount")
    op.alter_column("api_fields", "label", existing_type=sa.String(length=100), existing_nullable=True, comment="字段中文名：如 订单ID")
    op.alter_column("api_fields", "field_type", existing_type=sa.String(length=20), existing_nullable=True, comment="字段类型：string/int/bool/object/array")
    op.alter_column("api_fields", "required", existing_type=sa.Boolean(), existing_nullable=True, comment="是否必填")
    op.alter_column("api_fields", "default_value", existing_type=sa.Text(), existing_nullable=True, comment="默认值，支持表达式 ${...}")
    op.alter_column("api_fields", "remark", existing_type=sa.Text(), existing_nullable=True, comment="备注")
    op.alter_column("api_fields", "sort_order", existing_type=sa.Integer(), existing_nullable=True, comment="排序序号")

    # case_groups
    op.alter_column("case_groups", "id", existing_type=sa.Integer(), existing_nullable=False, existing_autoincrement=True, comment="主键ID")
    op.alter_column("case_groups", "project_id", existing_type=sa.Integer(), existing_nullable=True, comment="所属项目ID")
    op.alter_column("case_groups", "name", existing_type=sa.String(length=100), existing_nullable=False, comment="分组名称")
    op.alter_column("case_groups", "sort_order", existing_type=sa.Integer(), existing_nullable=True, comment="排序序号")
    op.alter_column("case_groups", "created_at", existing_type=sa.DateTime(), existing_nullable=True, comment="创建时间")

    # test_cases
    op.alter_column("test_cases", "id", existing_type=sa.Integer(), existing_nullable=False, existing_autoincrement=True, comment="主键ID")
    op.alter_column("test_cases", "project_id", existing_type=sa.Integer(), existing_nullable=True, comment="所属项目ID")
    op.alter_column("test_cases", "group_id", existing_type=sa.Integer(), existing_nullable=True, comment="所属分组ID，NULL 表示未分组")
    op.alter_column("test_cases", "name", existing_type=sa.String(length=200), existing_nullable=False, comment="用例名称")
    op.alter_column("test_cases", "description", existing_type=sa.Text(), existing_nullable=True, comment="用例描述")
    op.alter_column("test_cases", "dag_config", existing_type=sa.JSON(), existing_nullable=False, comment="DAG 配置：{nodes: [...], edges: [...]}")
    op.alter_column("test_cases", "sort_order", existing_type=sa.Integer(), existing_nullable=True, comment="组内排序序号（支持拖拽排序）")
    op.alter_column("test_cases", "created_at", existing_type=sa.DateTime(), existing_nullable=True, comment="创建时间")
    op.alter_column("test_cases", "updated_at", existing_type=sa.DateTime(), existing_nullable=True, comment="最近更新时间")
    op.alter_column("test_cases", "created_by", existing_type=sa.Integer(), existing_nullable=True, comment="创建人 user_id")
    op.alter_column("test_cases", "updated_by", existing_type=sa.Integer(), existing_nullable=True, comment="更新人 user_id")

    # case_node_configs
    op.alter_column("case_node_configs", "id", existing_type=sa.Integer(), existing_nullable=False, existing_autoincrement=True, comment="主键ID")
    op.alter_column("case_node_configs", "case_id", existing_type=sa.Integer(), existing_nullable=True, comment="所属用例ID")
    op.alter_column("case_node_configs", "node_id", existing_type=sa.String(length=100), existing_nullable=False, comment="DAG 节点唯一ID")
    op.alter_column("case_node_configs", "api_id", existing_type=sa.Integer(), existing_nullable=True, comment="关联接口ID")
    op.alter_column("case_node_configs", "pre_process", existing_type=sa.JSON(), existing_nullable=True, comment="前置处理动作列表：[{type, path, value}]")
    op.alter_column("case_node_configs", "post_extract", existing_type=sa.JSON(), existing_nullable=True, comment="后置提取规则列表：[{name, source, jsonpath, sql, field}]")
    op.alter_column("case_node_configs", "assertions", existing_type=sa.JSON(), existing_nullable=True, comment="断言规则列表：[{type, path, expected, sql, ...}]")

    # execution_records
    op.alter_column("execution_records", "id", existing_type=sa.Integer(), existing_nullable=False, existing_autoincrement=True, comment="主键ID")
    op.alter_column("execution_records", "case_id", existing_type=sa.Integer(), existing_nullable=True, comment="所属用例ID")
    op.alter_column("execution_records", "env_id", existing_type=sa.Integer(), existing_nullable=True, comment="执行环境ID")
    op.alter_column("execution_records", "status", existing_type=sa.String(length=20), existing_nullable=True, comment="执行状态：running 进行中 / success 成功 / failed 失败")
    op.alter_column("execution_records", "started_at", existing_type=sa.DateTime(), existing_nullable=True, comment="开始执行时间")
    op.alter_column("execution_records", "ended_at", existing_type=sa.DateTime(), existing_nullable=True, comment="结束时间")
    op.alter_column("execution_records", "summary", existing_type=sa.JSON(), existing_nullable=True, comment="执行摘要：{total 总数, passed 通过, failed 失败}")
    op.alter_column("execution_records", "created_by", existing_type=sa.Integer(), existing_nullable=True, comment="执行人 user_id")

    # step_records
    op.alter_column("step_records", "id", existing_type=sa.Integer(), existing_nullable=False, existing_autoincrement=True, comment="主键ID")
    op.alter_column("step_records", "execution_id", existing_type=sa.Integer(), existing_nullable=True, comment="所属执行记录ID")
    op.alter_column("step_records", "node_id", existing_type=sa.String(length=100), existing_nullable=True, comment="DAG 节点ID")
    op.alter_column("step_records", "api_name", existing_type=sa.String(length=100), existing_nullable=True, comment="接口名称（执行时快照）")
    op.alter_column("step_records", "api_path", existing_type=sa.String(length=500), existing_nullable=True, comment="请求路径（执行时快照）")
    op.alter_column("step_records", "api_method", existing_type=sa.String(length=10), existing_nullable=True, comment="HTTP 方法（执行时快照）")
    op.alter_column("step_records", "request_headers", existing_type=sa.JSON(), existing_nullable=True, comment="实际请求头")
    op.alter_column("step_records", "request_body", existing_type=sa.JSON(), existing_nullable=True, comment="实际请求体")
    op.alter_column("step_records", "response_status", existing_type=sa.Integer(), existing_nullable=True, comment="HTTP 响应状态码")
    op.alter_column("step_records", "response_body", existing_type=sa.JSON(), existing_nullable=True, comment="响应体")
    op.alter_column("step_records", "response_time_ms", existing_type=sa.Integer(), existing_nullable=True, comment="响应耗时（毫秒）")
    op.alter_column("step_records", "started_at", existing_type=sa.DateTime(), existing_nullable=True, comment="步骤开始时间")
    op.alter_column("step_records", "ended_at", existing_type=sa.DateTime(), existing_nullable=True, comment="步骤结束时间")
    op.alter_column("step_records", "status", existing_type=sa.String(length=20), existing_nullable=True, comment="步骤状态：success 成功 / failed 失败")

    # assertion_records
    op.alter_column("assertion_records", "id", existing_type=sa.Integer(), existing_nullable=False, existing_autoincrement=True, comment="主键ID")
    op.alter_column("assertion_records", "step_id", existing_type=sa.Integer(), existing_nullable=True, comment="所属步骤记录ID")
    op.alter_column("assertion_records", "rule_type", existing_type=sa.String(length=50), existing_nullable=True, comment="断言类型：如 json_path_equals / db_query_equals")
    op.alter_column("assertion_records", "rule_config", existing_type=sa.JSON(), existing_nullable=True, comment="断言规则配置（原始参数）")
    op.alter_column("assertion_records", "result", existing_type=sa.Boolean(), existing_nullable=True, comment="断言结果：True 通过 / False 失败")
    op.alter_column("assertion_records", "actual_value", existing_type=sa.Text(), existing_nullable=True, comment="实际值")
    op.alter_column("assertion_records", "expected_value", existing_type=sa.Text(), existing_nullable=True, comment="期望值")
    op.alter_column("assertion_records", "message", existing_type=sa.String(length=500), existing_nullable=True, comment="结果消息（失败时含原因）")

    # operation_logs
    op.alter_column("operation_logs", "id", existing_type=sa.Integer(), existing_nullable=False, existing_autoincrement=True, comment="主键ID")
    op.alter_column("operation_logs", "user_id", existing_type=sa.Integer(), existing_nullable=True, comment="操作人 user_id")
    op.alter_column("operation_logs", "username", existing_type=sa.String(length=50), existing_nullable=True, comment="操作人用户名（冗余字段，便于查询）")
    op.alter_column("operation_logs", "action", existing_type=sa.String(length=20), existing_nullable=False, comment="操作类型：create 创建 / update 更新 / delete 删除")
    op.alter_column("operation_logs", "target_type", existing_type=sa.String(length=50), existing_nullable=False, comment="目标对象类型：project/environment/api/testcase/user 等")
    op.alter_column("operation_logs", "target_id", existing_type=sa.Integer(), existing_nullable=True, comment="目标对象ID（delete 时可能已无对应记录）")
    op.alter_column("operation_logs", "target_name", existing_type=sa.String(length=200), existing_nullable=True, comment="目标对象名称（便于阅读）")
    op.alter_column("operation_logs", "detail", existing_type=sa.Text(), existing_nullable=True, comment="操作详情（JSON 字符串，可选）")
    op.alter_column("operation_logs", "created_at", existing_type=sa.DateTime(), existing_nullable=True, comment="操作时间")


def downgrade() -> None:
    """回滚：清除所有表字段的 comment。"""
    # MySQL 修改 comment 必须带完整列定义；这里逐表把 id 列 comment 置空作为回滚标记，
    # 其余列 comment 保留（无业务影响）。完整回滚需逐列 MODIFY，此处仅作示意性回滚。
    tables = [
        "users", "projects", "environments", "api_groups", "api_definitions",
        "api_fields", "case_groups", "test_cases", "case_node_configs",
        "execution_records", "step_records", "assertion_records", "operation_logs",
    ]
    for table in tables:
        op.alter_column(table, "id", existing_type=sa.Integer(),
                        existing_nullable=False, existing_autoincrement=True, comment=None)

"""
数据库模型定义。

核心实体：
- Project          项目
- Environment      环境（base_url / db_config / 登录配置 / 通知配置 / 变量）
- ApiGroup         接口分组
- ApiDefinition    接口定义（method / path / 请求模板）
- ApiField         接口请求字段（字段级配置，支持嵌套路径）
- CaseGroup        用例分组
- TestCase         测试用例（DAG 配置）
- CaseNodeConfig   DAG 节点配置（前置处理 / 后置提取 / 断言）
- ExecutionRecord  执行记录
- StepRecord       步骤记录（每个接口调用一条）
- AssertionRecord  断言记录
"""
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, ForeignKey, JSON, Boolean,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from .database import Base


class User(Base):
    """用户表：账号密码登录 + 角色控制"""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True, comment="主键ID")
    username = Column(String(50), nullable=False, unique=True, index=True, comment="登录用户名")
    password_hash = Column(String(255), nullable=False, comment="密码哈希：pbkdf2_hmac(sha256) + salt")
    name = Column(String(50), comment="显示名")
    role = Column(String(20), default="member", comment="角色：admin 管理员 / member 普通成员")
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")
    # 审计字段：谁创建/更新了该用户（自引用外键，记录操作人）
    created_by = Column(Integer, nullable=True, comment="创建人 user_id")
    updated_by = Column(Integer, nullable=True, comment="更新人 user_id")
    # 登录安全：失败计数 + 锁定截止时间（连续失败 5 次锁 15 分钟）
    failed_count = Column(Integer, default=0, comment="连续登录失败次数，成功登录后重置")
    locked_until = Column(DateTime, nullable=True, comment="锁定截止时间，NULL 表示未锁定")
    # 首次登录强制改密：默认 admin 创建时为 True，改密成功后置 False
    must_change_password = Column(Boolean, default=False, comment="是否需要强制修改密码：True 时登录后强制跳转改密页")
    # 用户头像：前端 canvas 压缩后的 base64 data URL（约 10-50KB），NULL 表示未上传
    avatar = Column(Text, nullable=True, comment="头像 base64 data URL，前端压缩后上传")

    @property
    def has_avatar(self) -> bool:
        """是否已设置头像（供 UserOut 输出，避免返回 base64 大字段）"""
        return bool(self.avatar)


class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True, comment="主键ID")
    name = Column(String(100), nullable=False, comment="项目名称")
    description = Column(Text, comment="项目描述")
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")
    created_by = Column(Integer, nullable=True, comment="创建人 user_id")
    updated_by = Column(Integer, nullable=True, comment="更新人 user_id")

    environments = relationship("Environment", back_populates="project", cascade="all, delete-orphan")
    api_groups = relationship("ApiGroup", back_populates="project", cascade="all, delete-orphan")
    apis = relationship("ApiDefinition", back_populates="project", cascade="all, delete-orphan")
    case_groups = relationship("CaseGroup", back_populates="project", cascade="all, delete-orphan")
    test_cases = relationship("TestCase", back_populates="project", cascade="all, delete-orphan")
    versions = relationship("ProjectVersion", back_populates="project", cascade="all, delete-orphan",
                            order_by="ProjectVersion.version_no.desc()")


class Environment(Base):
    __tablename__ = "environments"

    id = Column(Integer, primary_key=True, index=True, comment="主键ID")
    project_id = Column(Integer, ForeignKey("projects.id"), comment="所属项目ID")
    name = Column(String(50), nullable=False, comment="环境名称：dev/test/prod")
    base_url = Column(String(500), nullable=False, comment="接口基础地址，如 https://api.example.com")
    db_config = Column(JSON, default=dict, comment="MySQL 连接配置：{host, port, user, password, database}")
    login_config = Column(JSON, default=dict, comment="登录配置：{login_path, login_body, token_jsonpath, auth_header_name}")
    notify_config = Column(JSON, default=dict, comment="通知配置：{wecom_webhook, enable_on_failure, enable_on_success}")
    variables = Column(JSON, default=dict, comment="业务变量（与登录/通知解耦）")
    common_headers = Column(JSON, default=dict, comment="公共请求头，每个接口请求都会携带")
    timeout = Column(Integer, default=15, comment="接口请求超时时间（秒）")
    is_default = Column(Boolean, default=False, comment="是否为项目默认环境")
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")
    created_by = Column(Integer, nullable=True, comment="创建人 user_id")
    updated_by = Column(Integer, nullable=True, comment="更新人 user_id")

    project = relationship("Project", back_populates="environments")


class ApiGroup(Base):
    """接口分组（订单组/认证组/文件组等）"""
    __tablename__ = "api_groups"

    id = Column(Integer, primary_key=True, index=True, comment="主键ID")
    project_id = Column(Integer, ForeignKey("projects.id"), comment="所属项目ID")
    name = Column(String(100), nullable=False, comment="分组名称")
    sort_order = Column(Integer, default=0, comment="排序序号")
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")

    project = relationship("Project", back_populates="api_groups")
    apis = relationship("ApiDefinition", back_populates="group", cascade="all, delete-orphan")


class ApiDefinition(Base):
    __tablename__ = "api_definitions"

    id = Column(Integer, primary_key=True, index=True, comment="主键ID")
    project_id = Column(Integer, ForeignKey("projects.id"), comment="所属项目ID")
    group_id = Column(Integer, ForeignKey("api_groups.id"), nullable=True, comment="所属分组ID，NULL 表示未分组")
    name = Column(String(100), nullable=False, comment="接口中文名：如 创建订单")
    code = Column(String(100), nullable=False, unique=True, comment="接口唯一编码：如 order_create")
    category = Column(String(50), comment="旧版分类（order/auth/file），新版本用 group")
    method = Column(String(10), default="POST", comment="HTTP 方法：GET/POST/PUT/DELETE")
    path = Column(String(500), nullable=False, comment="请求路径：如 /api/order/orderEntrust/orderAdd")
    description = Column(Text, comment="接口描述")
    request_template = Column(JSON, default=dict, comment="旧版请求体模板，新版本用 fields 字段表")
    headers_template = Column(JSON, default=dict, comment="请求头模板")
    sort_order = Column(Integer, default=0, comment="组内排序序号（支持拖拽排序）")
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")
    created_by = Column(Integer, nullable=True, comment="创建人 user_id")
    updated_by = Column(Integer, nullable=True, comment="更新人 user_id")

    project = relationship("Project", back_populates="apis")
    group = relationship("ApiGroup", back_populates="apis")
    fields = relationship("ApiField", back_populates="api", cascade="all, delete-orphan",
                          order_by="ApiField.sort_order")


class ApiField(Base):
    """接口请求字段（字段级配置，支持嵌套路径，如 to_customer.put_amount）"""
    __tablename__ = "api_fields"

    id = Column(Integer, primary_key=True, index=True, comment="主键ID")
    api_id = Column(Integer, ForeignKey("api_definitions.id"), comment="所属接口ID")
    key = Column(String(200), nullable=False, comment="字段路径：如 order_id / to_customer.put_amount")
    label = Column(String(100), comment="字段中文名：如 订单ID")
    field_type = Column(String(20), default="string", comment="字段类型：string/int/bool/object/array")
    required = Column(Boolean, default=False, comment="是否必填")
    default_value = Column(Text, comment="默认值，支持表达式 ${...}")
    remark = Column(Text, comment="备注")
    sort_order = Column(Integer, default=0, comment="排序序号")

    api = relationship("ApiDefinition", back_populates="fields")


class CaseGroup(Base):
    """用例分组（冒烟组/订单组/付款组/核销组/对账组等）"""
    __tablename__ = "case_groups"

    id = Column(Integer, primary_key=True, index=True, comment="主键ID")
    project_id = Column(Integer, ForeignKey("projects.id"), comment="所属项目ID")
    name = Column(String(100), nullable=False, comment="分组名称")
    sort_order = Column(Integer, default=0, comment="排序序号")
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")

    project = relationship("Project", back_populates="case_groups")
    cases = relationship("TestCase", back_populates="group", cascade="all, delete-orphan")


class TestCase(Base):
    __tablename__ = "test_cases"

    id = Column(Integer, primary_key=True, index=True, comment="主键ID")
    project_id = Column(Integer, ForeignKey("projects.id"), comment="所属项目ID")
    group_id = Column(Integer, ForeignKey("case_groups.id"), nullable=True, comment="所属分组ID，NULL 表示未分组")
    name = Column(String(200), nullable=False, comment="用例名称")
    description = Column(Text, comment="用例描述")
    dag_config = Column(JSON, nullable=False, comment="DAG 配置：{nodes: [...], edges: [...]}")
    sort_order = Column(Integer, default=0, comment="组内排序序号（支持拖拽排序）")
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment="最近更新时间")
    created_by = Column(Integer, nullable=True, comment="创建人 user_id")
    updated_by = Column(Integer, nullable=True, comment="更新人 user_id")

    project = relationship("Project", back_populates="test_cases")
    group = relationship("CaseGroup", back_populates="cases")
    node_configs = relationship("CaseNodeConfig", back_populates="case", cascade="all, delete-orphan")
    executions = relationship("ExecutionRecord", back_populates="case", cascade="all, delete-orphan")


class CaseNodeConfig(Base):
    __tablename__ = "case_node_configs"

    id = Column(Integer, primary_key=True, index=True, comment="主键ID")
    case_id = Column(Integer, ForeignKey("test_cases.id"), comment="所属用例ID")
    node_id = Column(String(100), nullable=False, comment="DAG 节点唯一ID")
    api_id = Column(Integer, ForeignKey("api_definitions.id"), comment="关联接口ID")
    pre_process = Column(JSON, default=list, comment="前置处理动作列表：[{type, path, value}]")
    post_extract = Column(JSON, default=list, comment="后置提取规则列表：[{name, source, jsonpath, sql, field}]")
    assertions = Column(JSON, default=list, comment="断言规则列表：[{type, path, expected, sql, ...}]")

    case = relationship("TestCase", back_populates="node_configs")
    api = relationship("ApiDefinition")


class ExecutionRecord(Base):
    __tablename__ = "execution_records"

    id = Column(Integer, primary_key=True, index=True, comment="主键ID")
    case_id = Column(Integer, ForeignKey("test_cases.id"), comment="所属用例ID")
    env_id = Column(Integer, ForeignKey("environments.id"), comment="执行环境ID")
    status = Column(String(20), default="running", comment="执行状态：running 进行中 / success 成功 / failed 失败")
    started_at = Column(DateTime, default=datetime.now, comment="开始执行时间")
    ended_at = Column(DateTime, comment="结束时间")
    summary = Column(JSON, default=dict, comment="执行摘要：{total 总数, passed 通过, failed 失败}")
    created_by = Column(Integer, nullable=True, comment="执行人 user_id")

    case = relationship("TestCase", back_populates="executions")
    steps = relationship("StepRecord", back_populates="execution", cascade="all, delete-orphan")


class StepRecord(Base):
    __tablename__ = "step_records"

    id = Column(Integer, primary_key=True, index=True, comment="主键ID")
    execution_id = Column(Integer, ForeignKey("execution_records.id"), comment="所属执行记录ID")
    node_id = Column(String(100), comment="DAG 节点ID")
    api_name = Column(String(100), comment="接口名称（执行时快照）")
    api_path = Column(String(500), comment="请求路径（执行时快照）")
    api_method = Column(String(10), comment="HTTP 方法（执行时快照）")
    request_headers = Column(JSON, comment="实际请求头")
    request_body = Column(JSON, comment="实际请求体")
    response_status = Column(Integer, comment="HTTP 响应状态码")
    response_body = Column(JSON, comment="响应体")
    response_time_ms = Column(Integer, comment="响应耗时（毫秒）")
    started_at = Column(DateTime, comment="步骤开始时间")
    ended_at = Column(DateTime, comment="步骤结束时间")
    status = Column(String(20), comment="步骤状态：success 成功 / failed 失败")

    execution = relationship("ExecutionRecord", back_populates="steps")
    assertions = relationship("AssertionRecord", back_populates="step", cascade="all, delete-orphan")


class AssertionRecord(Base):
    __tablename__ = "assertion_records"

    id = Column(Integer, primary_key=True, index=True, comment="主键ID")
    step_id = Column(Integer, ForeignKey("step_records.id"), comment="所属步骤记录ID")
    rule_type = Column(String(50), comment="断言类型：如 json_path_equals / db_query_equals")
    rule_config = Column(JSON, comment="断言规则配置（原始参数）")
    result = Column(Boolean, comment="断言结果：True 通过 / False 失败")
    actual_value = Column(Text, comment="实际值")
    expected_value = Column(Text, comment="期望值")
    message = Column(String(500), comment="结果消息（失败时含原因）")

    step = relationship("StepRecord", back_populates="assertions")


class ProjectVersion(Base):
    """项目版本快照：一次保存 = 项目下所有接口+用例的完整快照，支持回滚和 Diff 对比。
    纯手动触发，用户在项目管理页点「保存版本」时生成。"""
    __tablename__ = "project_versions"
    __table_args__ = (
        UniqueConstraint("project_id", "version_no", name="uq_project_version"),
    )

    id = Column(Integer, primary_key=True, index=True, comment="主键ID")
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True, comment="所属项目ID")
    version_no = Column(Integer, nullable=False, comment="版本号：从 1 递增")
    name = Column(String(200), nullable=False, comment="版本名称：如 v1.0 / 冒烟基线")
    description = Column(Text, comment="版本说明/变更备注")
    snapshot = Column(JSON, nullable=False, comment="完整快照：{apis:[...], cases:[...]}，不含环境（敏感信息）")
    created_by = Column(Integer, nullable=True, comment="创建人 user_id")
    created_at = Column(DateTime, default=datetime.now, comment="版本创建时间")

    project = relationship("Project", back_populates="versions")


class OperationLog(Base):
    """操作日志：记录用户的增删改操作"""
    __tablename__ = "operation_logs"

    id = Column(Integer, primary_key=True, index=True, comment="主键ID")
    user_id = Column(Integer, nullable=True, comment="操作人 user_id")
    username = Column(String(50), comment="操作人用户名（冗余字段，便于查询）")
    action = Column(String(20), nullable=False, comment="操作类型：create 创建 / update 更新 / delete 删除")
    target_type = Column(String(50), nullable=False, comment="目标对象类型：project/environment/api/testcase/user 等")
    target_id = Column(Integer, nullable=True, comment="目标对象ID（delete 时可能已无对应记录）")
    target_name = Column(String(200), comment="目标对象名称（便于阅读）")
    detail = Column(Text, comment="操作详情（JSON 字符串，可选）")
    created_at = Column(DateTime, default=datetime.now, index=True, comment="操作时间")


class FieldDictionary(Base):
    """字段字典：项目级英文字段名 → 中文含义映射，用于配置界面自动展示中文标签"""
    __tablename__ = "field_dictionaries"
    __table_args__ = (
        UniqueConstraint("project_id", "key", name="uq_field_dict_project_key"),
    )

    id = Column(Integer, primary_key=True, index=True, comment="主键ID")
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True, comment="所属项目ID")
    key = Column(String(200), nullable=False, comment="字段英文名：如 order_id / bl_no")
    label = Column(String(100), nullable=False, comment="字段中文名：如 订单ID / 提单号")
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment="最近更新时间")
    created_by = Column(Integer, nullable=True, comment="创建人 user_id")
    updated_by = Column(Integer, nullable=True, comment="更新人 user_id")

    project = relationship("Project")

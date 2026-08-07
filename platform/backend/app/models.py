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
    Column, Integer, String, Text, DateTime, ForeignKey, JSON, Boolean
)
from sqlalchemy.orm import relationship

from .database import Base


class User(Base):
    """用户表：账号密码登录 + 角色控制"""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), nullable=False, unique=True, index=True)
    password_hash = Column(String(255), nullable=False)   # pbkdf2_hmac(sha256) + salt
    name = Column(String(50))                              # 显示名
    role = Column(String(20), default="member")            # admin / member
    created_at = Column(DateTime, default=datetime.now)
    # 审计字段：谁创建/更新了该用户（自引用外键，记录操作人）
    created_by = Column(Integer, nullable=True)
    updated_by = Column(Integer, nullable=True)
    # 登录安全：失败计数 + 锁定截止时间（连续失败 5 次锁 15 分钟）
    failed_count = Column(Integer, default=0)              # 连续登录失败次数
    locked_until = Column(DateTime, nullable=True)         # 锁定截止时间，NULL 表示未锁定


class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    description = Column(Text)
    created_at = Column(DateTime, default=datetime.now)
    created_by = Column(Integer, nullable=True)            # 创建人 user_id
    updated_by = Column(Integer, nullable=True)            # 更新人 user_id

    environments = relationship("Environment", back_populates="project", cascade="all, delete-orphan")
    api_groups = relationship("ApiGroup", back_populates="project", cascade="all, delete-orphan")
    apis = relationship("ApiDefinition", back_populates="project", cascade="all, delete-orphan")
    case_groups = relationship("CaseGroup", back_populates="project", cascade="all, delete-orphan")
    test_cases = relationship("TestCase", back_populates="project", cascade="all, delete-orphan")


class Environment(Base):
    __tablename__ = "environments"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"))
    name = Column(String(50), nullable=False)          # dev/test/prod
    base_url = Column(String(500), nullable=False)
    db_config = Column(JSON, default=dict)             # MySQL 连接配置
    login_config = Column(JSON, default=dict)          # 登录配置：{login_path, login_body, token_jsonpath, auth_header_name}
    notify_config = Column(JSON, default=dict)         # 通知配置：{wecom_webhook, enable_on_failure, enable_on_success}
    variables = Column(JSON, default=dict)             # 业务变量（与登录/通知解耦）
    common_headers = Column(JSON, default=dict)        # 公共请求头
    timeout = Column(Integer, default=15)              # 接口请求超时时间（秒）
    is_default = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.now)
    created_by = Column(Integer, nullable=True)
    updated_by = Column(Integer, nullable=True)

    project = relationship("Project", back_populates="environments")


class ApiGroup(Base):
    """接口分组（订单组/认证组/文件组等）"""
    __tablename__ = "api_groups"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"))
    name = Column(String(100), nullable=False)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.now)

    project = relationship("Project", back_populates="api_groups")
    apis = relationship("ApiDefinition", back_populates="group", cascade="all, delete-orphan")


class ApiDefinition(Base):
    __tablename__ = "api_definitions"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"))
    group_id = Column(Integer, ForeignKey("api_groups.id"), nullable=True)
    name = Column(String(100), nullable=False)         # 中文名：创建订单
    code = Column(String(100), nullable=False, unique=True)  # 唯一编码：order_create
    category = Column(String(50))                      # order/auth/file（兼容字段，新版本用 group）
    method = Column(String(10), default="POST")        # GET/POST/PUT/DELETE
    path = Column(String(500), nullable=False)         # /api/order/orderEntrust/orderAdd
    description = Column(Text)
    request_template = Column(JSON, default=dict)      # 请求体模板（兼容字段，新版本用 fields）
    headers_template = Column(JSON, default=dict)      # 请求头模板
    sort_order = Column(Integer, default=0)            # 组内排序（拖拽排序）
    created_at = Column(DateTime, default=datetime.now)
    created_by = Column(Integer, nullable=True)
    updated_by = Column(Integer, nullable=True)

    project = relationship("Project", back_populates="apis")
    group = relationship("ApiGroup", back_populates="apis")
    fields = relationship("ApiField", back_populates="api", cascade="all, delete-orphan",
                          order_by="ApiField.sort_order")


class ApiField(Base):
    """接口请求字段（字段级配置，支持嵌套路径，如 to_customer.put_amount）"""
    __tablename__ = "api_fields"

    id = Column(Integer, primary_key=True, index=True)
    api_id = Column(Integer, ForeignKey("api_definitions.id"))
    key = Column(String(200), nullable=False)          # 字段路径：order_id / to_customer.put_amount
    label = Column(String(100))                        # 中文名：订单ID
    field_type = Column(String(20), default="string")  # string/int/bool/object/array
    required = Column(Boolean, default=False)
    default_value = Column(Text)                       # 默认值（支持表达式 ${...}）
    remark = Column(Text)                              # 备注
    sort_order = Column(Integer, default=0)

    api = relationship("ApiDefinition", back_populates="fields")


class CaseGroup(Base):
    """用例分组（冒烟组/订单组/付款组/核销组/对账组等）"""
    __tablename__ = "case_groups"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"))
    name = Column(String(100), nullable=False)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.now)

    project = relationship("Project", back_populates="case_groups")
    cases = relationship("TestCase", back_populates="group", cascade="all, delete-orphan")


class TestCase(Base):
    __tablename__ = "test_cases"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"))
    group_id = Column(Integer, ForeignKey("case_groups.id"), nullable=True)
    name = Column(String(200), nullable=False)
    description = Column(Text)
    dag_config = Column(JSON, nullable=False)          # {nodes: [...], edges: [...]}
    sort_order = Column(Integer, default=0)            # 组内排序（拖拽排序）
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    created_by = Column(Integer, nullable=True)
    updated_by = Column(Integer, nullable=True)

    project = relationship("Project", back_populates="test_cases")
    group = relationship("CaseGroup", back_populates="cases")
    node_configs = relationship("CaseNodeConfig", back_populates="case", cascade="all, delete-orphan")
    executions = relationship("ExecutionRecord", back_populates="case", cascade="all, delete-orphan")


class CaseNodeConfig(Base):
    __tablename__ = "case_node_configs"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("test_cases.id"))
    node_id = Column(String(100), nullable=False)      # DAG 节点唯一ID
    api_id = Column(Integer, ForeignKey("api_definitions.id"))
    pre_process = Column(JSON, default=list)           # 前置处理动作列表
    post_extract = Column(JSON, default=list)          # 后置提取规则列表
    assertions = Column(JSON, default=list)            # 断言规则列表

    case = relationship("TestCase", back_populates="node_configs")
    api = relationship("ApiDefinition")


class ExecutionRecord(Base):
    __tablename__ = "execution_records"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("test_cases.id"))
    env_id = Column(Integer, ForeignKey("environments.id"))
    status = Column(String(20), default="running")     # running/success/failed
    started_at = Column(DateTime, default=datetime.now)
    ended_at = Column(DateTime)
    summary = Column(JSON, default=dict)               # {total, passed, failed}
    created_by = Column(Integer, nullable=True)        # 执行人

    case = relationship("TestCase", back_populates="executions")
    steps = relationship("StepRecord", back_populates="execution", cascade="all, delete-orphan")


class StepRecord(Base):
    __tablename__ = "step_records"

    id = Column(Integer, primary_key=True, index=True)
    execution_id = Column(Integer, ForeignKey("execution_records.id"))
    node_id = Column(String(100))
    api_name = Column(String(100))
    api_path = Column(String(500))
    api_method = Column(String(10))
    request_headers = Column(JSON)
    request_body = Column(JSON)
    response_status = Column(Integer)
    response_body = Column(JSON)
    response_time_ms = Column(Integer)
    started_at = Column(DateTime)
    ended_at = Column(DateTime)
    status = Column(String(20))                        # success/failed

    execution = relationship("ExecutionRecord", back_populates="steps")
    assertions = relationship("AssertionRecord", back_populates="step", cascade="all, delete-orphan")


class AssertionRecord(Base):
    __tablename__ = "assertion_records"

    id = Column(Integer, primary_key=True, index=True)
    step_id = Column(Integer, ForeignKey("step_records.id"))
    rule_type = Column(String(50))
    rule_config = Column(JSON)
    result = Column(Boolean)
    actual_value = Column(Text)
    expected_value = Column(Text)
    message = Column(String(500))

    step = relationship("StepRecord", back_populates="assertions")


class OperationLog(Base):
    """操作日志：记录用户的增删改操作"""
    __tablename__ = "operation_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=True)            # 操作人 user_id
    username = Column(String(50))                       # 操作人用户名（冗余，便于查询）
    action = Column(String(20), nullable=False)         # create / update / delete
    target_type = Column(String(50), nullable=False)    # project/environment/api/testcase/user/...
    target_id = Column(Integer, nullable=True)          # 目标对象 ID（delete 时可能已无）
    target_name = Column(String(200))                   # 目标对象名称（便于阅读）
    detail = Column(Text)                               # 详情（JSON 字符串，可选）
    created_at = Column(DateTime, default=datetime.now, index=True)

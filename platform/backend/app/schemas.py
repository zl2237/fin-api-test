"""Pydantic V2 schemas：请求/响应数据模型"""
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict


# ============ 通用 ============
class ORMBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ============ User / Auth ============
class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    username: str
    password: str
    name: Optional[str] = None


class UserOut(ORMBase):
    id: int
    username: str
    name: Optional[str] = None
    role: str = "member"
    created_at: Optional[datetime] = None
    created_by: Optional[int] = None
    created_by_name: Optional[str] = None
    updated_by: Optional[int] = None
    updated_by_name: Optional[str] = None


class LoginResponse(BaseModel):
    token: str
    user: UserOut


class UserCreateRequest(BaseModel):
    username: str
    password: str
    name: Optional[str] = None
    role: str = "member"


class UserRoleUpdate(BaseModel):
    role: str


class UserPasswordReset(BaseModel):
    password: str


class OperationLogOut(ORMBase):
    id: int
    user_id: Optional[int] = None
    username: Optional[str] = None
    action: str
    target_type: str
    target_id: Optional[int] = None
    target_name: Optional[str] = None
    detail: Optional[str] = None
    created_at: Optional[datetime] = None


# ============ Project ============
class ProjectCreate(BaseModel):
    name: str
    description: Optional[str] = None


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class ProjectOut(ORMBase):
    id: int
    name: str
    description: Optional[str] = None
    created_at: Optional[datetime] = None
    created_by: Optional[int] = None
    updated_by: Optional[int] = None
    created_by_name: Optional[str] = None
    updated_by_name: Optional[str] = None


# ============ Environment ============
class EnvironmentCreate(BaseModel):
    project_id: int
    name: str
    base_url: str
    db_config: Dict[str, Any] = {}
    login_config: Dict[str, Any] = {}
    notify_config: Dict[str, Any] = {}
    variables: Dict[str, Any] = {}
    common_headers: Dict[str, Any] = {}
    timeout: int = 15
    is_default: bool = False


class EnvironmentUpdate(BaseModel):
    name: Optional[str] = None
    base_url: Optional[str] = None
    db_config: Optional[Dict[str, Any]] = None
    login_config: Optional[Dict[str, Any]] = None
    notify_config: Optional[Dict[str, Any]] = None
    variables: Optional[Dict[str, Any]] = None
    common_headers: Optional[Dict[str, Any]] = None
    timeout: Optional[int] = None
    is_default: Optional[bool] = None


class EnvironmentOut(ORMBase):
    id: int
    project_id: int
    name: str
    base_url: str
    db_config: Dict[str, Any] = {}
    login_config: Dict[str, Any] = {}
    notify_config: Dict[str, Any] = {}
    variables: Dict[str, Any] = {}
    common_headers: Dict[str, Any] = {}
    timeout: int = 15
    is_default: bool = False
    created_at: Optional[datetime] = None
    created_by: Optional[int] = None
    updated_by: Optional[int] = None
    created_by_name: Optional[str] = None
    updated_by_name: Optional[str] = None


# ============ ApiGroup ============
class ApiGroupCreate(BaseModel):
    project_id: int
    name: str
    sort_order: int = 0


class ApiGroupUpdate(BaseModel):
    name: Optional[str] = None
    sort_order: Optional[int] = None


class ApiGroupOut(ORMBase):
    id: int
    project_id: int
    name: str
    sort_order: int = 0
    created_at: Optional[datetime] = None


# ============ ApiField ============
class ApiFieldIn(BaseModel):
    key: str
    label: Optional[str] = None
    field_type: str = "string"
    required: bool = False
    default_value: Optional[str] = None
    remark: Optional[str] = None
    sort_order: int = 0


class ApiFieldOut(ORMBase):
    id: int
    api_id: int
    key: str
    label: Optional[str] = None
    field_type: str = "string"
    required: bool = False
    default_value: Optional[str] = None
    remark: Optional[str] = None
    sort_order: int = 0


# ============ ApiDefinition ============
class ApiCreate(BaseModel):
    project_id: int
    group_id: Optional[int] = None
    name: str
    code: str
    category: Optional[str] = None
    method: str = "POST"
    path: str
    description: Optional[str] = None
    request_template: Dict[str, Any] = {}
    headers_template: Dict[str, Any] = {}
    fields: List[ApiFieldIn] = []


class ApiUpdate(BaseModel):
    group_id: Optional[int] = None
    name: Optional[str] = None
    code: Optional[str] = None
    category: Optional[str] = None
    method: Optional[str] = None
    path: Optional[str] = None
    description: Optional[str] = None
    request_template: Optional[Dict[str, Any]] = None
    headers_template: Optional[Dict[str, Any]] = None
    fields: Optional[List[ApiFieldIn]] = None


class ApiBatchMove(BaseModel):
    """批量移动接口到指定分组（group_id 为 null 表示移到未分组）"""
    api_ids: List[int]
    group_id: Optional[int] = None


class ApiImportRequest(BaseModel):
    """Swagger/OpenAPI 接口导入请求"""
    project_id: int
    group_id: Optional[int] = None
    spec: Dict[str, Any]  # 完整的 Swagger/OpenAPI JSON


class ApiDebugRequest(BaseModel):
    """单接口调试请求：指定环境执行一次接口，返回请求/响应详情"""
    env_id: int
    body_override: Optional[Dict[str, Any]] = None  # 覆盖字段默认值；为空则用 fields 组装


class ApiOut(ORMBase):
    id: int
    project_id: int
    group_id: Optional[int] = None
    name: str
    code: str
    category: Optional[str] = None
    method: str
    path: str
    description: Optional[str] = None
    request_template: Dict[str, Any] = {}
    headers_template: Dict[str, Any] = {}
    fields: List[ApiFieldOut] = []
    created_at: Optional[datetime] = None
    created_by: Optional[int] = None
    updated_by: Optional[int] = None
    created_by_name: Optional[str] = None
    updated_by_name: Optional[str] = None


# ============ CaseGroup ============
class CaseGroupCreate(BaseModel):
    project_id: int
    name: str
    sort_order: int = 0


class CaseGroupUpdate(BaseModel):
    name: Optional[str] = None
    sort_order: Optional[int] = None


class CaseGroupOut(ORMBase):
    id: int
    project_id: int
    name: str
    sort_order: int = 0
    created_at: Optional[datetime] = None


# ============ CaseNodeConfig ============
class NodeConfigIn(BaseModel):
    node_id: str
    api_id: Optional[int] = None
    pre_process: List[Dict[str, Any]] = []
    post_extract: List[Dict[str, Any]] = []
    assertions: List[Dict[str, Any]] = []


class NodeConfigOut(ORMBase):
    id: int
    case_id: int
    node_id: str
    api_id: Optional[int] = None
    pre_process: List[Dict[str, Any]] = []
    post_extract: List[Dict[str, Any]] = []
    assertions: List[Dict[str, Any]] = []


# ============ TestCase ============
class TestCaseCreate(BaseModel):
    project_id: int
    group_id: Optional[int] = None
    name: str
    description: Optional[str] = None
    dag_config: Dict[str, Any]
    node_configs: List[NodeConfigIn] = []


class TestCaseUpdate(BaseModel):
    group_id: Optional[int] = None
    name: Optional[str] = None
    description: Optional[str] = None
    dag_config: Optional[Dict[str, Any]] = None
    node_configs: Optional[List[NodeConfigIn]] = None


class TestCaseOut(ORMBase):
    id: int
    project_id: int
    group_id: Optional[int] = None
    name: str
    description: Optional[str] = None
    dag_config: Dict[str, Any]
    node_configs: List[NodeConfigOut] = []
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    created_by: Optional[int] = None
    updated_by: Optional[int] = None
    created_by_name: Optional[str] = None
    updated_by_name: Optional[str] = None


class CaseBatchMove(BaseModel):
    """批量移动用例到指定分组（group_id 为 null 表示移到未分组）"""
    case_ids: List[int]
    group_id: Optional[int] = None


# ============ Execution ============
class ExecutionCreate(BaseModel):
    case_id: int
    env_id: int


class BatchExecutionCreate(BaseModel):
    """批量执行：串行执行多个用例，一个结束执行下一个"""
    case_ids: List[int]
    env_id: int


class AssertionRecordOut(ORMBase):
    id: int
    step_id: int
    rule_type: str
    rule_config: Optional[Dict[str, Any]] = None
    result: Optional[bool] = None
    actual_value: Optional[str] = None
    expected_value: Optional[str] = None
    message: Optional[str] = None


class StepRecordOut(ORMBase):
    id: int
    execution_id: int
    node_id: Optional[str] = None
    api_name: Optional[str] = None
    api_path: Optional[str] = None
    api_method: Optional[str] = None
    request_headers: Optional[Dict[str, Any]] = None
    request_body: Optional[Dict[str, Any]] = None
    response_status: Optional[int] = None
    response_body: Optional[Any] = None
    response_time_ms: Optional[int] = None
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    status: Optional[str] = None
    assertions: List[AssertionRecordOut] = []


class ExecutionRecordOut(ORMBase):
    id: int
    case_id: int
    env_id: int
    case_name: Optional[str] = None
    env_name: Optional[str] = None
    project_id: Optional[int] = None
    project_name: Optional[str] = None
    status: str
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    summary: Dict[str, Any] = {}
    steps: List[StepRecordOut] = []
    created_by: Optional[int] = None
    created_by_name: Optional[str] = None

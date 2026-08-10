"""Pydantic V2 schemas：请求/响应数据模型"""
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


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
    must_change_password: bool = False
    has_avatar: bool = False
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


class ChangePasswordRequest(BaseModel):
    """用户自助改密：仅需新密码（强制改密场景用户刚登录，已验证身份）"""
    new_password: str


class AvatarUpdate(BaseModel):
    """上传头像：前端 canvas 压缩后的 base64 data URL"""
    avatar: str = Field(..., description="data:image/(jpeg|png|webp);base64,xxx")


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
    request_template: Any = {}
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
    request_template: Optional[Any] = None
    headers_template: Optional[Dict[str, Any]] = None
    fields: Optional[List[ApiFieldIn]] = None


class ApiBatchMove(BaseModel):
    """批量移动接口到指定分组（group_id 为 null 表示移到未分组）"""
    api_ids: List[int]
    group_id: Optional[int] = None


class ApiReorderItem(BaseModel):
    """重排序单项：接口ID + 新的 sort_order"""
    id: int
    sort_order: int


class ApiReorderRequest(BaseModel):
    """批量重排序接口（组内拖拽排序）"""
    items: List[ApiReorderItem]


class CaseReorderItem(BaseModel):
    id: int
    sort_order: int


class CaseReorderRequest(BaseModel):
    """批量重排序用例（组内拖拽排序）"""
    items: List[CaseReorderItem]


class ApiImportRequest(BaseModel):
    """Swagger/OpenAPI 接口导入请求"""
    project_id: int
    group_id: Optional[int] = None
    spec: Dict[str, Any]  # 完整的 Swagger/OpenAPI JSON


class ApiImportFieldsRequest(BaseModel):
    """用 Swagger 覆盖指定接口的字段：只解析返回字段列表，不落库。
    前端拿到字段后展示新旧对比，用户确认后再调 PUT /apis/{id} 覆盖。"""
    method: str  # 目标接口方法（GET/POST/...），用于定位 spec 中对应 operation
    path: str  # 目标接口路径，用于定位 spec 中对应 operation
    spec: Dict[str, Any]  # 完整的 Swagger/OpenAPI JSON


class ApiImportFieldsResponse(BaseModel):
    """Swagger 解析后的字段列表 + 操作定位信息"""
    matched: bool  # spec 中是否找到 method+path 对应的 operation
    method: str
    path: str
    operation_summary: Optional[str] = None  # operation 的 summary/operationId，便于确认匹配
    fields: List[ApiFieldIn] = []


class HarPreviewField(BaseModel):
    """HAR 预览中的单个字段"""
    key: str
    field_type: str = "string"
    default_value: str = ""
    in_: str = Field("body", alias="in")  # query/body
    required: bool = False
    model_config = ConfigDict(populate_by_name=True)


class HarPreviewItem(BaseModel):
    """HAR 解析后的单个接口预览"""
    method: str
    path: str
    url: str
    name: str
    field_count: int
    fields: List[Dict[str, Any]] = []  # 原始字段 dict（前端展示用）
    is_array_body: bool = False
    content_type: str = ""


class HarPreviewResponse(BaseModel):
    """HAR 文件解析预览响应"""
    total: int  # 解析出的接口总数
    previews: List[HarPreviewItem] = []


class HarImportRequest(BaseModel):
    """HAR 导入请求：用户勾选的接口列表"""
    project_id: int
    group_id: Optional[int] = None
    previews: List[Dict[str, Any]]  # 用户勾选的预览项（含 method/path/name/fields/is_array_body）


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
    request_template: Any = {}
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


# ============ ProjectVersion 项目版本快照 ============
class ProjectVersionCreate(BaseModel):
    """手动创建版本快照"""
    name: str
    description: Optional[str] = None


class ProjectVersionOut(ORMBase):
    """项目版本输出（列表/详情通用，列表时 snapshot 可选省略）"""
    id: int
    project_id: int
    version_no: int
    name: str
    description: Optional[str] = None
    snapshot: Optional[Dict[str, Any]] = None
    created_by: Optional[int] = None
    created_by_name: Optional[str] = None
    created_at: Optional[datetime] = None


class ProjectVersionDiff(BaseModel):
    """两个项目版本对比结果：各类资源的 added/removed/modified"""
    base: ProjectVersionOut
    target: ProjectVersionOut
    diff: Dict[str, Any]


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
    request_body: Optional[Any] = None  # 兼容数组请求体 [{...}]
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


# ============ FieldDictionary 字段字典 ============
class FieldDictItemIn(BaseModel):
    """批量导入单行：key=label"""
    key: str
    label: str


class FieldDictionaryCreate(BaseModel):
    project_id: int
    key: str
    label: str


class FieldDictionaryUpdate(BaseModel):
    key: Optional[str] = None
    label: Optional[str] = None


class FieldDictionaryBatchIn(BaseModel):
    """批量导入：覆盖式写入（同 key 更新 label）"""
    project_id: int
    items: List[FieldDictItemIn]


class FieldDictionaryOut(ORMBase):
    id: int
    project_id: int
    key: str
    label: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    created_by: Optional[int] = None
    updated_by: Optional[int] = None
    created_by_name: Optional[str] = None
    updated_by_name: Optional[str] = None

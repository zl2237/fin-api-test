"""Pydantic V2 schemas：请求/响应数据模型"""
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


# ============ 通用 ============
class ORMBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class AuditMixin(BaseModel):
    """审计字段单一事实来源：Out schema 混入即获得创建审计三字段。

    之前这组字段在 7 个 Out 类中逐字段重复声明，任何调整需改 7 处。
    updated_* 变体按需在各 Out 单独声明（并非所有实体都有更新人语义）。
    """
    created_at: datetime | None = None
    created_by: int | None = None
    created_by_name: str | None = None


# ============ User / Auth ============
class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    username: str
    password: str
    name: str | None = None


class UserOut(ORMBase):
    id: int
    username: str
    name: str | None = None
    role: str = "member"
    must_change_password: bool = False
    has_avatar: bool = False
    phone: str | None = None
    email: str | None = None
    created_at: datetime | None = None
    created_by: int | None = None
    created_by_name: str | None = None
    updated_by: int | None = None
    updated_by_name: str | None = None


class LoginResponse(BaseModel):
    token: str
    user: UserOut


class UserCreateRequest(BaseModel):
    username: str
    password: str
    name: str | None = None
    role: str = "member"


class UserRoleUpdate(BaseModel):
    role: str


class UserInfoUpdate(BaseModel):
    """编辑用户整抽屉提交：用户名/显示名/手机号/邮箱/部门/角色一次保存"""
    username: str = Field(min_length=2, max_length=50)
    name: str | None = Field(default=None, max_length=50)
    phone: str | None = Field(default=None, max_length=20)
    email: str | None = Field(default=None, max_length=100)
    department: str | None = Field(default=None, max_length=50)
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
    user_id: int | None = None
    username: str | None = None
    action: str
    target_type: str
    target_id: int | None = None
    target_name: str | None = None
    detail: str | None = None
    created_at: datetime | None = None


# ============ Project ============
class ProjectCreate(BaseModel):
    name: str
    description: str | None = None


class ProjectUpdate(BaseModel):
    name: str | None = None
    description: str | None = None


class ProjectReorderRequest(BaseModel):
    """批量重排序项目（拖拽排序）"""
    items: list[dict[str, Any]]


class ProjectOut(ORMBase, AuditMixin):
    id: int
    name: str
    description: str | None = None
    sort_order: int = 0
    updated_by: int | None = None
    updated_by_name: str | None = None


# ============ Environment ============
class EnvironmentCreate(BaseModel):
    project_id: int
    name: str
    base_url: str
    db_config: dict[str, Any] = {}
    login_config: dict[str, Any] = {}
    notify_config: dict[str, Any] = {}
    variables: dict[str, Any] = {}
    common_headers: dict[str, Any] = {}
    timeout: int = 15
    is_default: bool = False


class EnvironmentUpdate(BaseModel):
    name: str | None = None
    base_url: str | None = None
    db_config: dict[str, Any] | None = None
    login_config: dict[str, Any] | None = None
    notify_config: dict[str, Any] | None = None
    variables: dict[str, Any] | None = None
    common_headers: dict[str, Any] | None = None
    timeout: int | None = None
    is_default: bool | None = None


class EnvironmentReorderRequest(BaseModel):
    """批量重排序环境（拖拽排序）"""
    items: list[dict[str, Any]]


class EnvironmentOut(ORMBase, AuditMixin):
    id: int
    project_id: int
    name: str
    base_url: str
    db_config: dict[str, Any] = {}
    login_config: dict[str, Any] = {}
    notify_config: dict[str, Any] = {}
    variables: dict[str, Any] = {}
    common_headers: dict[str, Any] = {}
    timeout: int = 15
    is_default: bool = False
    sort_order: int = 0
    updated_by: int | None = None
    updated_by_name: str | None = None


# ============ ApiGroup ============
class ApiGroupCreate(BaseModel):
    project_id: int
    parent_id: int | None = None
    name: str
    sort_order: int = 0


class ApiGroupUpdate(BaseModel):
    name: str | None = None
    parent_id: int | None = None
    sort_order: int | None = None


class ApiGroupOut(ORMBase):
    id: int
    project_id: int
    parent_id: int | None = None
    name: str
    sort_order: int = 0
    created_at: datetime | None = None


# ============ ApiField ============
class ApiFieldIn(BaseModel):
    key: str
    label: str | None = None
    field_type: str = "string"
    required: bool = False
    default_value: str | None = None
    remark: str | None = None
    sort_order: int = 0


class ApiFieldOut(ORMBase):
    id: int
    api_id: int
    key: str
    label: str | None = None
    field_type: str = "string"
    required: bool = False
    default_value: str | None = None
    remark: str | None = None
    sort_order: int = 0


# ============ ApiDefinition ============
class ApiCreate(BaseModel):
    project_id: int
    group_id: int | None = None
    name: str
    code: str
    category: str | None = None
    method: str = "POST"
    path: str
    description: str | None = None
    request_template: Any = {}
    headers_template: dict[str, Any] = {}
    fields: list[ApiFieldIn] = []


class ApiUpdate(BaseModel):
    group_id: int | None = None
    name: str | None = None
    code: str | None = None
    category: str | None = None
    method: str | None = None
    path: str | None = None
    description: str | None = None
    request_template: Any | None = None
    headers_template: dict[str, Any] | None = None
    fields: list[ApiFieldIn] | None = None


class ApiBatchMove(BaseModel):
    """批量移动接口到指定分组（group_id 为 null 表示移到未分组）"""
    api_ids: list[int]
    group_id: int | None = None


class ApiReorderItem(BaseModel):
    """重排序单项：接口ID + 新的 sort_order"""
    id: int
    sort_order: int


class ApiReorderRequest(BaseModel):
    """批量重排序接口（组内拖拽排序）"""
    items: list[ApiReorderItem]


class CaseReorderItem(BaseModel):
    id: int
    sort_order: int


class CaseReorderRequest(BaseModel):
    """批量重排序用例（组内拖拽排序）"""
    items: list[CaseReorderItem]


class ApiImportRequest(BaseModel):
    """Swagger/OpenAPI 接口导入请求"""
    project_id: int
    group_id: int | None = None
    spec: dict[str, Any]  # 完整的 Swagger/OpenAPI JSON


class ApiImportFieldsRequest(BaseModel):
    """用 Swagger 覆盖指定接口的字段：只解析返回字段列表，不落库。
    前端拿到字段后展示新旧对比，用户确认后再调 PUT /apis/{id} 覆盖。"""
    method: str  # 目标接口方法（GET/POST/...），用于定位 spec 中对应 operation
    path: str  # 目标接口路径，用于定位 spec 中对应 operation
    spec: dict[str, Any]  # 完整的 Swagger/OpenAPI JSON


class ApiImportFieldsResponse(BaseModel):
    """Swagger 解析后的字段列表 + 操作定位信息"""
    matched: bool  # spec 中是否找到 method+path 对应的 operation
    method: str
    path: str
    operation_summary: str | None = None  # operation 的 summary/operationId，便于确认匹配
    fields: list[ApiFieldIn] = []


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
    fields: list[dict[str, Any]] = []  # 原始字段 dict（前端展示用）
    is_array_body: bool = False
    content_type: str = ""


class HarPreviewResponse(BaseModel):
    """HAR 文件解析预览响应"""
    total: int  # 解析出的接口总数
    previews: list[HarPreviewItem] = []


class HarImportRequest(BaseModel):
    """HAR 导入请求：用户勾选的接口列表"""
    project_id: int
    group_id: int | None = None
    previews: list[dict[str, Any]]  # 用户勾选的预览项（含 method/path/name/fields/is_array_body）


class CurlPreviewRequest(BaseModel):
    """cURL 命令预览请求：粘贴一条或多条 cURL 命令文本"""
    text: str  # cURL 命令文本（多条以空行分隔）


class CurlPreviewResponse(BaseModel):
    """cURL 解析预览响应"""
    total: int  # 成功解析的接口总数
    previews: list[HarPreviewItem] = []  # 复用 HAR 预览结构
    errors: list[str] = []  # 解析失败的命令及原因


class CurlImportRequest(BaseModel):
    """cURL 导入请求：用户勾选的接口列表"""
    project_id: int
    group_id: int | None = None
    previews: list[dict[str, Any]]  # 用户勾选的预览项（结构与 HAR 一致）


class ApiDebugRequest(BaseModel):
    """单接口调试请求：指定环境执行一次接口，返回请求/响应详情"""
    env_id: int
    body_override: dict[str, Any] | None = None  # 覆盖字段默认值；为空则用 fields 组装


class ApiOut(ORMBase):
    id: int
    project_id: int
    group_id: int | None = None
    name: str
    code: str
    category: str | None = None
    method: str
    path: str
    description: str | None = None
    request_template: Any = {}
    headers_template: dict[str, Any] = {}
    fields: list[ApiFieldOut] = []
    created_at: datetime | None = None
    created_by: int | None = None
    updated_by: int | None = None
    created_by_name: str | None = None
    updated_by_name: str | None = None


# ============ CaseGroup ============
class CaseGroupCreate(BaseModel):
    project_id: int
    parent_id: int | None = None
    name: str
    sort_order: int = 0


class CaseGroupUpdate(BaseModel):
    name: str | None = None
    parent_id: int | None = None
    sort_order: int | None = None


class CaseGroupOut(ORMBase):
    id: int
    project_id: int
    parent_id: int | None = None
    name: str
    sort_order: int = 0
    created_at: datetime | None = None


# ============ CaseNodeConfig ============
class NodeConfigIn(BaseModel):
    node_id: str
    api_id: int | None = None
    pre_process: list[dict[str, Any]] = []
    post_extract: list[dict[str, Any]] = []
    assertions: list[dict[str, Any]] = []
    wait_after_ms: int = 0


class NodeConfigOut(ORMBase):
    id: int
    case_id: int
    node_id: str
    api_id: int | None = None
    pre_process: list[dict[str, Any]] = []
    post_extract: list[dict[str, Any]] = []
    assertions: list[dict[str, Any]] = []
    wait_after_ms: int = 0


# ============ TestCase ============
class TestCaseCreate(BaseModel):
    project_id: int
    group_id: int | None = None
    name: str
    description: str | None = None
    dag_config: dict[str, Any]
    node_configs: list[NodeConfigIn] = []


class TestCaseUpdate(BaseModel):
    group_id: int | None = None
    name: str | None = None
    description: str | None = None
    dag_config: dict[str, Any] | None = None
    node_configs: list[NodeConfigIn] | None = None
    dataset_id: int | None = None  # 绑定数据集（数据驱动）；显式传 null 解绑


class TestCaseOut(ORMBase):
    id: int
    project_id: int
    group_id: int | None = None
    name: str
    description: str | None = None
    dag_config: dict[str, Any]
    node_configs: list[NodeConfigOut] = []
    dataset_id: int | None = None  # 绑定的数据集（数据驱动），NULL=普通用例
    created_at: datetime | None = None
    updated_at: datetime | None = None
    created_by: int | None = None
    updated_by: int | None = None
    created_by_name: str | None = None
    updated_by_name: str | None = None


class CaseBatchMove(BaseModel):
    """批量移动用例到指定分组（group_id 为 null 表示移到未分组）"""
    case_ids: list[int]
    group_id: int | None = None


class CaseCombineRequest(BaseModel):
    """多用例组合（拼接成新用例），case_ids 顺序即拼接顺序"""
    case_ids: list[int]
    name: str
    group_id: int | None = None


class CaseSplitRequest(BaseModel):
    """用例拆分：抽离 node_ids 到新用例（scan-split 阶段只需 node_ids，执行阶段才要新用例名）"""
    node_ids: list[str]
    new_name: str | None = None
    new_group_id: int | None = None


# ============ ProjectVersion 项目版本快照 ============
class ProjectVersionCreate(BaseModel):
    """手动创建版本快照"""
    name: str
    description: str | None = None


class ProjectVersionOut(ORMBase):
    """项目版本输出（列表/详情通用，列表时 snapshot 可选省略）"""
    id: int
    project_id: int
    version_no: int
    name: str
    description: str | None = None
    snapshot: dict[str, Any] | None = None
    created_by: int | None = None
    created_by_name: str | None = None
    created_at: datetime | None = None


class ProjectVersionDiff(BaseModel):
    """两个项目版本对比结果：各类资源的 added/removed/modified"""
    base: ProjectVersionOut
    target: ProjectVersionOut
    diff: dict[str, Any]


# ============ Execution ============
class ExecutionCreate(BaseModel):
    case_id: int
    env_id: int
    dataset_id: int | None = None  # 执行时临时换数据集（不改用例绑定）
    row_ids: list[int] | None = None  # 仅执行选中的数据行（单行手动执行=逐条通知）


class BatchExecutionCreate(BaseModel):
    """批量执行：串行执行多个用例，一个结束执行下一个"""
    case_ids: list[int]
    env_id: int
    # 每个用例的执行次数（与 case_ids 一一对应，缺省全部为 1）；如 A 跑 3 次、B 跑 1 次
    counts: list[int] | None = None


class AssertionRecordOut(ORMBase):
    id: int
    step_id: int
    rule_type: str
    rule_config: dict[str, Any] | None = None
    result: bool | None = None
    actual_value: str | None = None
    expected_value: str | None = None
    message: str | None = None


class StepRecordOut(ORMBase):
    id: int
    execution_id: int
    node_id: str | None = None
    api_name: str | None = None
    api_path: str | None = None
    api_method: str | None = None
    request_headers: dict[str, Any] | None = None
    request_body: Any | None = None  # 兼容数组请求体 [{...}]
    response_status: int | None = None
    response_body: Any | None = None
    response_time_ms: int | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
    status: str | None = None
    assertions: list[AssertionRecordOut] = []


class ExecutionRecordOut(ORMBase):
    id: int
    case_id: int
    env_id: int
    case_name: str | None = None
    env_name: str | None = None
    project_id: int | None = None
    project_name: str | None = None
    status: str
    trigger_type: str = "manual"
    started_at: datetime | None = None
    ended_at: datetime | None = None
    summary: dict[str, Any] = {}
    dataset_id: int | None = None
    dataset_row: dict[str, Any] | None = None  # 数据驱动行快照 {row_index, data, label}
    steps: list[StepRecordOut] = []
    created_by: int | None = None
    created_by_name: str | None = None


# ============ TestSchedule 定时任务 ============
class TestScheduleCreate(BaseModel):
    case_id: int
    env_id: int
    schedule_type: str  # interval / daily
    interval_minutes: int | None = None
    daily_time: str | None = None  # HH:MM
    enabled: bool = True


class TestScheduleUpdate(BaseModel):
    env_id: int | None = None
    schedule_type: str | None = None
    interval_minutes: int | None = None
    daily_time: str | None = None
    enabled: bool | None = None


class TestScheduleOut(ORMBase):
    id: int
    case_id: int
    env_id: int
    case_name: str | None = None
    env_name: str | None = None
    schedule_type: str
    interval_minutes: int | None = None
    daily_time: str | None = None
    enabled: bool
    last_run_at: datetime | None = None
    next_run_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    created_by: int | None = None
    created_by_name: str | None = None
    updated_by: int | None = None
    updated_by_name: str | None = None


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
    key: str | None = None
    label: str | None = None


class FieldDictionaryBatchIn(BaseModel):
    """批量导入：覆盖式写入（同 key 更新 label）"""
    project_id: int
    items: list[FieldDictItemIn]


class FieldDictionaryOut(ORMBase, AuditMixin):
    id: int
    project_id: int
    key: str
    label: str
    updated_at: datetime | None = None
    updated_by: int | None = None
    updated_by_name: str | None = None


# ============ FileCategory 文件分类 ============
class FileCategoryCreate(BaseModel):
    project_id: int
    parent_id: int | None = None
    name: str
    sort_order: int = 0


class FileCategoryUpdate(BaseModel):
    name: str | None = None
    parent_id: int | None = None
    sort_order: int | None = None


class FileCategoryOut(ORMBase, AuditMixin):
    id: int
    project_id: int
    parent_id: int | None = None
    name: str
    sort_order: int = 0


# ============ TestFile 测试文件 ============
class FileUpdateRequest(BaseModel):
    """重命名 / 改分类"""
    name: str | None = None
    category_id: int | None = None


class FileOut(ORMBase, AuditMixin):
    id: int
    project_id: int
    category_id: int | None = None
    name: str
    original_name: str
    content_type: str = "application/octet-stream"
    size: int = 0
    sha256: str
    storage_path: str
    ref_count: int = 1
    updated_at: datetime | None = None
    updated_by: int | None = None
    updated_by_name: str | None = None


# ============ DataSet 数据集（数据驱动测试） ============
class DataSetColumnIn(BaseModel):
    """列定义：key 即执行时变量名（校验见 dataset_service._validate_columns；label 已废除，中文名实时引用字段字典）"""
    key: str
    type: str = "string"  # string/int/bool/array/object


class DataSetCreate(BaseModel):
    project_id: int
    case_id: int  # 归属用例（1:N 隔离）
    name: str
    description: str | None = None
    columns: list[DataSetColumnIn]


class DataSetGenerateIn(BaseModel):
    """从用例生成数据集：收集用例全部写死请求参数各成一列 + 1 行原值快照 + 节点配置快照"""
    case_id: int
    name: str | None = None


class DataSetUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    columns: list[DataSetColumnIn] | None = None


class DataSetRowOut(ORMBase):
    id: int
    dataset_id: int
    row_index: int
    data: dict[str, Any] = {}


class DataSetOut(ORMBase, AuditMixin):
    id: int
    project_id: int
    case_id: int
    name: str
    description: str | None = None
    columns: list[dict[str, Any]] = []
    node_configs: list[dict[str, Any]] = []  # 节点配置快照（只读展示，改配置回用例编排再同步）
    rows: list[DataSetRowOut] = []
    case_bound_count: int = 0  # 被引用用例数（列表展示）
    updated_at: datetime | None = None
    updated_by: int | None = None
    updated_by_name: str | None = None


class DataSetRowCreate(BaseModel):
    data: dict[str, Any]


class DataSetRowsReplace(BaseModel):
    """批量保存（表格整页保存）：整体替换，row_index 由后端重排"""
    rows: list[dict[str, Any]]


# ============ 轻量契约（原裸 dict 出参） ============
class SimpleUserOut(BaseModel):
    """筛选下拉用轻量用户：仅 id 与显示名"""
    id: int
    name: str


class AvatarOut(BaseModel):
    """按用户 ID 查头像的响应"""
    avatar: str | None = None
    name: str

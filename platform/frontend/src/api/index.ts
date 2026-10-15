import axios from 'axios'
import { startProgress, doneProgress } from '@/utils/requestProgress'

const http = axios.create({
  baseURL: '/api',
  timeout: 60000,
  // 数组参数序列化为重复键（key=1&key=2），匹配 FastAPI 的 List Query 解析；
  // axios 默认的 key[]=1 格式后端不识别，会导致过滤参数被静默忽略
  paramsSerializer: {
    serialize: (params) => {
      const sp = new URLSearchParams()
      for (const [key, value] of Object.entries(params)) {
        if (value === undefined || value === null) continue
        if (Array.isArray(value)) {
          value.forEach((v) => sp.append(key, String(v)))
        } else {
          sp.append(key, String(value))
        }
      }
      return sp.toString()
    },
  },
})

// 扩展 axios config：silent=true 时跳过顶部进度条（用于轮询请求避免频繁闪烁）
declare module 'axios' {
  export interface AxiosRequestConfig {
    silent?: boolean
  }
}

// ============ Token 管理 ============
const TOKEN_KEY = 'fin_api_test_token'

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token)
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY)
}

// 请求拦截器：自动注入 Authorization + 启动顶部进度条
http.interceptors.request.use((config) => {
  const token = getToken()
  if (token) {
    config.headers = config.headers || {}
    config.headers.Authorization = `Bearer ${token}`
  }
  // silent 请求（如轮询）跳过进度条，避免频繁闪烁
  if (!config.silent) {
    startProgress()
  }
  return config
})

// 后端 detail 兜底折叠：主应用已有 422 handler 折叠为字符串，但数组形态
// （其他服务/旧版本网关）会退化成英文逗号串，这里统一为「字段: 原因；…」
function foldDetail(detail: unknown): string {
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail
      .map((e: { loc?: unknown[]; msg?: unknown }) => {
        const loc = Array.isArray(e?.loc) ? e.loc.filter((x) => x !== 'body').join('.') : ''
        const msg = typeof e?.msg === 'string' ? e.msg : ''
        return loc ? `${loc}: ${msg}` : msg
      })
      .filter(Boolean)
      .join('；')
  }
  return ''
}

// 响应拦截器：401 清 token 跳登录；其他错误提取 detail；结束进度条
http.interceptors.response.use(
  (resp) => {
    if (!resp.config.silent) doneProgress()
    return resp
  },
  (error) => {
    if (!error?.config?.silent) doneProgress()
    const status = error?.response?.status
    if (status === 401) {
      clearToken()
      // history 模式：直接跳 /login，避免在登录页重复跳转
      if (!window.location.pathname.includes('/login')) {
        window.location.href = '/login'
      }
    }
    // blob 请求（文件下载/导出）失败时 body 是 Blob，需读文本后解析出后端 detail；
    // 解析完再统一 reject，保证调用方 catch 到的仍是 ApiError
    const rejectWithMsg = (msg: string) => Promise.reject(new ApiError(msg, status))
    const data = error?.response?.data
    if (typeof Blob !== 'undefined' && data instanceof Blob && data.type.includes('json')) {
      return data.text().then((txt: string) => {
        try {
          return rejectWithMsg(foldDetail(JSON.parse(txt)?.detail) || error?.message || '请求失败')
        } catch {
          return rejectWithMsg(error?.message || '请求失败')
        }
      })
    }
    const msg = foldDetail(data?.detail) || error?.message || '请求失败'
    return rejectWithMsg(msg)
  },
)

// ============ ApiError 契约 ============
// 拦截器把一切失败（HTTP 错误/blob 响应/网络错误）规整为 ApiError：
// message 必为后端 detail（缺失时回退 axios message / '请求失败'）。
// 调用方 catch 只读 e.message，不要再写 e?.response?.data?.detail 之类的对冲解析。
export class ApiError extends Error {
  /** HTTP 状态码；无响应（网络错误/超时）时为 undefined */
  status?: number
  constructor(message: string, status?: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

// ============ 类型 ============
// 响应类型优先取 OpenAPI 生成物别名（npm run gen:api，后端 Pydantic 为单一事实源）。
// 仍手写的接口分两类：嵌套结构在生成物中退化为 unknown（Environment/ApiDef/TestCase/
// NodeConfig/记录族/DataSet 族/版本族——视图需要更强的领域形状），或手写 union 承载
// 领域约束（TestSchedule 的 schedule_type、DataSetColumn 的 type）；待后端模型细化后分批换。
export type User = components['schemas']['UserOut']
export type Project = components['schemas']['ProjectOut']
export interface Environment {
  id: number; project_id: number; name: string; base_url: string
  db_config: Record<string, any>
  login_config: Record<string, any>
  notify_config: Record<string, any>
  common_headers: Record<string, any>; success_codes?: string; timeout: number
  node_retry_count?: number | null  // 节点请求层失败自动重试次数（0/空=不重试）
  node_retry_interval?: number | null  // 节点重试间隔（秒）
  is_default: boolean; sort_order?: number; created_at?: string
  created_by?: number | null; updated_by?: number | null
  created_by_name?: string | null; updated_by_name?: string | null
}
export type ApiGroup = components['schemas']['ApiGroupOut']
export interface ApiField {
  id?: number; api_id?: number
  key: string; label?: string; field_type: string; required: boolean
  default_value?: string; remark?: string; sort_order: number
}
export interface ApiDef {
  id: number; project_id: number; group_id?: number | null; name: string; code: string; category?: string
  method: string; path: string; description?: string
  request_template: any; headers_template: Record<string, any>
  fields: ApiField[]; sort_order?: number; created_at?: string
  created_by?: number | null; updated_by?: number | null
  created_by_name?: string | null; updated_by_name?: string | null
}
export interface HarPreviewField {
  key: string; field_type: string; default_value: string; in: string; required: boolean
}
export interface HarPreviewItem {
  method: string; path: string; url: string; name: string; field_count: number
  fields: HarPreviewField[]; is_array_body: boolean; content_type: string
  _selected?: boolean  // 前端勾选状态
}
export type CaseGroup = components['schemas']['CaseGroupOut']
// ============ 四来源参数模型（2026-09-30 定案：节点入参取值单选四来源） ============
export type ParamSource = 'constant' | 'func' | 'ref' | 'sql'
/** 函数入参：常量或引用（引用允许上游变量/本节点 SQL 参数，后端逐参求值） */
export interface FuncArgSpec {
  name: string
  kind: 'const' | 'ref'
  value?: any          // kind=const
  node_id?: string     // kind=ref
  var_path?: string    // kind=ref
}
export interface ParamSpec {
  source: ParamSource
  value?: any          // constant：任意 JSON 值
  func?: string        // func：函数名（见 constants/funcRegistry）
  args?: FuncArgSpec[] // func：按关键字传参
  node_id?: string     // ref：画布节点 / __dataset__ / __suite__ / 本节点（SQL 参数结果）
  var_path?: string    // ref
  as_array?: boolean   // ref/func：单值包成单元素数组
  sql?: string         // sql：{{节点.变量}} 占位引用
  column?: string      // sql：结果列名（缺省首行首列）
}
export interface NodeParams {
  body?: Record<string, ParamSpec>
  headers?: Record<string, ParamSpec>
}
/** 数据集行内单节点入参配置（入参唯一收敛到数据集；字段设置=参数取值来源声明） */
export interface DatasetNodeParams {
  params: NodeParams
}
// ============ 契约同步（2026-10-10 定案：数据集参数 ↔ 接口字段一致性） ============
/** 契约外参数（动态来源红线：只标注不删） */
export interface ContractGapExtra {
  path: string
  source: string
  dynamic: boolean
}
export interface ContractGaps {
  missing?: string[]        // 接口字段无参数覆盖（执行按空值占位发送）
  extra?: ContractGapExtra[] // 参数路径不在接口契约内
}
/** 接口契约变更影响面条目（一个引用数据集节点） */
export interface ContractImpactItem {
  dataset_id: number; dataset_name: string
  case_id: number; case_name: string
  node_id: string; node_label: string
  gaps: ContractGaps
}
export interface ContractSyncResult {
  total: { nodes: number; added: number; removed: number; skipped_dynamic: number }
  details: Array<{ dataset_id: number; dataset_name: string; node_id: string; added: number; removed: number; skipped_dynamic: number }>
}
export interface NodeConfig {
  id?: number; case_id?: number; node_id: string; api_id?: number | null
  post_extract: any[]; assertions: any[]
  wait_after_ms?: number
}
export interface TestCase {
  id: number; project_id: number; group_id?: number | null; name: string; description?: string
  case_type?: string  // normal 普通用例 / suite 套件（成员为跨项目用例链）
  shared_vars?: string[] | null  // 套件专用：共享变量白名单（上游产出→下游注入）
  env_id?: number | null  // 绑定的执行环境（严格绑定：执行一律用它）
  env_name?: string | null  // 绑定环境名（冗余展示）
  dag_config: { nodes: any[]; edges: any[] }
  node_configs: NodeConfig[]; sort_order?: number; created_at?: string; updated_at?: string
  created_by?: number | null; updated_by?: number | null
  created_by_name?: string | null; updated_by_name?: string | null
  dataset_id?: number | null  // 绑定的数据集（数据驱动），NULL=普通用例
  last_exec_at?: string | null      // 最近一次执行开始时间（终结回写；NULL=从未执行）
  last_exec_status?: string | null  // 最近一次执行终态：success/failed/terminated
}

// 套件成员（跨项目用例引用，串行执行；环境跟随成员用例绑定）
export interface SuiteMember {
  id?: number
  member_case_id: number
  env_id?: number | null  // 成员用例绑定环境（实时值）
  sort_order?: number
  case_name?: string | null
  project_id?: number | null
  project_name?: string | null
  env_name?: string | null
  member_case_type?: string
}
export interface AssertionRecord {
  id: number; step_id: number; rule_type: string; rule_config?: any
  result?: boolean; actual_value?: string; expected_value?: string; message?: string
}
export interface StepRecord {
  id: number; execution_id: number; node_id?: string; api_name?: string
  api_path?: string; api_method?: string
  request_headers?: any; request_body?: any; response_status?: number
  response_body?: any; response_time_ms?: number
  retry_count?: number | null  // 失败自动重试实际次数（0/空=未重试）
  resumed?: boolean  // 断点续跑段产出的步骤（顶替旧失败记录）
  replay_passed_at?: string | null  // 重放验证通过时间（「已重放通过」徽标）
  started_at?: string; ended_at?: string; status?: string
  pre_process?: { type?: string; path?: string; value?: any; sql?: string }[] | null  // 历史遗留：仅老报告回显，新步骤恒 null
  post_extract?: Record<string, any>[] | null
  extracted_vars?: Record<string, any> | null
  assertions: AssertionRecord[]
}
export interface ExecutionRecord {
  id: number; case_id: number; env_id: number
  case_name?: string; env_name?: string
  project_id?: number | null; project_name?: string | null
  status: string
  started_at?: string; ended_at?: string; summary: Record<string, any>
  suite_execution_id?: number | null  // 非空=套件链成员执行，指向套件主执行记录
  dataset_id?: number | null
  dataset_row?: { row_index: number; data: Record<string, any>; label: string } | null
  steps: StepRecord[]
  created_by?: number | null; created_by_name?: string | null
  trigger_type?: string
}

export interface TestSchedule {
  id: number; case_id: number; env_id?: number | null  // 快照（实际执行环境以用例绑定为準）
  case_name?: string | null; env_name?: string | null
  schedule_type: 'interval' | 'daily'
  interval_minutes?: number | null
  daily_time?: string | null
  enabled: boolean
  last_run_at?: string | null; next_run_at?: string | null
  created_at?: string | null; updated_at?: string | null
  created_by?: number | null; created_by_name?: string | null
  updated_by?: number | null; updated_by_name?: string | null
}

export interface ProjectVersionListItem {
  id: number; project_id: number; version_no: number
  name: string; description?: string
  created_by?: number | null; created_by_name?: string | null
  created_at?: string
}

export interface ProjectVersion extends ProjectVersionListItem {
  snapshot?: {
    api_groups: any[]
    case_groups: any[]
    apis: any[]
    cases: any[]
  }
}

export interface ProjectVersionDiff {
  base: ProjectVersion
  target: ProjectVersion
  diff: {
    api_groups: CollectionDiff
    case_groups: CollectionDiff
    apis: CollectionDiff
    cases: CollectionDiff
  }
}

export interface CollectionDiff {
  added: { key: string; target: any }[]
  removed: { key: string; base: any }[]
  modified: { key: string; base: any; target: any }[]
}

// ============ Auth ============
export const authApi = {
  login: (username: string, password: string) =>
    http.post<{ token: string; user: User }>('/auth/login', { username, password }).then((r) => r.data),
  register: (username: string, password: string, name?: string) =>
    http.post<{ token: string; user: User }>('/auth/register', { username, password, name }).then((r) => r.data),
  me: () => http.get<User>('/auth/me').then((r) => r.data),
  changePassword: (newPassword: string) =>
    http.post<{ message: string }>('/auth/change-password', { new_password: newPassword }).then((r) => r.data),
  // 头像：上传（base64 data URL）/ 删除 / 按 id 查 / 按 username 查
  updateAvatar: (avatar: string) =>
    http.put<{ message: string }>('/auth/avatar', { avatar }).then((r) => r.data),
  removeAvatar: () => http.delete('/auth/avatar'),
  getAvatar: (userId: number) =>
    http.get<AvatarInfo>(`/auth/avatar/${userId}`).then((r) => r.data),
}

// ============ User 管理（仅管理员） ============
// 类型来源切到 OpenAPI 生成（npm run gen:api），消除手写镜像；形状与后端 SimpleUserOut 单一事实来源
import type { components } from '@/types/api.gen'

export type SimpleUser = components['schemas']['SimpleUserOut']
export type AvatarInfo = components['schemas']['AvatarOut']
export const userApi = {
  list: () => http.get<User[]>('/users').then((r) => r.data),
  simple: () => http.get<SimpleUser[]>('/users/simple').then((r) => r.data),
  create: (data: { username: string; password: string; name?: string; role?: string; department?: string }) =>
    http.post<User>('/users', data).then((r) => r.data),
  updateRole: (id: number, role: string) =>
    http.put<User>(`/users/${id}/role`, { role }).then((r) => r.data),
  update: (id: number, data: { username: string; name?: string | null; phone?: string | null; email?: string | null; department?: string | null; role: string }) =>
    http.put<User>(`/users/${id}`, data).then((r) => r.data),
  resetPassword: (id: number, password: string) =>
    http.put(`/users/${id}/password`, { password }),
  remove: (id: number) => http.delete(`/users/${id}`),
}

// ============ 操作日志（仅管理员） ============
export type OperationLog = components['schemas']['OperationLogOut']

export const logApi = {
  list: (params?: { action?: string; target_type?: string; user_id?: number; limit?: number; start_time?: string; end_time?: string }) =>
    http.get<OperationLog[]>('/operation-logs', { params }).then((r) => r.data),
  cleanup: (days: number) => http.delete<{ message: string; deleted: number; days: number }>('/operation-logs/cleanup', { params: { days } }).then((r) => r.data),
}

// ============ Project ============
export const projectApi = {
  list: (params?: { created_by?: number; updated_by?: number }) => http.get<Project[]>('/projects', { params }).then((r) => r.data),
  create: (data: Partial<Project>) => http.post<Project>('/projects', data).then((r) => r.data),
  update: (id: number, data: Partial<Project>) => http.put<Project>(`/projects/${id}`, data).then((r) => r.data),
  remove: (id: number) => http.delete(`/projects/${id}`),
  reorder: (items: { id: number; sort_order: number }[]) =>
    http.post<{ message: string; updated: number }>('/projects/reorder', { items }).then((r) => r.data),
}

// ============ Environment ============
export const envApi = {
  list: (projectId?: number, createdBy?: number, updatedBy?: number) => http.get<Environment[]>('/environments', { params: { project_id: projectId, created_by: createdBy, updated_by: updatedBy } }).then((r) => r.data),
  get: (id: number) => http.get<Environment>(`/environments/${id}`).then((r) => r.data),
  create: (data: Partial<Environment>) => http.post<Environment>('/environments', data).then((r) => r.data),
  update: (id: number, data: Partial<Environment>) => http.put<Environment>(`/environments/${id}`, data).then((r) => r.data),
  remove: (id: number) => http.delete(`/environments/${id}`),
  copy: (id: number) => http.post<Environment>(`/environments/${id}/copy`).then((r) => r.data),
  testDb: (id: number) => http.post<{ ok: boolean; message: string; test_result?: any }>(`/environments/${id}/test-db`).then((r) => r.data),
  testLogin: (id: number) => http.post<{ ok: boolean; message: string; auth_header_name?: string; auth_header_preview?: string; base_url?: string }>(`/environments/${id}/test-login`).then((r) => r.data),
  reorder: (items: { id: number; sort_order: number }[]) =>
    http.post<{ message: string; updated: number }>('/environments/reorder', { items }).then((r) => r.data),
}

// ============ ApiGroup ============
export const apiGroupApi = {
  list: (projectId: number) => http.get<ApiGroup[]>('/api-groups', { params: { project_id: projectId } }).then((r) => r.data),
  create: (data: { project_id: number; parent_id?: number | null; name: string; sort_order?: number }) => http.post<ApiGroup>('/api-groups', data).then((r) => r.data),
  update: (id: number, data: Partial<ApiGroup>) => http.put<ApiGroup>(`/api-groups/${id}`, data).then((r) => r.data),
  remove: (id: number) => http.delete(`/api-groups/${id}`),
}

// ============ Api ============
export const apiApi = {
  list: (projectId?: number, createdBy?: number, updatedBy?: number) => http.get<ApiDef[]>('/apis', { params: { project_id: projectId, created_by: createdBy, updated_by: updatedBy } }).then((r) => r.data),
  get: (id: number) => http.get<ApiDef>(`/apis/${id}`).then((r) => r.data),
  create: (data: Partial<ApiDef>) => http.post<ApiDef>('/apis', data).then((r) => r.data),
  update: (id: number, data: Partial<ApiDef>) => http.put<ApiDef>(`/apis/${id}`, data).then((r) => r.data),
  remove: (id: number) => http.delete(`/apis/${id}`),
  copy: (id: number) => http.post<ApiDef>(`/apis/${id}/copy`).then((r) => r.data),
  // 契约影响面/同步（接口保存或数据集保存后弹窗预览 + 用户许可后全量同步）
  contractImpact: (id: number) =>
    http.get<ContractImpactItem[]>(`/apis/${id}/contract-impact`).then((r) => r.data),
  contractSync: (id: number) =>
    http.post<ContractSyncResult>(`/apis/${id}/contract-sync`).then((r) => r.data),
  batchMove: (apiIds: number[], groupId: number | null) =>
    http.post<{ message: string; updated: number }>('/apis/batch-move', { api_ids: apiIds, group_id: groupId }).then((r) => r.data),
  reorder: (items: { id: number; sort_order: number }[]) =>
    http.post<{ message: string; updated: number }>('/apis/reorder', { items }).then((r) => r.data),
  importSpec: (projectId: number, spec: Record<string, any>, groupId?: number | null) =>
    http.post<{ message: string; imported: any[]; skipped: string[] }>('/apis/import', { project_id: projectId, group_id: groupId ?? null, spec }).then((r) => r.data),
  previewHar: (file: File) => {
    const formData = new FormData()
    formData.append('file', file)
    return http.post<{ total: number; previews: HarPreviewItem[] }>('/apis/import-har/preview', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }).then((r) => r.data)
  },
  importHar: (projectId: number, previews: HarPreviewItem[], groupId?: number | null) =>
    http.post<{ message: string; imported: any[]; skipped: string[] }>('/apis/import-har', { project_id: projectId, group_id: groupId ?? null, previews }).then((r) => r.data),
  previewCurl: (text: string) =>
    http.post<{ total: number; previews: HarPreviewItem[]; errors: string[] }>('/apis/import-curl/preview', { text }).then((r) => r.data),
  importCurl: (projectId: number, previews: HarPreviewItem[], groupId?: number | null) =>
    http.post<{ message: string; imported: any[]; skipped: string[] }>('/apis/import-curl', { project_id: projectId, group_id: groupId ?? null, previews }).then((r) => r.data),
  importFields: (apiId: number, method: string, path: string, spec: Record<string, any>) =>
    http.post<{
      matched: boolean; method: string; path: string; operation_summary: string | null
      fields: ApiField[]
    }>(`/apis/${apiId}/import-fields`, { method, path, spec }).then((r) => r.data),
  debug: (apiId: number, envId: number, bodyOverride?: Record<string, any>) =>
    http.post<{
      api_id: number; api_name: string; method: string; path: string
      request_headers: Record<string, any>; request_body: any
      response_status: number; response_body: any; response_time_ms: number
      started_at: string; ok: boolean; login_failed: boolean; error: string | null
    }>(`/apis/${apiId}/debug`, { env_id: envId, body_override: bodyOverride ?? null }).then((r) => r.data),
  // 列表导出：excel=简表 / json=全量 / openapi=OpenAPI 3.0（Postman/Apifox 可导入）；ids=勾选导出（优先于筛选）
  exportList: (params: { project_id: number; format: 'excel' | 'json' | 'openapi'; ids?: number[]; created_by?: number; updated_by?: number }) => {
    const { ids, ...rest } = params
    return http.get<Blob>('/apis/export', {
      responseType: 'blob',
      params: { ...rest, ids: ids?.length ? ids.join(',') : undefined },
    }).then((r) => r.data)
  },
}

// ============ CaseGroup ============
export const caseGroupApi = {
  list: (projectId: number) => http.get<CaseGroup[]>('/case-groups', { params: { project_id: projectId } }).then((r) => r.data),
  create: (data: { project_id: number; parent_id?: number | null; name: string; sort_order?: number }) => http.post<CaseGroup>('/case-groups', data).then((r) => r.data),
  update: (id: number, data: Partial<CaseGroup>) => http.put<CaseGroup>(`/case-groups/${id}`, data).then((r) => r.data),
  remove: (id: number) => http.delete(`/case-groups/${id}`),
}

// ============ TestCase ============
export const caseApi = {
  list: (projectId?: number, createdBy?: number, updatedBy?: number) => http.get<TestCase[]>('/testcases', { params: { project_id: projectId, created_by: createdBy, updated_by: updatedBy } }).then((r) => r.data),
  get: (id: number) => http.get<TestCase>(`/testcases/${id}`).then((r) => r.data),
  create: (data: Partial<TestCase>) => http.post<TestCase>('/testcases', data).then((r) => r.data),
  update: (id: number, data: Partial<TestCase>) => http.put<TestCase>(`/testcases/${id}`, data).then((r) => r.data),
  remove: (id: number) => http.delete(`/testcases/${id}`),
  copy: (id: number) => http.post<TestCase>(`/testcases/${id}/copy`).then((r) => r.data),
  batchMove: (caseIds: number[], groupId: number | null) =>
    http.post<{ message: string; updated: number }>('/testcases/batch-move', { case_ids: caseIds, group_id: groupId }).then((r) => r.data),
  reorder: (items: { id: number; sort_order: number }[]) =>
    http.post<{ message: string; updated: number }>('/testcases/reorder', { items }).then((r) => r.data),
  // 环境严格绑定：执行环境=用例绑定环境（case.env_id），不再传 env_id
  execute: (caseId: number, opts?: { dataset_id?: number | null }) =>
    http.post<ExecutionRecord>(`/testcases/${caseId}/execute`,
      { case_id: caseId, dataset_id: opts?.dataset_id ?? undefined }).then((r) => r.data),
  batchExecute: (caseIds: number[], counts?: number[], concurrency: number = 4) =>
    http.post<ExecutionRecord[]>('/testcases/batch-execute',
      { case_ids: caseIds, counts, concurrency }).then((r) => r.data),
  // 列表导出：excel=简表 / json=全量（含 DAG 与节点配置），筛选条件与列表页一致
  exportList: (params: { project_id: number; format: 'excel' | 'json'; created_by?: number; updated_by?: number }) =>
    http.get<Blob>('/testcases/export', { responseType: 'blob', params }).then((r) => r.data),
  // 套件成员：按执行顺序返回（带用例/项目/环境冗余名）；PUT 整体替换（编排保存语义）
  getMembers: (caseId: number) =>
    http.get<SuiteMember[]>(`/testcases/${caseId}/members`).then((r) => r.data),
  updateMembers: (caseId: number, members: { member_case_id: number; sort_order?: number }[]) =>
    http.put<SuiteMember[]>(`/testcases/${caseId}/members`, { members }).then((r) => r.data),
  // 多用例组合（拼接成新用例），caseIds 顺序即拼接顺序
  combine: (caseIds: number[], name: string, groupId?: number | null) =>
    http.post<TestCase>('/testcases/combine', { case_ids: caseIds, name, group_id: groupId ?? null }).then((r) => r.data),
  // 拆分前置扫描：返回跨界变量清单（outgoing/incoming），只需 node_ids
  scanSplit: (caseId: number, nodeIds: string[]) =>
    http.post<{ outgoing: SplitVar[]; incoming: SplitVar[] }>(`/testcases/${caseId}/scan-split`, { node_ids: nodeIds }).then((r) => r.data),
  // 执行拆分：抽离节点到新用例
  split: (caseId: number, data: { node_ids: string[]; new_name: string; new_group_id?: number | null }) =>
    http.post<{ message: string; new_case: TestCase; origin_case: TestCase }>(`/testcases/${caseId}/split`, data).then((r) => r.data),
}

export interface SplitVar {
  var: string
  providers: string[]
  consumer: string
}

// ============ TestSchedule 定时任务 ============
export interface SchedulePayload {
  case_id?: number
  schedule_type?: 'interval' | 'daily'
  interval_minutes?: number | null
  daily_time?: string | null
  enabled?: boolean
}

export const scheduleApi = {
  list: (params?: { project_id?: number; case_id?: number }) =>
    http.get<TestSchedule[]>('/schedules', { params }).then((r) => r.data),
  create: (data: Required<Pick<SchedulePayload, 'case_id' | 'schedule_type'>> & SchedulePayload) =>
    http.post<TestSchedule>('/schedules', data).then((r) => r.data),
  update: (id: number, data: SchedulePayload) =>
    http.put<TestSchedule>(`/schedules/${id}`, data).then((r) => r.data),
  remove: (id: number) => http.delete(`/schedules/${id}`),
  run: (id: number) => http.post<{ message: string }>(`/schedules/${id}/run`).then((r) => r.data),
}

// ============ DataSet 数据集（入参配置中心：每个数据集 = 各节点入参的一套完整取值） ============
/** 行数据：{"nodes": {节点ID: {params}}}（单行收敛，多数据集 = 多场景） */
export interface DataSetRow {
  id: number; dataset_id: number; row_index: number; data: { nodes?: Record<string, DatasetNodeParams> }
}
export interface DataSet {
  id: number; project_id: number; case_id: number; name: string; description?: string | null
  rows: DataSetRow[]
  case_bound_count?: number  // >0 时删除需先解绑
  created_at?: string; updated_at?: string
  created_by?: number | null; created_by_name?: string | null
  updated_by?: number | null; updated_by_name?: string | null
}
/** 参数视图单节点：接口字段定义 × 行内现值 × 静态产出（引用下拉数据源） */
export interface DatasetNodeView {
  node_id: string
  label: string
  api_id?: number | null
  api_name?: string
  fields: Record<string, any>[]
  params: NodeParams
  productions: string[]
}
export interface DatasetParamsView {
  dataset_id: number
  case_id: number
  nodes: DatasetNodeView[]
  edges: { source: string; target: string }[]
  orphan_node_ids: string[]  // 行内已配置但画布已删的节点（提示清理）
}

export const datasetApi = {
  list: (params?: { project_id?: number; case_id?: number; with_rows?: boolean }) =>
    http.get<DataSet[]>('/datasets', { params }).then((r) => r.data),
  create: (data: { project_id: number; case_id: number; name: string; description?: string }) =>
    http.post<DataSet>('/datasets', data).then((r) => r.data),
  update: (id: number, data: { name?: string; description?: string }) =>
    http.put<DataSet>(`/datasets/${id}`, data).then((r) => r.data),
  remove: (id: number) => http.delete(`/datasets/${id}`),
  // 复制：行内全部节点入参配置深拷贝，归属同用例（多场景复用）
  copy: (id: number) => http.post<DataSet>(`/datasets/${id}/copy`).then((r) => r.data),
  // 参数视图：按归属用例 DAG 节点组织（数据集页节点 tab 数据源）
  paramsView: (id: number) =>
    http.get<DatasetParamsView>(`/datasets/${id}/params-view`).then((r) => r.data),
  // 保存单节点入参配置（整体替换该节点 params，服务端含静态校验）
  saveNodeConfig: (id: number, data: { node_id: string; params: NodeParams }) =>
    http.put<DataSet>(`/datasets/${id}/node-config`, data).then((r) => r.data),
  // 清理悬空节点配置（画布节点已删）
  removeNodeConfig: (id: number, nodeId: string) =>
    http.delete(`/datasets/${id}/node-config/${encodeURIComponent(nodeId)}`).then((r) => r.data),
}

// ============ ProjectVersion 项目版本 ============
export const projectVersionApi = {
  list: (projectId: number) =>
    http.get<ProjectVersionListItem[]>(`/projects/${projectId}/versions`).then((r) => r.data),
  create: (projectId: number, data: { name: string; description?: string }) =>
    http.post<ProjectVersion>(`/projects/${projectId}/versions`, data).then((r) => r.data),
  get: (versionId: number) =>
    http.get<ProjectVersion>(`/project-versions/${versionId}`).then((r) => r.data),
  diff: (baseId: number, targetId: number) =>
    http.get<ProjectVersionDiff>(`/project-versions/${baseId}/diff`, { params: { target_id: targetId } }).then((r) => r.data),
  rollback: (versionId: number) =>
    http.post<{ message: string }>(`/project-versions/${versionId}/rollback`).then((r) => r.data),
  remove: (versionId: number) => http.delete(`/project-versions/${versionId}`),
}

// ============ Execution / Report ============
export const execApi = {
  list: (params?: { case_id?: number; project_id?: number; created_by?: number; limit?: number; offset?: number; case_name?: string; status?: string; start_time?: string; end_time?: string; sort_by?: string; order?: string }) =>
    http.get<{ items: ExecutionRecord[]; total: number }>('/executions', { params }).then((r) => r.data),
  // 近 N 天执行统计（工作台）：全量聚合口径，不受列表翻页截断影响
  stats: (params?: { days?: number; project_id?: number }) =>
    http.get<{ count: number; passed: number; rate: number | null; days: number }>('/executions/stats', { params }).then((r) => r.data),
  get: (id: number, silent?: boolean) => http.get<ExecutionRecord>(`/executions/${id}`, { silent }).then((r) => r.data),
  // 手动终止（运行中记录）：僵尸记录直接落状态；活动执行由 runner 检查点提前退出
  terminate: (id: number) => http.post<ExecutionRecord>(`/executions/${id}/terminate`).then((r) => r.data),
  // 报告详情与 get 同源（后端 /executions/{id} 单一事实源，/reports 读端点保留给外部调用方）
  report: (id: number) => http.get<ExecutionRecord>(`/executions/${id}`).then((r) => r.data),
  // 报告导出（后端组装：csv=Excel 兼容 BOM+CRLF；html=自包含单文件报告）
  exportReport: (id: number, format: 'csv' | 'html') =>
    http.get<Blob>(`/reports/executions/${id}/export`, { responseType: 'blob', params: { format } }).then((r) => r.data),
  cleanup: (days: number) => http.delete<{ message: string; deleted: number; days: number }>('/executions/cleanup', { params: { days } }).then((r) => r.data),
  // 报告页节点重放：bodyOverride 为编辑后的请求体（null=用原快照重发一次）。
  // 断点续跑配套：同口径跑断言与提取，passed=断言全过且请求成功（通过时后端打 replay_passed_at）
  replayStep: (stepId: number, bodyOverride: unknown) =>
    http.post<{ status_code: number; response_body: any; error: string | null; elapsed_ms: number; request_body: any; passed: boolean; assertions: { type: string; pass: boolean; message?: string }[]; extracted: Record<string, any> }>(
      `/executions/steps/${stepId}/replay`, { body_override: bodyOverride ?? null }).then((r) => r.data),
  // 断点续跑：从首个未成功节点用当前配置+当前数据集重新执行（仅 failed 普通报告；编排结构需与报告时一致）
  resume: (execId: number) =>
    http.post<ExecutionRecord>(`/executions/${execId}/resume`).then((r) => r.data),
}

// ============ Home 工作台 ============
export interface HomeRecentExec {
  id: number; case_id: number; case_name?: string | null
  env_id?: number | null; env_name?: string | null
  status: string; summary?: Record<string, any> | null; started_at?: string | null
}

// 首页聚合（一次请求替代 4 个重列表接口的全量拉取）
export const homeApi = {
  summary: (projectId: number, days = 7) =>
    http.get<{
      api_count: number; case_count: number
      stats: { count: number; passed: number; rate: number | null; days: number }
      recent_execs: HomeRecentExec[]
      recent_cases: { id: number; name: string }[]
    }>('/home/summary', { params: { project_id: projectId, days } }).then((r) => r.data),
}

// ============ FieldDictionary 字段字典 ============
export type FieldDictionary = components['schemas']['FieldDictionaryOut']

export const dictApi = {
  list: (projectId: number, keyword?: string) =>
    http.get<FieldDictionary[]>('/field-dictionaries', { params: { project_id: projectId, keyword } }).then((r) => r.data),
  getMap: (projectId: number) =>
    http.get<Record<string, string>>('/field-dictionaries/map', { params: { project_id: projectId } }).then((r) => r.data),
  create: (data: { project_id: number; key: string; label: string }) =>
    http.post<FieldDictionary>('/field-dictionaries', data).then((r) => r.data),
  update: (id: number, data: { key?: string; label?: string }) =>
    http.put<FieldDictionary>(`/field-dictionaries/${id}`, data).then((r) => r.data),
  remove: (id: number) => http.delete(`/field-dictionaries/${id}`),
  batch: (projectId: number, items: { key: string; label: string }[]) =>
    http.post<{ message: string; count: number }>('/field-dictionaries/batch', { project_id: projectId, items }).then((r) => r.data),
}

// ============ FileCenter 文件中心 ============
export type FileCategory = components['schemas']['FileCategoryOut']
export type TestFile = components['schemas']['FileOut']

export const fileApi = {
  // 文件 CRUD
  list: (projectId: number, params?: { category_id?: number | null; keyword?: string }) =>
    http.get<TestFile[]>('/files', { params: { project_id: projectId, ...params } }).then((r) => r.data),
  get: (id: number) => http.get<TestFile>(`/files/${id}`).then((r) => r.data),
  upload: (file: File, projectId: number, categoryId?: number | null) => {
    const formData = new FormData()
    formData.append('file', file)
    return http.post<TestFile>(`/files/upload?project_id=${projectId}${categoryId ? `&category_id=${categoryId}` : ''}`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }).then((r) => r.data)
  },
  update: (id: number, data: { name?: string; category_id?: number | null }) =>
    http.put<TestFile>(`/files/${id}`, data).then((r) => r.data),
  remove: (id: number) => http.delete<{ message: string; physical_removed: boolean }>(`/files/${id}`),
  // 下载/预览：用 axios 获取 blob（带 token），转 object URL 供 img/iframe/a 使用
  fetchBlob: (id: number, preview = false) =>
    http.get<Blob>(`/files/${id}/${preview ? 'preview' : 'download'}`, { responseType: 'blob' }).then((r) => {
      const url = URL.createObjectURL(r.data)
      return { url, blob: r.data }
    }),
}

export const fileCategoryApi = {
  list: (projectId: number) =>
    http.get<FileCategory[]>('/file-categories', { params: { project_id: projectId } }).then((r) => r.data),
  create: (data: { project_id: number; parent_id?: number | null; name: string; sort_order?: number }) =>
    http.post<FileCategory>('/file-categories', data).then((r) => r.data),
  update: (id: number, data: { name?: string; parent_id?: number | null; sort_order?: number }) =>
    http.put<FileCategory>(`/file-categories/${id}`, data).then((r) => r.data),
  remove: (id: number) => http.delete(`/file-categories/${id}`),
}

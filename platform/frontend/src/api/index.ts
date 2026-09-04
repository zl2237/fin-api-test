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
          return rejectWithMsg(JSON.parse(txt)?.detail || error?.message || '请求失败')
        } catch {
          return rejectWithMsg(error?.message || '请求失败')
        }
      })
    }
    const msg = error?.response?.data?.detail || error?.message || '请求失败'
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
  variables: Record<string, any>
  common_headers: Record<string, any>; success_codes?: string; timeout: number; is_default: boolean; sort_order?: number; created_at?: string
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
export interface NodeConfig {
  id?: number; case_id?: number; node_id: string; api_id?: number | null
  pre_process: any[]; post_extract: any[]; assertions: any[]
  wait_after_ms?: number
}
export interface TestCase {
  id: number; project_id: number; group_id?: number | null; name: string; description?: string
  dag_config: { nodes: any[]; edges: any[] }
  node_configs: NodeConfig[]; sort_order?: number; created_at?: string; updated_at?: string
  created_by?: number | null; updated_by?: number | null
  created_by_name?: string | null; updated_by_name?: string | null
  dataset_id?: number | null  // 绑定的数据集（数据驱动），NULL=普通用例
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
  started_at?: string; ended_at?: string; status?: string
  pre_process?: { type?: string; path?: string; value?: any; sql?: string }[] | null
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
  dataset_id?: number | null
  dataset_row?: { row_index: number; data: Record<string, any>; label: string } | null
  steps: StepRecord[]
  created_by?: number | null; created_by_name?: string | null
  trigger_type?: string
}

export interface TestSchedule {
  id: number; case_id: number; env_id: number
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
  get: (id: number) => http.get<Project>(`/projects/${id}`).then((r) => r.data),
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
  // 列表导出：excel=简表 / json=全量，筛选条件与列表页一致
  exportList: (params: { project_id: number; format: 'excel' | 'json'; created_by?: number; updated_by?: number }) =>
    http.get<Blob>('/apis/export', { responseType: 'blob', params }).then((r) => r.data),
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
  execute: (caseId: number, envId: number, opts?: { dataset_id?: number | null; row_ids?: number[] }) =>
    http.post<ExecutionRecord>(`/testcases/${caseId}/execute`,
      { case_id: caseId, env_id: envId, dataset_id: opts?.dataset_id ?? undefined, row_ids: opts?.row_ids ?? undefined }).then((r) => r.data),
  batchExecute: (caseIds: number[], envId: number, counts?: number[], concurrency: number = 4) =>
    http.post<ExecutionRecord[]>('/testcases/batch-execute',
      { case_ids: caseIds, env_id: envId, counts, concurrency }).then((r) => r.data),
  // 列表导出：excel=简表 / json=全量（含 DAG 与节点配置），筛选条件与列表页一致
  exportList: (params: { project_id: number; format: 'excel' | 'json'; created_by?: number; updated_by?: number }) =>
    http.get<Blob>('/testcases/export', { responseType: 'blob', params }).then((r) => r.data),
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
  env_id?: number
  schedule_type?: 'interval' | 'daily'
  interval_minutes?: number | null
  daily_time?: string | null
  enabled?: boolean
}

export const scheduleApi = {
  list: (params?: { project_id?: number; case_id?: number }) =>
    http.get<TestSchedule[]>('/schedules', { params }).then((r) => r.data),
  create: (data: Required<Pick<SchedulePayload, 'case_id' | 'env_id' | 'schedule_type'>> & SchedulePayload) =>
    http.post<TestSchedule>('/schedules', data).then((r) => r.data),
  update: (id: number, data: SchedulePayload) =>
    http.put<TestSchedule>(`/schedules/${id}`, data).then((r) => r.data),
  remove: (id: number) => http.delete(`/schedules/${id}`),
  run: (id: number) => http.post<{ message: string }>(`/schedules/${id}/run`).then((r) => r.data),
}

// ============ DataSet 数据集（数据驱动测试，用例私有 1:N） ============
export interface DataSetColumn {
  key: string; type: 'string' | 'int' | 'bool' | 'array' | 'object' | 'file'  // file=文件中心文件 ID；中文名实时引用字段字典，缺失显 key
  origin?: any  // 快照原值（生成列携带）：执行时快照保真比对基准，手工列无
}
export interface DataSetNodeConfig {  // 节点配置快照（只读；保存用例自动同步，手动 resync 兜底）
  node_id: string; api_id?: number | null
  pre_process?: any[]; post_extract?: any[]; assertions?: any[]; wait_after_ms?: number
}
export interface DataSetRow {
  id: number; dataset_id: number; row_index: number; data: Record<string, any>
}
export interface DataSet {
  id: number; project_id: number; case_id: number; name: string; description?: string | null
  columns: DataSetColumn[]; rows: DataSetRow[]; node_configs?: DataSetNodeConfig[]
  case_bound_count?: number  // ≤1（用例私有），>0 时删除需先解绑
  created_at?: string; updated_at?: string
  created_by?: number | null; created_by_name?: string | null
  updated_by?: number | null; updated_by_name?: string | null
}

export const datasetApi = {
  list: (params?: { project_id?: number; case_id?: number; with_rows?: boolean }) =>
    http.get<DataSet[]>('/datasets', { params }).then((r) => r.data),
  get: (id: number) => http.get<DataSet>(`/datasets/${id}`).then((r) => r.data),
  create: (data: { project_id: number; case_id: number; name: string; description?: string; columns: DataSetColumn[] }) =>
    http.post<DataSet>('/datasets', data).then((r) => r.data),
  update: (id: number, data: { name?: string; description?: string; columns?: DataSetColumn[] }) =>
    http.put<DataSet>(`/datasets/${id}`, data).then((r) => r.data),
  remove: (id: number) => http.delete(`/datasets/${id}`),
  // 复制：列/行/节点配置快照全量深拷贝，归属同用例
  copy: (id: number) => http.post<DataSet>(`/datasets/${id}/copy`).then((r) => r.data),
  // 重新同步节点配置快照：用例当前编排整块替换（列/行不动）。
  // 保存用例（编排有改动）时后端已自动同步全部绑定数据集，此为手动兜底入口
  resync: (id: number) =>
    http.post<{ message: string; nodes: number }>(`/datasets/${id}/resync`).then((r) => r.data),
  // 快照过期检测：节点配置快照 vs 用例当前编排 的字段级差异
  drift: (id: number) =>
    http.get<{ stale: boolean; nodes: { node_id: string; label: string; changes: string[] }[] }>(`/datasets/${id}/drift`).then((r) => r.data),
  // 从用例生成：收集用例全部写死请求参数各成一列 + 1 行原值快照
  generate: (caseId: number, name?: string) =>
    http.post<{
      dataset: DataSet
      stats: { nodes: number; columns: number; dynamic: number; nested: number; empty: number; invalid: number; conflicts: { key: string; values: any[] }[] }
    }>('/datasets/generate', { case_id: caseId, name: name || undefined }).then((r) => r.data),
  // 行操作
  listRows: (id: number) => http.get<DataSetRow[]>(`/datasets/${id}/rows`).then((r) => r.data),
  addRow: (id: number, data: Record<string, any>) =>
    http.post<DataSetRow>(`/datasets/${id}/rows`, { data }).then((r) => r.data),
  replaceRows: (id: number, rows: Record<string, any>[]) =>
    http.put<DataSetRow[]>(`/datasets/${id}/rows`, { rows }).then((r) => r.data),
  clearRows: (id: number) => http.delete(`/datasets/${id}/rows`),
  updateRow: (id: number, rowId: number, data: Record<string, any>) =>
    http.put<DataSetRow>(`/datasets/${id}/rows/${rowId}`, { data }).then((r) => r.data),
  copyRow: (id: number, rowId: number) =>
    http.post<DataSetRow>(`/datasets/${id}/rows/${rowId}/copy`).then((r) => r.data),
  removeRow: (id: number, rowId: number) => http.delete(`/datasets/${id}/rows/${rowId}`),
  // 导入：preview=true 只解析返回预览；否则整体替换落库
  importFile: (id: number, file: File, preview = false) => {
    const form = new FormData()
    form.append('file', file)
    return http.post<{ preview: boolean; count: number; rows?: Record<string, any>[]; warnings: string[] }>(
      `/datasets/${id}/import`, form, { params: { preview } }).then((r) => r.data)
  },
  // 行导出 xlsx（与导入对偶：表头=列 key，object/array 为 JSON 字符串）
  exportRows: (id: number) =>
    http.get<Blob>(`/datasets/${id}/export`, { responseType: 'blob' }).then((r) => r.data),
  // 数据集间对比：按 api_id 配对相同节点，返回可覆盖列（空=无覆盖必要）
  mergePreview: (id: number, sourceId: number) =>
    http.get<{ source: { id: number; name: string; rows: number; row_labels: string[] }; common_nodes: { api_id: number; api_name: string; columns: string[] }[]; columns_total: number }>(
      `/datasets/${id}/merge-preview`, { params: { source_dataset_id: sourceId } }).then((r) => r.data),
  // 覆盖合并：源数据集指定行的相同节点涉及列值刷到目标全部行
  merge: (id: number, data: { source_dataset_id: number; api_ids?: number[]; source_row_index?: number }) =>
    http.post<{ message: string; rows: number; columns: number; keys: string[] }>(`/datasets/${id}/merge`, data).then((r) => r.data),
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
  report: (id: number) => http.get<ExecutionRecord>(`/reports/executions/${id}`).then((r) => r.data),
  // 报告导出（后端组装：csv=Excel 兼容 BOM+CRLF；html=自包含单文件报告）
  exportReport: (id: number, format: 'csv' | 'html') =>
    http.get<Blob>(`/reports/executions/${id}/export`, { responseType: 'blob', params: { format } }).then((r) => r.data),
  cleanup: (days: number) => http.delete<{ message: string; deleted: number; days: number }>('/executions/cleanup', { params: { days } }).then((r) => r.data),
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

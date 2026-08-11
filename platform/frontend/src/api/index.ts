import axios from 'axios'
import { startProgress, doneProgress } from '@/utils/requestProgress'

const http = axios.create({
  baseURL: '/api',
  timeout: 60000,
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
    const msg = error?.response?.data?.detail || error?.message || '请求失败'
    return Promise.reject(new Error(msg))
  },
)

// ============ 类型 ============
export interface User {
  id: number; username: string; name?: string; role: string; must_change_password?: boolean; created_at?: string
  created_by?: number | null; updated_by?: number | null
  created_by_name?: string | null; updated_by_name?: string | null
  has_avatar?: boolean
}
export interface Project {
  id: number; name: string; description?: string; created_at?: string
  created_by?: number | null; updated_by?: number | null
  created_by_name?: string | null; updated_by_name?: string | null
}
export interface Environment {
  id: number; project_id: number; name: string; base_url: string
  db_config: Record<string, any>
  login_config: Record<string, any>
  notify_config: Record<string, any>
  variables: Record<string, any>
  common_headers: Record<string, any>; timeout: number; is_default: boolean; created_at?: string
  created_by?: number | null; updated_by?: number | null
  created_by_name?: string | null; updated_by_name?: string | null
}
export interface ApiGroup {
  id: number; project_id: number; parent_id?: number | null; name: string; sort_order: number; created_at?: string
}
export interface ApiField {
  id?: number; api_id?: number
  key: string; label?: string; field_type: string; required: boolean
  default_value?: string; remark?: string; sort_order: number
}
export interface ApiDef {
  id: number; project_id: number; group_id?: number | null; name: string; code: string; category?: string
  method: string; path: string; description?: string
  request_template: Record<string, any>; headers_template: Record<string, any>
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
export interface CaseGroup {
  id: number; project_id: number; parent_id?: number | null; name: string; sort_order: number; created_at?: string
}
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
  assertions: AssertionRecord[]
}
export interface ExecutionRecord {
  id: number; case_id: number; env_id: number
  case_name?: string; env_name?: string
  project_id?: number | null; project_name?: string | null
  status: string
  started_at?: string; ended_at?: string; summary: Record<string, any>
  steps: StepRecord[]
  created_by?: number | null; created_by_name?: string | null
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
    http.get<{ avatar: string | null; name: string }>(`/auth/avatar/${userId}`).then((r) => r.data),
  getAvatarByUsername: (username: string) =>
    http.get<{ avatar: string | null; name: string }>(`/auth/avatar/by-username/${username}`).then((r) => r.data),
}

// ============ User 管理（仅管理员） ============
export interface SimpleUser {
  id: number
  name: string
}
export const userApi = {
  list: () => http.get<User[]>('/users').then((r) => r.data),
  simple: () => http.get<SimpleUser[]>('/users/simple').then((r) => r.data),
  create: (data: { username: string; password: string; name?: string; role?: string }) =>
    http.post<User>('/users', data).then((r) => r.data),
  updateRole: (id: number, role: string) =>
    http.put<User>(`/users/${id}/role`, { role }).then((r) => r.data),
  resetPassword: (id: number, password: string) =>
    http.put(`/users/${id}/password`, { password }),
  remove: (id: number) => http.delete(`/users/${id}`),
}

// ============ 操作日志（仅管理员） ============
export interface OperationLog {
  id: number
  user_id: number | null
  username: string | null
  action: string
  target_type: string
  target_id: number | null
  target_name: string | null
  detail: string | null
  created_at: string | null
}

export const logApi = {
  list: (params?: { action?: string; target_type?: string; user_id?: number; limit?: number }) =>
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
  execute: (caseId: number, envId: number) =>
    http.post<ExecutionRecord>(`/testcases/${caseId}/execute`, { case_id: caseId, env_id: envId }).then((r) => r.data),
  batchExecute: (caseIds: number[], envId: number) =>
    http.post<ExecutionRecord[]>('/testcases/batch-execute', { case_ids: caseIds, env_id: envId }).then((r) => r.data),
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
  list: (params?: { case_id?: number; project_id?: number; created_by?: number; limit?: number }) =>
    http.get<ExecutionRecord[]>('/executions', { params }).then((r) => r.data),
  get: (id: number, silent?: boolean) => http.get<ExecutionRecord>(`/executions/${id}`, { silent }).then((r) => r.data),
  report: (id: number) => http.get<ExecutionRecord>(`/reports/executions/${id}`).then((r) => r.data),
  cleanup: (days: number) => http.delete<{ message: string; deleted: number; days: number }>('/executions/cleanup', { params: { days } }).then((r) => r.data),
}

// ============ FieldDictionary 字段字典 ============
export interface FieldDictionary {
  id: number; project_id: number; key: string; label: string
  created_at?: string; updated_at?: string
  created_by?: number | null; updated_by?: number | null
  created_by_name?: string | null; updated_by_name?: string | null
}

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

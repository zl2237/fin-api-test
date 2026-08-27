<template>
  <div class="api-edit">
    <!-- 顶部工具栏 -->
    <div class="edit-header">
      <el-button @click="onBack">
        <el-icon><ArrowLeft /></el-icon>返回
      </el-button>
      <span class="edit-title">{{ isEdit ? '编辑接口' : '新建接口' }}</span>
      <div class="header-right">
        <span v-if="dirty" class="dirty-tip">有未保存改动</span>
        <el-button v-if="isEdit" :disabled="loading" @click="showImportFieldsDialog = true">导入覆盖字段</el-button>
        <el-button v-if="isEdit" type="success" :loading="debugging" :disabled="loading" @click="openDebug">调试</el-button>
        <el-button type="primary" :loading="saving" :disabled="loading" @click="onSave">保存</el-button>
      </div>
    </div>

    <!-- 调试弹窗 -->
    <el-dialog v-model="debugVisible" title="接口调试" width="780px" align-center :close-on-click-modal="false">
      <div class="debug-bar">
        <el-select v-model="debugEnvId" placeholder="选择环境" style="width: 200px" :disabled="debugging">
          <el-option v-for="e in store.environments" :key="e.id" :label="e.name" :value="e.id" />
        </el-select>
        <el-button type="success" :loading="debugging" :disabled="!debugEnvId" @click="onDebug">
          发送请求
        </el-button>
        <span v-if="debugResult" class="debug-meta">
          <el-tag :type="debugResult.ok ? 'success' : 'danger'" size="small" effect="plain" round>
            {{ debugResult.ok ? '成功' : '失败' }}
          </el-tag>
          <el-tag v-if="debugResult.response_status" size="small" type="info" effect="plain" round>
            HTTP {{ debugResult.response_status }}
          </el-tag>
          <el-tag size="small" type="info" effect="plain" round>
            {{ debugResult.response_time_ms }} ms
          </el-tag>
        </span>
      </div>
      <el-alert v-if="debugResult?.login_failed" type="error" :closable="false" show-icon style="margin: 8px 0">
        登录失败：{{ debugResult.error }}
      </el-alert>
      <el-alert v-else-if="debugResult?.error" type="warning" :closable="false" show-icon style="margin: 8px 0">
        {{ debugResult.error }}
      </el-alert>

      <el-tabs v-if="debugResult" v-model="debugTab" class="debug-tabs">
        <el-tab-pane label="请求" name="request">
          <div class="debug-section">
            <div class="debug-section-title">请求头</div>
            <pre class="debug-json">{{ formatJson(debugResult.request_headers) }}</pre>
          </div>
          <div class="debug-section">
            <div class="debug-section-title">请求体</div>
            <pre class="debug-json">{{ formatJson(debugResult.request_body) }}</pre>
          </div>
        </el-tab-pane>
        <el-tab-pane label="响应" name="response">
          <div class="debug-section">
            <div class="debug-section-title">响应体</div>
            <pre class="debug-json">{{ formatJson(debugResult.response_body) }}</pre>
          </div>
        </el-tab-pane>
      </el-tabs>
      <EmptyState v-else description="选择环境后点「发送请求」" :image-size="60" />
    </el-dialog>

    <!-- 导入覆盖字段弹窗（cURL 粘贴 / HAR 上传 / OpenAPI 粘贴） -->
    <el-dialog v-model="showImportFieldsDialog" title="导入覆盖字段" width="900px" align-center :close-on-click-modal="false" @close="onImportFieldsClose">
      <div class="import-fields-body">
        <el-alert type="info" :closable="false" show-icon style="margin-bottom: 12px">
          粘贴 cURL 命令、上传 HAR 或粘贴 Swagger/OpenAPI JSON，系统按当前接口的 method+path 定位，解析出最新字段列表后展示新旧对比，确认后覆盖当前字段（不会自动保存，需点顶部「保存」）。
        </el-alert>
        <div class="locate-row" style="margin-bottom: 12px;">
          <span class="locate-label">定位依据：</span>
          <span class="locate-info">{{ formData.method }} {{ formData.path }}</span>
        </div>
        <el-tabs v-model="importFieldsTab" class="import-fields-tabs">
          <!-- Tab 1: cURL 命令粘贴（默认） -->
          <el-tab-pane label="cURL 命令" name="curl">
            <el-form label-width="90px">
              <el-form-item label="cURL 命令">
                <el-input
                  v-model="importFieldsCurlText"
                  type="textarea"
                  :rows="8"
                  placeholder="粘贴 cURL 命令，系统按当前接口 method+path 自动匹配并解析字段"
                />
              </el-form-item>
              <el-form-item>
                <el-button type="primary" :loading="importFieldsCurlParsing" @click="onImportFieldsCurlParse">
                  <el-icon style="margin-right: 4px;"><Search /></el-icon>
                  解析
                </el-button>
              </el-form-item>
            </el-form>
          </el-tab-pane>

          <!-- Tab 2: HAR 文件上传 -->
          <el-tab-pane label="HAR 文件上传" name="har">
            <el-upload
              :auto-upload="true"
              :show-file-list="false"
              :before-upload="onImportFieldsHarBeforeUpload"
              :http-request="onImportFieldsHarUpload"
              accept=".har"
              style="margin-bottom: 12px;"
            >
              <el-button type="primary" :loading="importFieldsHarParsing">
                <el-icon style="margin-right: 4px;"><Upload /></el-icon>
                选择 HAR 文件
              </el-button>
              <template #tip>
                <div class="el-upload__tip">浏览器开发者工具 → Network → 右键 → Save all as HAR，直接上传</div>
              </template>
            </el-upload>
          </el-tab-pane>

          <!-- Tab 3: OpenAPI 粘贴 -->
          <el-tab-pane label="OpenAPI / Swagger" name="openapi">
            <el-form label-width="90px">
              <el-form-item label="Swagger JSON">
                <el-input
                  v-model="importFieldsSpecText"
                  type="textarea"
                  :rows="10"
                  placeholder="粘贴完整的 Swagger/OpenAPI JSON（支持 2.0 和 3.0）"
                />
              </el-form-item>
            </el-form>
          </el-tab-pane>
        </el-tabs>

        <!-- 解析结果：新旧字段对比 -->
        <div v-if="importFieldsResult" class="fields-compare">
          <div v-if="!importFieldsResult.matched" class="compare-empty">
            <el-alert type="warning" :closable="false" show-icon>
              未找到 {{ formData.method }} {{ formData.path }} 对应的接口，请检查路径是否一致。
            </el-alert>
          </div>
          <template v-else>
            <div class="compare-header">
              <span class="compare-title">
                匹配到：{{ importFieldsResult.method }} {{ importFieldsResult.path }}
                <el-tag size="small" type="info" effect="plain" round style="margin-left: 8px">
                  {{ importFieldsResult.operation_summary }}
                </el-tag>
              </span>
              <span class="compare-stat">
                新 {{ newFieldKeys.length }} 个，旧 {{ formData.fields.length }} 个，
                新增 {{ addedFieldKeys.length }}，删除 {{ removedFieldKeys.length }}，更新 {{ updatedFieldKeys.length }}
              </span>
            </div>
            <el-table :data="fieldCompareRows" size="small" border max-height="360" empty-text="暂无差异，字段定义一致">
              <el-table-column label="字段路径" min-width="180" show-overflow-tooltip>
                <template #default="{ row }">
                  <span :class="{ 'field-added': row.status === 'added', 'field-removed': row.status === 'removed' }">
                    {{ row.key }}
                  </span>
                </template>
              </el-table-column>
              <el-table-column label="状态" width="90">
                <template #default="{ row }">
                  <el-tag size="small" :type="compareTagType(row.status)" effect="plain" round>
                    {{ compareStatusLabel(row.status) }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column label="新类型" width="90">
                <template #default="{ row }">{{ row.new_type || '—' }}</template>
              </el-table-column>
              <el-table-column label="旧类型" width="90">
                <template #default="{ row }">{{ row.old_type || '—' }}</template>
              </el-table-column>
              <el-table-column label="新默认值" min-width="150">
                <template #default="{ row }">{{ row.new_default || '—' }}</template>
              </el-table-column>
              <el-table-column label="旧默认值" min-width="150">
                <template #default="{ row }">{{ row.old_default || '—' }}</template>
              </el-table-column>
            </el-table>
          </template>
        </div>
      </div>
      <template #footer>
        <el-button @click="showImportFieldsDialog = false">取消</el-button>
        <el-button v-if="importFieldsTab === 'curl'" :loading="importFieldsCurlParsing" type="primary" @click="onImportFieldsCurlParse">解析</el-button>
        <el-button v-if="importFieldsTab === 'openapi'" :loading="importFieldsLoading" type="primary" @click="onParseFields">解析</el-button>
        <el-button
          v-if="importFieldsResult?.matched"
          type="success"
          @click="onApplyFields"
        >覆盖字段（{{ newFieldKeys.length }} 个）</el-button>
      </template>
    </el-dialog>

    <!-- 主体：左右布局 -->
    <div class="edit-body" v-loading="loading" element-loading-text="加载接口配置中...">
      <!-- 左侧：基础信息 -->
      <div class="basic-panel">
        <div class="panel-title">基础信息</div>
        <el-form label-width="90px" :model="formData">
          <el-form-item label="接口名称" required>
            <el-input v-model="formData.name" placeholder="创建订单" />
          </el-form-item>
          <el-form-item label="接口编码" required>
            <el-input v-model="formData.code" placeholder="order_create" />
          </el-form-item>
          <el-form-item label="接口分组">
            <el-select v-model="formData.group_id" placeholder="选择分组 / 输入搜索" clearable filterable style="width: 100%">
              <el-option v-for="g in groups" :key="g.id" :label="g.name" :value="g.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="请求方法">
            <el-select v-model="formData.method" style="width: 100%">
              <el-option label="GET" value="GET" />
              <el-option label="POST" value="POST" />
              <el-option label="PUT" value="PUT" />
              <el-option label="DELETE" value="DELETE" />
            </el-select>
          </el-form-item>
          <el-form-item label="请求路径" required>
            <el-input v-model="formData.path" placeholder="/api/order/orderEntrust/orderAdd" />
          </el-form-item>
          <el-form-item label="描述">
            <el-input v-model="formData.description" type="textarea" :rows="2" placeholder="可选" />
          </el-form-item>
          <el-form-item label="请求体类型">
            <el-switch v-model="formData.is_array_body" active-text="数组 [{...}]" inactive-text="对象 {...}" />
          </el-form-item>
        </el-form>
      </div>

      <!-- 右侧：字段级请求模板 -->
      <div class="fields-panel">
        <div class="panel-title">
          请求字段配置
          <span class="panel-hint">支持点号嵌套路径，默认值支持 ${} 表达式</span>
        </div>
        <FieldTable v-model="formData.fields" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, reactive, watch, nextTick } from 'vue'
import { useRoute, useRouter, onBeforeRouteLeave } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowLeft, Upload, Search } from '@element-plus/icons-vue'
import { apiApi, apiGroupApi, type ApiDef, type ApiField, type ApiGroup } from '@/api'
import EmptyState from '@/components/EmptyState.vue'
import FieldTable from '@/components/FieldTable.vue'
import { useAppStore } from '@/stores'
import { useTabStore } from '@/stores/tabs'
import { storeToRefs } from 'pinia'

const route = useRoute()
const router = useRouter()
const store = useAppStore()
const tabStore = useTabStore()
const { currentProjectId } = storeToRefs(store)

const projectId = computed(() => currentProjectId.value)
const isEdit = computed(() => !!route.params.id)
const saving = ref(false)
const dirty = ref(false)
const loading = ref(false)
const groups = ref<ApiGroup[]>([])

// ===== 调试 =====
const debugVisible = ref(false)
const debugging = ref(false)
const debugEnvId = ref<number | null>(null)
const debugResult = ref<any>(null)
const debugTab = ref('request')

// ===== 导入覆盖字段（cURL 粘贴 / HAR 上传 / OpenAPI 粘贴）=====
const showImportFieldsDialog = ref(false)
const importFieldsLoading = ref(false)
const importFieldsSpecText = ref('')
const importFieldsTab = ref<'curl' | 'har' | 'openapi'>('curl')
// cURL 解析相关
const importFieldsCurlText = ref('')
const importFieldsCurlParsing = ref(false)
// HAR 解析相关
const importFieldsHarParsing = ref(false)
const importFieldsResult = ref<{
  matched: boolean; method: string; path: string; operation_summary: string | null
  fields: ApiField[]
} | null>(null)

// 新字段 key 集合
const newFieldKeys = computed(() => (importFieldsResult.value?.fields || []).map((f) => f.key))
// 旧字段 key → 字段对象 映射
const oldFieldMap = computed(() => {
  const m = new Map<string, ApiField>()
  formData.fields.forEach((f) => { if (f.key) m.set(f.key, f) })
  return m
})
// 新增：新字段中有、旧字段中没有的 key
const addedFieldKeys = computed(() =>
  newFieldKeys.value.filter((k) => !oldFieldMap.value.has(k))
)
// 删除：旧字段中有、新字段中没有的 key
const removedFieldKeys = computed(() =>
  formData.fields.filter((f) => f.key && !newFieldKeys.value.includes(f.key)).map((f) => f.key)
)
// 更新：新旧都有但类型或默认值变化的 key
const updatedFieldKeys = computed(() => {
  const result: string[] = []
  for (const nf of importFieldsResult.value?.fields || []) {
    const of = oldFieldMap.value.get(nf.key)
    if (of && (of.field_type !== nf.field_type || (of.default_value || '') !== (nf.default_value || ''))) {
      result.push(nf.key)
    }
  }
  return result
})
// 对比表格行：新增 + 删除 + 更新/不变，按新字段顺序排，删除的追加到末尾
const fieldCompareRows = computed(() => {
  const rows: any[] = []
  const newKeys = new Set<string>()
  for (const nf of importFieldsResult.value?.fields || []) {
    newKeys.add(nf.key)
    const of = oldFieldMap.value.get(nf.key)
    let status: 'added' | 'removed' | 'updated' | 'same' = 'same'
    if (!of) status = 'added'
    else if (of.field_type !== nf.field_type || (of.default_value || '') !== (nf.default_value || '')) status = 'updated'
    rows.push({
      key: nf.key, status,
      new_type: nf.field_type, old_type: of?.field_type || '',
      new_default: nf.default_value || '', old_default: of?.default_value || '',
    })
  }
  // 旧字段中已删除的追加
  for (const f of formData.fields) {
    if (f.key && !newKeys.has(f.key)) {
      rows.push({
        key: f.key, status: 'removed',
        new_type: '', old_type: f.field_type,
        new_default: '', old_default: f.default_value || '',
      })
    }
  }
  return rows
})

function compareTagType(status: string): 'success' | 'danger' | 'warning' | 'info' {
  if (status === 'added') return 'success'
  if (status === 'removed') return 'danger'
  if (status === 'updated') return 'warning'
  return 'info'
}
function compareStatusLabel(status: string): string {
  if (status === 'added') return '新增'
  if (status === 'removed') return '删除'
  if (status === 'updated') return '更新'
  return '不变'
}

// cURL 解析：按当前接口 method+path 自动匹配，解析字段并构造对比结果
async function onImportFieldsCurlParse() {
  if (!importFieldsCurlText.value.trim()) {
    ElMessage.warning('请粘贴 cURL 命令')
    return
  }
  importFieldsCurlParsing.value = true
  importFieldsResult.value = null
  try {
    const res = await apiApi.previewCurl(importFieldsCurlText.value)
    if (res.total === 0) {
      ElMessage.warning('未解析出有效接口')
      return
    }
    // 按当前接口 method + path 精确匹配
    const matched = res.previews.find(
      (p) => p.method.toUpperCase() === formData.method.toUpperCase()
        && p.path === formData.path
    )
    if (!matched) {
      importFieldsResult.value = {
        matched: false,
        method: formData.method,
        path: formData.path,
        operation_summary: null,
        fields: [],
      }
      ElMessage.warning(`未在 cURL 中找到 ${formData.method} ${formData.path}，请确认路径一致`)
      return
    }
    // 把 cURL 字段映射为 ApiField 结构（与 HAR 覆盖字段逻辑一致）
    const fields: ApiField[] = matched.fields.map((f: any, i: number) => ({
      key: f.key,
      label: '',
      field_type: f.field_type,
      required: f.required,
      default_value: f.default_value || '',
      remark: '',
      sort_order: i,
    }))
    importFieldsResult.value = {
      matched: true,
      method: matched.method,
      path: matched.path,
      operation_summary: matched.name,
      fields,
    }
    ElMessage.success(`匹配成功：${fields.length} 个字段（新增 ${addedFieldKeys.value.length}，删除 ${removedFieldKeys.value.length}，更新 ${updatedFieldKeys.value.length}）`)
  } catch (e: any) {
    ElMessage.error(e.message || 'cURL 解析失败')
  } finally {
    importFieldsCurlParsing.value = false
  }
}

// HAR 上传前校验
function onImportFieldsHarBeforeUpload(file: File): boolean {
  if (!file.name.toLowerCase().endsWith('.har')) {
    ElMessage.error('请上传 .har 文件')
    return false
  }
  if (file.size > 50 * 1024 * 1024) {
    ElMessage.error('文件超过 50MB 限制')
    return false
  }
  return true
}

// HAR 上传 + 解析：按当前接口 method+path 从 HAR 预览中匹配，构造对比结果
async function onImportFieldsHarUpload(options: any) {
  const file = options.file as File
  importFieldsHarParsing.value = true
  importFieldsResult.value = null
  try {
    const res = await apiApi.previewHar(file)
    if (res.total === 0) {
      ElMessage.warning('HAR 文件中未解析出有效接口')
      return
    }
    // 按当前接口 method + path 精确匹配
    const matched = res.previews.find(
      (p) => p.method.toUpperCase() === formData.method.toUpperCase()
        && p.path === formData.path
    )
    if (!matched) {
      importFieldsResult.value = {
        matched: false,
        method: formData.method,
        path: formData.path,
        operation_summary: null,
        fields: [],
      }
      ElMessage.warning(`未在 HAR 中找到 ${formData.method} ${formData.path}，请确认路径一致`)
      return
    }
    // 把 HAR 字段映射为 ApiField 结构
    const fields: ApiField[] = matched.fields.map((f, i) => ({
      key: f.key,
      label: '',
      field_type: f.field_type,
      required: f.required,
      default_value: f.default_value || '',
      remark: '',
      sort_order: i,
    }))
    importFieldsResult.value = {
      matched: true,
      method: matched.method,
      path: matched.path,
      operation_summary: matched.name,
      fields,
    }
    ElMessage.success(`匹配成功：${fields.length} 个字段（新增 ${addedFieldKeys.value.length}，删除 ${removedFieldKeys.value.length}，更新 ${updatedFieldKeys.value.length}）`)
  } catch (e: any) {
    ElMessage.error(e.message || 'HAR 解析失败')
  } finally {
    importFieldsHarParsing.value = false
  }
}

// 关闭导入弹窗时重置状态
function onImportFieldsClose() {
  importFieldsResult.value = null
  importFieldsSpecText.value = ''
  importFieldsCurlText.value = ''
  importFieldsTab.value = 'curl'
}

async function onParseFields() {
  if (!importFieldsSpecText.value.trim()) {
    ElMessage.warning('请粘贴 Swagger JSON')
    return
  }
  let spec: Record<string, any>
  try {
    spec = JSON.parse(importFieldsSpecText.value)
  } catch (e: any) {
    ElMessage.error('Swagger JSON 解析失败：' + e.message)
    return
  }
  if (!spec.paths) {
    ElMessage.error('未找到 paths 字段，请粘贴完整的 Swagger/OpenAPI JSON')
    return
  }
  importFieldsLoading.value = true
  try {
    const res = await apiApi.importFields(formData.id!, formData.method, formData.path, spec)
    importFieldsResult.value = res
    if (!res.matched) {
      ElMessage.warning(`未匹配到 ${formData.method} ${formData.path}，请确认路径一致`)
    } else {
      ElMessage.success(`解析成功：${res.fields.length} 个字段（新增 ${addedFieldKeys.value.length}，删除 ${removedFieldKeys.value.length}，更新 ${updatedFieldKeys.value.length}）`)
    }
  } catch (e: any) {
    ElMessage.error(e.message || '解析失败')
  } finally {
    importFieldsLoading.value = false
  }
}

function onApplyFields() {
  if (!importFieldsResult.value?.matched) return
  const newFields = importFieldsResult.value.fields.map((f, i) => ({ ...f, sort_order: i }))
  formData.fields = newFields
  ElMessage.success(`已覆盖为 ${newFields.length} 个字段，请点顶部「保存」生效`)
  showImportFieldsDialog.value = false
  importFieldsResult.value = null
  importFieldsSpecText.value = ''
  importFieldsCurlText.value = ''
}

function formatJson(v: any): string {
  try {
    return JSON.stringify(v, null, 2)
  } catch {
    return String(v)
  }
}

function openDebug() {
  if (!isEdit.value) return
  if (!store.environments.length) {
    ElMessage.warning('当前项目暂无环境，请先到环境配置创建')
    return
  }
  debugResult.value = null
  debugTab.value = 'request'
  if (!debugEnvId.value && store.environments.length) {
    debugEnvId.value = store.environments[0].id
  }
  debugVisible.value = true
}

async function onDebug() {
  if (!debugEnvId.value || !formData.id) return
  debugging.value = true
  try {
    debugResult.value = await apiApi.debug(formData.id, debugEnvId.value)
  } catch (e: any) {
    ElMessage.error(e.message || '调试失败')
  } finally {
    debugging.value = false
  }
}

interface ApiFormData {
  id?: number
  name: string
  code: string
  group_id: number | null
  method: string
  path: string
  description: string
  fields: ApiField[]
  is_array_body: boolean
}

const formData = reactive<ApiFormData>({
  name: '',
  code: '',
  group_id: null,
  method: 'POST',
  path: '',
  description: '',
  fields: [],
  is_array_body: false,
})

// 监听变更
watch(formData, () => { dirty.value = true }, { deep: true })

async function loadGroups() {
  if (!projectId.value) return
  groups.value = await apiGroupApi.list(projectId.value)
}

async function loadApi() {
  if (!isEdit.value) return
  const id = Number(route.params.id)
  const api: ApiDef = await apiApi.get(id)
  formData.id = api.id
  formData.name = api.name
  formData.code = api.code
  formData.group_id = api.group_id ?? null
  formData.method = api.method
  formData.path = api.path
  formData.description = api.description || ''
  formData.fields = (api.fields || []).map(f => ({ ...f }))
  // request_template 为 list 表示数组请求体（body 组装为 [{...}]）
  formData.is_array_body = Array.isArray(api.request_template)
  // watch(formData) 是异步触发的，会在下一个 tick 把 dirty 设为 true；
  // 这里用 nextTick 等待 watch 触发后再重置，避免误判"有未保存改动"
  await nextTick()
  dirty.value = false
}

function onBack() {
  router.push('/apis')
}

// ===== 未保存改动防丢失：路由离开 + 关闭/刷新标签页双层拦截 =====
// 与 CaseDesigner/EnvEdit 同法：编辑页是带 :id? 的临时页，守卫放行时统一关闭自身标签，
// 避免残留标签 + keep-alive 缓存让 dirty 状态的页面可反复点回
onBeforeRouteLeave(async () => {
  // removeTab 对已不存在的标签（点 X 关闭流已先移除）返回 null，无副作用，可安全重入
  const closeSelfTab = () => tabStore.removeTab(route.path)
  if (!dirty.value) {
    closeSelfTab()
    return true
  }
  try {
    await ElMessageBox.confirm(
      '有未保存的接口配置改动，离开后将丢失。确定离开？',
      '未保存提示',
      { type: 'warning', confirmButtonText: '放弃改动并离开', cancelButtonText: '留在本页' },
    )
    closeSelfTab()
    return true
  } catch {
    // 留在本页：标签原样保留
    return false
  }
})

const onBeforeUnload = (e: BeforeUnloadEvent) => {
  if (dirty.value) {
    e.preventDefault()
    e.returnValue = ''
  }
}

async function onSave() {
  // trim 关键字段，避免首尾空格
  formData.name = formData.name.trim()
  formData.code = formData.code.trim()
  formData.path = formData.path.trim()
  if (!formData.name || !formData.code || !formData.path) {
    ElMessage.warning('名称、编码、路径不能为空')
    return
  }
  saving.value = true
  try {
    const payload: Partial<ApiDef> = {
      project_id: projectId.value!,
      group_id: formData.group_id,
      name: formData.name,
      code: formData.code,
      method: formData.method,
      path: formData.path,
      description: formData.description,
      fields: formData.fields.filter(f => f.key),
      // 数组请求体用 [] 标记，build_request_body 据此组装为 [{...}]；
      // 普通请求体用 {} 标记
      request_template: formData.is_array_body ? [] : {},
    }
    if (isEdit.value) {
      await apiApi.update(formData.id!, payload)
      ElMessage.success('已保存')
    } else {
      await apiApi.create(payload)
      ElMessage.success('已创建')
      // 先复位 dirty 再导航：onBeforeRouteLeave 守卫会读它，避免依赖微任务时序
      dirty.value = false
      router.push('/apis')
      return
    }
    dirty.value = false
  } catch (e: any) {
    ElMessage.error(e.message || '保存失败')
  } finally {
    saving.value = false
  }
}

onMounted(async () => {
  // 编辑模式加载数据期间显示骨架屏，避免空白无反馈
  loading.value = isEdit.value
  try {
    await loadGroups()
    await loadApi()
  } finally {
    loading.value = false
  }
  window.addEventListener('keydown', onKeydown)
  window.addEventListener('beforeunload', onBeforeUnload)
})
onUnmounted(() => {
  window.removeEventListener('keydown', onKeydown)
  window.removeEventListener('beforeunload', onBeforeUnload)
})

function onKeydown(e: KeyboardEvent) {
  if ((e.ctrlKey || e.metaKey) && e.key === 's') {
    e.preventDefault()
    onSave()
  }
}
</script>

<style scoped>
.api-edit {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--app-bg);
}
.edit-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 20px;
  background: var(--app-card);
  backdrop-filter: saturate(180%) blur(20px);
  border-bottom: 1px solid var(--app-border);
}
.edit-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--app-text);
  flex: 1;
}
.header-right {
  display: flex;
  align-items: center;
  gap: 10px;
}
.dirty-tip {
  color: var(--app-warn-accent);
  font-size: 13px;
}
.edit-body {
  display: flex;
  gap: 16px;
  flex: 1;
  padding: 16px;
  overflow: auto;
}
.basic-panel {
  width: 360px;
  background: var(--app-card-solid);
  border-radius: var(--app-radius-lg);
  padding: 20px;
  box-shadow: var(--app-shadow-sm);
  height: fit-content;
}
.fields-panel {
  flex: 1;
  background: var(--app-card-solid);
  border-radius: var(--app-radius-lg);
  padding: 20px;
  box-shadow: var(--app-shadow-sm);
  min-width: 0;
}
.panel-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--app-text);
  margin-bottom: 16px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.panel-hint {
  font-size: 12px;
  font-weight: 400;
  color: var(--app-text-muted);
}
.debug-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}
.debug-meta {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.debug-tabs {
  margin-top: 8px;
}
.debug-section {
  margin-bottom: 12px;
}
.debug-section-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--app-text);
  margin-bottom: 6px;
}
.debug-json {
  background: var(--app-bg);
  border-radius: var(--app-radius-sm);
  padding: 12px;
  font-size: 12px;
  font-family: var(--app-font-mono);
  color: var(--app-text);
  max-height: 260px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-all;
  margin: 0;
}
.import-fields-body {
  max-height: 70vh;
  overflow-y: auto;
}
.locate-info {
  font-family: var(--app-font-mono);
  font-size: 13px;
  color: var(--app-primary);
  font-weight: 600;
}
.fields-compare {
  margin-top: 12px;
}
.compare-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 8px;
}
.compare-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--app-text);
}
.compare-stat {
  font-size: 12px;
  color: var(--app-text-muted);
}
.field-added {
  color: var(--app-success);
  font-weight: 600;
}
.field-removed {
  color: var(--app-danger);
  text-decoration: line-through;
  font-weight: 600;
}
</style>

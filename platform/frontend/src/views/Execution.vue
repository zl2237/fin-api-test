<template>
  <div class="page">
    <!-- 搜索过滤栏：左主筛选 / 右筛选+查询+操作（≥3 条件组合查询：显式查询按钮触发，规范 §3） -->
    <div class="page-head">
      <div class="head-left">
        <span class="page-title">执行记录</span>
        <el-select
          v-model="filterProjectId"
          style="width: 140px"
          placeholder="项目"
          clearable
          filterable
        >
          <el-option v-for="p in store.projects" :key="p.id" :label="p.name" :value="p.id" />
        </el-select>
      </div>
      <div class="head-right">
        <el-select
          v-model="filterExecutor"
          style="width: 140px"
          placeholder="执行人"
          clearable
          filterable
        >
          <el-option v-for="u in users" :key="u.id" :label="u.name" :value="u.id" />
        </el-select>
        <el-input
          v-model="filterCaseId"
          style="width: 140px"
          placeholder="用例ID"
          clearable
          @keyup.enter="onQuery"
          @clear="onQuery"
        />
        <el-select v-model="filterStatus" style="width: 140px" placeholder="状态" clearable>
          <el-option label="通过" value="success" />
          <el-option label="失败" value="failed" />
          <el-option label="执行中" value="running" />
        </el-select>
        <el-date-picker
          v-model="filterRange"
          type="datetimerange"
          range-separator="至"
          start-placeholder="开始时间"
          end-placeholder="结束时间"
          format="YYYY-MM-DD HH:mm"
          value-format="YYYY-MM-DD HH:mm:ss"
          style="width: 360px"
        />
        <el-button type="primary" @click="onQuery">查询</el-button>
        <el-button @click="resetFilter">重置</el-button>
        <span class="filter-count">
          共 {{ filteredList.length }} 条<template v-if="filteredList.length >= 200">（仅显示最近 200 条）</template>
        </span>
        <el-button v-if="store.user?.role === 'admin'" type="warning" plain @click="openCleanup">清理旧记录</el-button>
      </div>
    </div>

    <el-card shadow="never" class="card">
      <div v-if="loadError" class="app-load-error">
        <el-icon><WarningFilled /></el-icon>
        <span>{{ loadError }}</span>
        <el-button size="small" @click="load">重试</el-button>
      </div>
      <el-skeleton v-else-if="loading" :rows="6" animated class="skeleton-wrap" />
      <el-table v-else :data="pagedList" stripe size="small" row-key="id">
        <template #empty>
          <EmptyState description="暂无执行记录" :image-size="80">
            <el-button type="primary" @click="router.push('/cases')">前往用例管理执行用例</el-button>
          </EmptyState>
        </template>
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column label="项目" min-width="120" show-overflow-tooltip>
          <template #default="{ row }">{{ row.project_name || `#${row.project_id}` || '—' }}</template>
        </el-table-column>
        <el-table-column label="用例" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">{{ row.case_name || `#${row.case_id}` }}</template>
        </el-table-column>
        <el-table-column label="环境" min-width="120" show-overflow-tooltip>
          <template #default="{ row }">{{ row.env_name || `#${row.env_id}` }}</template>
        </el-table-column>
        <el-table-column label="状态" width="110">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)" effect="light">
              <el-icon v-if="row.status === 'running'" class="is-loading"><Loading /></el-icon>
              {{ statusText(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="来源" width="90" align="center">
          <template #default="{ row }">
            <el-tooltip v-if="row.trigger_type === 'schedule'" content="定时任务触发" placement="top">
              <el-tag type="warning" effect="plain" size="small"><el-icon><Timer /></el-icon>定时</el-tag>
            </el-tooltip>
            <span v-else class="trigger-manual">手动</span>
          </template>
        </el-table-column>
        <el-table-column label="数据行" width="130">
          <template #default="{ row }">
            <el-tooltip
              v-if="row.dataset_row"
              placement="top"
              popper-class="ds-row-popper"
            >
              <template #content>
                <div class="ds-row-detail">
                  <template v-if="dsRowItems(row.dataset_row.data).length">
                    <div
                      v-for="[k, v] in dsRowItems(row.dataset_row.data)"
                      :key="k"
                      class="ds-row-item"
                    >
                      <span class="ds-row-key">{{ k }}</span>
                      <span class="ds-row-val">{{ formatDsVal(v) }}</span>
                    </div>
                  </template>
                  <div v-else class="ds-row-empty">该行所有字段均为空</div>
                </div>
              </template>
              <!-- el-tooltip 默认插槽只渲染单个触发元素：tag+行号需包一层，否则 ds-row-label 被丢弃 -->
              <span class="ds-row-wrap">
                <el-tag type="info" effect="plain" size="small">数据驱动</el-tag>
                <span class="ds-row-label">#{{ row.dataset_row.row_index }} {{ row.dataset_row.label }}</span>
              </span>
            </el-tooltip>
            <span v-else class="ds-row-none">—</span>
          </template>
        </el-table-column>
        <el-table-column label="通过/总数" width="120">
          <template #default="{ row }">
            {{ row.summary?.passed ?? 0 }} / {{ row.summary?.total ?? 0 }}
          </template>
        </el-table-column>
        <el-table-column label="开始时间" width="120">
          <template #default="{ row }">
            <el-tooltip :content="formatTime(row.started_at)" placement="top" popper-class="app-tip">
              <span>{{ formatRelativeTime(row.started_at) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="结束时间" width="120">
          <template #default="{ row }">
            <el-tooltip :content="formatTime(row.ended_at)" placement="top" popper-class="app-tip">
              <span>{{ formatRelativeTime(row.ended_at) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="执行人" width="100" align="center">
          <template #default="{ row }">{{ row.created_by_name || '未知' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="120" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="router.push(`/reports/${row.id}`)">查看报告</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="pagination-wrap">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :total="filteredList.length"
          :page-sizes="[10, 20, 50, 100]"
          layout="total, sizes, prev, pager, next"
          small
          background
        />
      </div>
    </el-card>

    <!-- 清理旧记录对话框 -->
    <el-dialog v-model="cleanupVisible" title="清理旧执行记录" width="420px" align-center :close-on-click-modal="false">
      <el-alert type="warning" :closable="false" show-icon style="margin-bottom: 16px">
        将永久删除指定天数前的执行记录（含步骤和断言），此操作不可恢复。
      </el-alert>
      <el-form label-width="100px">
        <el-form-item label="保留天数">
          <el-input-number v-model="cleanupDays" :min="1" :max="365" />
          <span style="margin-left: 8px; color: var(--app-text-muted); font-size: 12px">天前的记录将被删除</span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="cleanupVisible = false">取消</el-button>
        <el-button type="danger" :loading="cleanupLoading" @click="onCleanup">确认清理</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Loading, WarningFilled, Timer } from '@element-plus/icons-vue'
import { execApi, userApi, type ExecutionRecord, type SimpleUser } from '@/api'
import { useAppStore } from '@/stores'
import { storeToRefs } from 'pinia'
import { formatTime, formatRelativeTime, execStatusType as statusType, execStatusText as statusText } from '@/utils/format'
import { useExecutionRunner } from '@/composables/useExecutionRunner'
import EmptyState from '@/components/EmptyState.vue'

const route = useRoute()
const router = useRouter()
const store = useAppStore()
const { currentProjectId } = storeToRefs(store)
const list = ref<ExecutionRecord[]>([])
const loading = ref(false)
const loadError = ref('')
const users = ref<SimpleUser[]>([])

// 清理旧记录
const cleanupVisible = ref(false)
const cleanupDays = ref(30)
const cleanupLoading = ref(false)
const page = ref(1)
const pageSize = ref(10)

// 过滤条件输入（草稿）：项目/执行人/用例ID 走后端，状态/时间范围本地兜底
// 项目默认锁定当前项目，实现与环境/接口/用例一致的数据隔离
const filterProjectId = ref<number | null>(currentProjectId.value)
const filterExecutor = ref<number | null>(null)
const filterCaseId = ref('')
const filterStatus = ref('')
const filterRange = ref<[string, string] | null>(null)

// 生效条件快照：仅「查询/重置」点击时固化，load/轮询/本地过滤统一读取
// 避免「改了输入没点查询，列表却悄悄变化」的所见非所查问题
const applied = reactive({
  projectId: currentProjectId.value as number | null,
  executor: null as number | null,
  caseId: '',
  status: '',
  range: null as [string, string] | null,
})

const filteredList = computed(() => {
  let r = list.value
  if (applied.status) {
    r = r.filter(e => e.status === applied.status)
  }
  if (applied.range && applied.range.length === 2) {
    const [start, end] = applied.range
    r = r.filter(e => {
      const t = e.started_at ?? ''
      return t >= start && t <= end.replace('00:00:00', '23:59:59')
    })
  }
  return r
})

const pagedList = computed(() => {
  const start = (page.value - 1) * pageSize.value
  return filteredList.value.slice(start, start + pageSize.value)
})

// 显式查询：输入区条件快照到 applied 后统一生效（回第 1 页）
function onQuery() {
  applied.projectId = filterProjectId.value
  applied.executor = filterExecutor.value
  applied.caseId = filterCaseId.value.trim()
  applied.status = filterStatus.value
  applied.range = filterRange.value
  page.value = 1
  syncQueryToUrl()
  load()
}

// 筛选状态同步 URL（GitHub 惯例）：刷新不丢条件、可直接分享「失败记录」链接
function syncQueryToUrl() {
  const q: Record<string, string> = {}
  if (applied.projectId) q.project_id = String(applied.projectId)
  if (applied.executor) q.executor = String(applied.executor)
  if (applied.caseId) q.case_id = applied.caseId
  if (applied.status) q.status = applied.status
  if (applied.range && applied.range.length === 2) {
    q.start = applied.range[0]
    q.end = applied.range[1]
  }
  router.replace({ query: q })
}

// 从 URL 恢复筛选（草稿回填后走统一 onQuery 生效）
function restoreFromQuery() {
  const q = route.query
  if (q.project_id) {
    const n = Number(q.project_id)
    if (!Number.isNaN(n)) filterProjectId.value = n
  }
  if (q.executor) {
    const n = Number(q.executor)
    if (!Number.isNaN(n)) filterExecutor.value = n
  }
  if (q.case_id) filterCaseId.value = String(q.case_id)
  if (q.status) filterStatus.value = String(q.status)
  if (q.start && q.end) filterRange.value = [String(q.start), String(q.end)]
}

function resetFilter() {
  filterProjectId.value = null
  filterExecutor.value = null
  filterCaseId.value = ''
  filterStatus.value = ''
  filterRange.value = null
  onQuery()
}

// 状态映射统一走 utils/format（execStatusType/execStatusText 的本地别名见顶部 import）

// 数据行快照 tooltip：只展示已配置字段（数据集动辄上百列，空单元格无展示意义）
function dsRowItems(data: Record<string, any>): [string, any][] {
  return Object.entries(data || {}).filter(([, v]) => v !== null && v !== undefined && v !== '')
}
// 对象/数组序列化为紧凑 JSON，避免 [object Object]
function formatDsVal(v: any): string {
  if (typeof v === 'object') return JSON.stringify(v)
  return String(v)
}

// 自动刷新：列表存在 running 记录时轮询，全部结束/刷新失败即停（间隔与详情页一致）
const runner = useExecutionRunner()
let stopRefresh: (() => void) | null = null

// 生效条件快照 → 列表查询参数（load 与自动刷新共用，保证两处口径一致）
function execListParams(): { case_id?: number; project_id?: number; created_by?: number; limit?: number } | null {
  // 项目隔离：优先用生效条件中的项目，未选则回退到当前项目
  const projectId = applied.projectId ?? currentProjectId.value
  if (!projectId) return null
  const caseId = applied.caseId ? Number(applied.caseId) : undefined
  const params: { case_id?: number; project_id?: number; created_by?: number; limit?: number } = { limit: 200, project_id: projectId }
  if (caseId && !Number.isNaN(caseId)) params.case_id = caseId
  if (applied.executor) params.created_by = applied.executor
  return params
}

function startAutoRefresh() {
  if (stopRefresh) return
  stopRefresh = runner.refreshWhileRunning(async () => {
    const params = execListParams()
    if (!params) return true // 无项目上下文：跳过本轮，继续观察
    list.value = await execApi.list(params)
    // 没有 running 记录了，停止轮询
    return list.value.some(e => e.status === 'running')
  }, { interval: 3000 })
}

function stopAutoRefresh() {
  stopRefresh?.()
  stopRefresh = null
}

async function load() {
  const params = execListParams()
  if (!params) {
    list.value = []
    return
  }
  loading.value = true
  loadError.value = ''
  try {
    list.value = await execApi.list(params)
    // 存在执行中的记录则启动轮询，否则确保停止
    if (list.value.some(e => e.status === 'running')) {
      startAutoRefresh()
    } else {
      stopAutoRefresh()
    }
  } catch (e: any) {
    // 页面级失败：内联错误块 + 重试，不用 toast 一闪而过
    loadError.value = e?.message || '加载失败'
  } finally {
    loading.value = false
  }
}

async function loadUsers() {
  try {
    users.value = await userApi.simple()
  } catch {
    users.value = []
  }
}

function openCleanup() {
  cleanupDays.value = 30
  cleanupVisible.value = true
}

async function onCleanup() {
  try {
    await ElMessageBox.confirm(
      `确认删除 ${cleanupDays.value} 天前的所有执行记录？此操作不可恢复`,
      '提示',
      { type: 'warning' },
    )
  } catch {
    return // 用户取消
  }
  cleanupLoading.value = true
  try {
    const res = await execApi.cleanup(cleanupDays.value)
    ElMessage.success(res.message || `已清理 ${res.deleted} 条记录`)
    cleanupVisible.value = false
    await load()
  } catch (e: any) {
    ElMessage.error(e.message || '清理失败')
  } finally {
    cleanupLoading.value = false
  }
}

onMounted(() => {
  // URL 携带筛选条件时回填（含报告页跳转 ?case_id=xx）：条件可见可改，且刷新不丢
  restoreFromQuery()
  onQuery()
  loadUsers()
})

// 切换项目（顶栏全局上下文）时：同步草稿与生效条件并重新加载，实现项目级数据隔离
watch(currentProjectId, (newId) => {
  if (newId) {
    filterProjectId.value = newId
    applied.projectId = newId
    page.value = 1
    syncQueryToUrl()
    load()
  }
})

onUnmounted(() => {
  stopAutoRefresh()
})
</script>

<style scoped>
.page {
  display: flex;
  flex-direction: column;
  height: 100%;
  gap: 12px;
}
.card {
  flex: 1;
  min-height: 0;
  overflow: auto;
  background: var(--app-card);
}
/* 顶部工具栏统一走全局 .page-head 基准（style.css），此处仅保留本页布局所需的修正 */
.page-head {
  flex-shrink: 0;
}
.filter-count {
  margin-left: auto;
  font-size: 12px;
  color: var(--app-text-muted);
}
.pagination-wrap {
  display: flex;
  justify-content: flex-end;
  margin-top: 12px;
}
/* 来源列：手动为常态弱文本，定时用 warning tag 区分（见模板） */
.trigger-manual {
  font-size: 12px;
  color: var(--app-text-muted);
}
/* 数据行列：行号 + 首列值（hover 显示整行数据快照） */
.ds-row-wrap {
  display: inline-flex;
  align-items: center;
}
.ds-row-label {
  margin-left: 6px;
  font-size: 12px;
  color: var(--app-text-muted);
}
.ds-row-none {
  color: var(--app-text-muted);
}
</style>

<style>
/* 数据行 tooltip（popper 挂 body，不能 scoped）：限宽限高 + 内部滚动，长值截断 */
.ds-row-popper.el-popper {
  max-width: 420px;
}
.ds-row-popper .ds-row-detail {
  max-height: 280px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.ds-row-popper .ds-row-item {
  display: flex;
  align-items: baseline;
  gap: 8px;
  font-size: 12px;
  line-height: 1.6;
}
.ds-row-popper .ds-row-key {
  flex-shrink: 0;
  max-width: 160px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: #c0c4cc;
}
.ds-row-popper .ds-row-val {
  color: inherit;
  word-break: break-all;
  /* 超长值（如整对象列的 JSON）最多 3 行，超出截断 */
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.ds-row-popper .ds-row-empty {
  font-size: 12px;
  color: #c0c4cc;
}
</style>

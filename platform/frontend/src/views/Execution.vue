<template>
  <div class="page">
    <!-- 搜索过滤栏 -->
    <div class="filter-bar">
        <el-select
          v-model="filterProjectId"
          style="width: 180px"
          placeholder="项目"
          clearable
          filterable
          @change="onFilterChange"
        >
          <el-option v-for="p in store.projects" :key="p.id" :label="p.name" :value="p.id" />
        </el-select>
        <el-select
          v-model="filterExecutor"
          style="width: 140px"
          placeholder="执行人"
          clearable
          filterable
          @change="onFilterChange"
        >
          <el-option v-for="u in users" :key="u.id" :label="u.name" :value="u.id" />
        </el-select>
        <el-input
          v-model="filterCaseId"
          style="width: 140px"
          placeholder="用例ID"
          clearable
          @keyup.enter="onFilterChange"
          @clear="onFilterChange"
        />
        <el-select v-model="filterStatus" style="width: 140px" placeholder="状态" clearable @change="onFilterChange">
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
          @change="onFilterChange"
        />
        <el-button @click="resetFilter">重置</el-button>
        <span class="filter-count">共 {{ filteredList.length }} 条</span>
        <el-button v-if="store.user?.role === 'admin'" type="warning" plain @click="openCleanup">清理旧记录</el-button>
    </div>

    <el-card shadow="never" class="card">
      <el-skeleton v-if="loading" :rows="6" animated class="skeleton-wrap" />
      <el-table v-else :data="pagedList" stripe empty-text="暂无执行记录，前往用例列表执行用例">
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
        <el-table-column label="通过/总数" width="120">
          <template #default="{ row }">
            {{ row.summary?.passed ?? 0 }} / {{ row.summary?.total ?? 0 }}
          </template>
        </el-table-column>
        <el-table-column prop="started_at" label="开始时间" min-width="170" show-overflow-tooltip />
        <el-table-column prop="ended_at" label="结束时间" min-width="170" show-overflow-tooltip />
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
          background
          small
        />
      </div>
    </el-card>

    <!-- 清理旧记录对话框 -->
    <el-dialog v-model="cleanupVisible" title="清理旧执行记录" width="420px" align-center>
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
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Loading } from '@element-plus/icons-vue'
import { execApi, userApi, type ExecutionRecord, type SimpleUser } from '@/api'
import { useAppStore } from '@/stores'
import { storeToRefs } from 'pinia'

const route = useRoute()
const router = useRouter()
const store = useAppStore()
const { currentProjectId } = storeToRefs(store)
const list = ref<ExecutionRecord[]>([])
const loading = ref(false)
const users = ref<SimpleUser[]>([])

// 清理旧记录
const cleanupVisible = ref(false)
const cleanupDays = ref(30)
const cleanupLoading = ref(false)
const page = ref(1)
const pageSize = ref(10)

// 过滤条件：项目/执行人/用例ID 走后端，状态/时间范围本地兜底
// 项目默认锁定当前项目，实现与环境/接口/用例一致的数据隔离
const filterProjectId = ref<number | null>(currentProjectId.value)
const filterExecutor = ref<number | null>(null)
const filterCaseId = ref('')
const filterStatus = ref('')
const filterRange = ref<[string, string] | null>(null)

const filteredList = computed(() => {
  let r = list.value
  if (filterStatus.value) {
    r = r.filter(e => e.status === filterStatus.value)
  }
  if (filterRange.value && filterRange.value.length === 2) {
    const [start, end] = filterRange.value
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

function resetFilter() {
  filterProjectId.value = null
  filterExecutor.value = null
  filterCaseId.value = ''
  filterStatus.value = ''
  filterRange.value = null
  page.value = 1
  load()
}

function onFilterChange() {
  page.value = 1
  load()
}

function statusType(s: string) {
  return s === 'success' ? 'success' : s === 'running' ? 'warning' : 'danger'
}
function statusText(s: string) {
  return s === 'success' ? '通过' : s === 'running' ? '执行中' : '失败'
}

// 自动刷新：列表存在 running 记录时轮询，全部结束后停止
let refreshTimer: ReturnType<typeof setInterval> | null = null
const REFRESH_INTERVAL = 3000

function startAutoRefresh() {
  if (refreshTimer) return
  refreshTimer = setInterval(async () => {
    try {
      const projectId = filterProjectId.value ?? currentProjectId.value
      if (!projectId) return
      const caseId = route.query.case_id ? Number(route.query.case_id) : (filterCaseId.value.trim() ? Number(filterCaseId.value) : undefined)
      const params: { case_id?: number; project_id?: number; created_by?: number; limit?: number } = { limit: 200, project_id: projectId }
      if (caseId && !Number.isNaN(caseId)) params.case_id = caseId
      if (filterExecutor.value) params.created_by = filterExecutor.value
      list.value = await execApi.list(params)
      // 没有 running 记录了，停止轮询
      if (!list.value.some(e => e.status === 'running')) {
        stopAutoRefresh()
      }
    } catch {
      stopAutoRefresh()
    }
  }, REFRESH_INTERVAL)
}

function stopAutoRefresh() {
  if (refreshTimer) {
    clearInterval(refreshTimer)
    refreshTimer = null
  }
}

async function load() {
  // 项目隔离：优先用筛选框选中的项目，未选则回退到当前项目
  const projectId = filterProjectId.value ?? currentProjectId.value
  if (!projectId) {
    list.value = []
    return
  }
  loading.value = true
  try {
    // 后端过滤：case_id（URL 或输入框）、project_id、created_by（执行人）
    const caseId = route.query.case_id ? Number(route.query.case_id) : (filterCaseId.value.trim() ? Number(filterCaseId.value) : undefined)
    const params: { case_id?: number; project_id?: number; created_by?: number; limit?: number } = { limit: 200, project_id: projectId }
    if (caseId && !Number.isNaN(caseId)) params.case_id = caseId
    if (filterExecutor.value) params.created_by = filterExecutor.value
    list.value = await execApi.list(params)
    // 存在执行中的记录则启动轮询，否则确保停止
    if (list.value.some(e => e.status === 'running')) {
      startAutoRefresh()
    } else {
      stopAutoRefresh()
    }
  } catch (e: any) {
    ElMessage.error(e.message)
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
      `确认删除 ${cleanupDays.value} 天前的所有执行记录？此操作不可恢复。`,
      '清理确认',
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
  load()
  loadUsers()
})

// 切换项目时：同步筛选框并重新加载，实现项目级数据隔离
watch(currentProjectId, (newId) => {
  if (newId) {
    filterProjectId.value = newId
    page.value = 1
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
  backdrop-filter: saturate(180%) blur(20px);
}
.filter-bar {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 16px;
  flex-wrap: wrap;
  background: var(--app-card);
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius-lg);
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
</style>

<template>
  <div class="log-manage">
    <div class="page-head">
      <div class="head-left">
        <span class="page-title">操作日志</span>
      </div>
      <div class="head-right">
        <el-select v-model="filterUserId" placeholder="操作人" clearable filterable style="width: 140px" @change="load">
          <el-option v-for="u in users" :key="u.id" :label="u.name" :value="u.id" />
        </el-select>
        <el-select v-model="filterAction" placeholder="操作类型" clearable style="width: 140px" @change="load">
          <el-option label="新增" value="create" />
          <el-option label="修改" value="update" />
          <el-option label="删除" value="delete" />
          <el-option label="复制" value="copy" />
        </el-select>
        <el-select v-model="filterTarget" placeholder="目标类型" clearable style="width: 140px" @change="load">
          <el-option label="项目" value="project" />
          <el-option label="环境" value="environment" />
          <el-option label="接口" value="api" />
          <el-option label="用例" value="testcase" />
          <el-option label="用户" value="user" />
          <el-option label="接口分组" value="api_group" />
          <el-option label="用例分组" value="case_group" />
          <el-option label="数据集" value="dataset" />
        </el-select>
        <el-date-picker
          v-model="filterRange"
          type="datetimerange"
          range-separator="至"
          start-placeholder="开始时间"
          end-placeholder="结束时间"
          format="YYYY-MM-DD HH:mm"
          value-format="YYYY-MM-DD HH:mm:ss"
          style="width: 340px"
          @change="load"
        />
        <el-button @click="resetFilter">重置</el-button>
        <el-button @click="load">刷新</el-button>
        <el-button type="warning" plain @click="openCleanup">清理旧日志</el-button>
      </div>
    </div>

    <el-card shadow="never" class="table-card">
      <div v-if="loadError" class="app-load-error">
        <el-icon><WarningFilled /></el-icon>
        <span>{{ loadError }}</span>
        <el-button size="small" @click="load">重试</el-button>
      </div>
      <el-skeleton v-else-if="loading" :rows="6" animated class="skeleton-wrap" />
      <el-table v-else :data="pagedList" stripe size="small" row-key="id" @sort-change="onSortChange">
        <template #empty>
          <EmptyState description="暂无操作记录" :image-size="80" />
        </template>
        <el-table-column prop="id" label="ID" width="70" align="center" sortable="custom" />
        <el-table-column label="操作人" width="120">
          <template #default="{ row }">{{ row.username || '未知' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="90" align="center">
          <template #default="{ row }">
            <el-tag :type="actionTagType(row.action)" effect="light" size="small">
              {{ actionText(row.action) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="目标类型" width="110">
          <template #default="{ row }">{{ targetTypeText(row.target_type) }}</template>
        </el-table-column>
        <el-table-column prop="target_id" label="目标ID" width="80" align="center" />
        <el-table-column prop="target_name" label="目标名称" min-width="160" show-overflow-tooltip />
        <el-table-column label="详情" min-width="160">
          <template #default="{ row }">
            <span v-if="row.detail" class="cell-expand" title="点击查看完整详情" @click="openDetail(row)">{{ row.detail }}</span>
            <span v-else class="detail-empty">—</span>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="操作时间" width="120" sortable="custom">
          <template #default="{ row }">
            <el-tooltip :content="formatTime(row.created_at)" placement="top" popper-class="app-tip">
              <span>{{ formatRelativeTime(row.created_at) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
      </el-table>
      <div class="table-tip">仅显示最近 500 条</div>
      <div class="pagination-wrap">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :total="logs.length"
          :page-sizes="[10, 20, 50, 100]"
          layout="total, sizes, prev, pager, next"
          small
          background
        />
      </div>
    </el-card>

    <!-- 操作详情对话框：完整文本 + 复制（表格内单行截断，长变更列表看不全） -->
    <el-dialog v-model="detailVisible" title="操作详情" width="560px" align-center>
      <div v-if="detailRow" class="detail-meta">
        <el-tag :type="actionTagType(detailRow.action)" effect="light" size="small">{{ actionText(detailRow.action) }}</el-tag>
        <span>{{ detailRow.username || '未知' }}</span>
        <span class="detail-time">{{ formatTime(detailRow.created_at) }}</span>
      </div>
      <pre class="detail-text">{{ detailRow?.detail }}</pre>
      <template #footer>
        <el-button @click="copyDetail">复制</el-button>
        <el-button type="primary" @click="detailVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <!-- 清理旧日志对话框 -->
    <el-dialog v-model="cleanupVisible" title="清理旧操作日志" width="420px" align-center :close-on-click-modal="false">
      <el-alert type="warning" :closable="false" show-icon style="margin-bottom: 16px">
        将永久删除指定天数前的操作日志，此操作不可恢复。
      </el-alert>
      <el-form label-width="100px">
        <el-form-item label="保留天数">
          <el-input-number v-model="cleanupDays" :min="1" :max="365" />
          <span style="margin-left: 8px; color: var(--app-text-muted); font-size: 12px">天前的日志将被删除</span>
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
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { WarningFilled } from '@element-plus/icons-vue'
import { logApi, userApi, type OperationLog, type SimpleUser } from '@/api'
import { formatTime, formatRelativeTime } from '@/utils/format'
import { useClientSort } from '@/composables/useClientSort'
import EmptyState from '@/components/EmptyState.vue'

const logs = ref<OperationLog[]>([])
const loading = ref(false)
const loadError = ref('')
const users = ref<SimpleUser[]>([])
const filterAction = ref('')
const filterTarget = ref('')
const filterUserId = ref<number | null>(null)
const filterRange = ref<[string, string] | null>(null)
const page = ref(1)
const pageSize = ref(10)
// 表头排序（sortable="custom"）：先排全量再分页切片，避免只排当前页的假象
const { onSortChange, sorted: sortedLogs } = useClientSort(logs, {
  id: l => l.id,
  created_at: l => l.created_at ?? '',
}, () => { page.value = 1 })
const pagedList = computed(() => {
  const start = (page.value - 1) * pageSize.value
  return sortedLogs.value.slice(start, start + pageSize.value)
})

// 详情对话框
const detailVisible = ref(false)
const detailRow = ref<OperationLog | null>(null)
function openDetail(row: OperationLog) {
  detailRow.value = row
  detailVisible.value = true
}
async function copyDetail() {
  if (!detailRow.value?.detail) return
  try {
    await navigator.clipboard.writeText(detailRow.value.detail)
    ElMessage.success('已复制')
  } catch {
    ElMessage.error('复制失败')
  }
}

async function load() {
  loading.value = true
  loadError.value = ''
  try {
    const params: { action?: string; target_type?: string; user_id?: number; limit?: number; start_time?: string; end_time?: string } = { limit: 500 }
    if (filterAction.value) params.action = filterAction.value
    if (filterTarget.value) params.target_type = filterTarget.value
    if (filterUserId.value) params.user_id = filterUserId.value
    if (filterRange.value && filterRange.value.length === 2) {
      params.start_time = filterRange.value[0]
      // 日期端点（00:00:00）补到当天末尾，保持闭区间口径
      params.end_time = filterRange.value[1].replace('00:00:00', '23:59:59')
    }
    logs.value = await logApi.list(params)
    page.value = 1
  } catch (e: any) {
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

function resetFilter() {
  filterAction.value = ''
  filterTarget.value = ''
  filterUserId.value = null
  filterRange.value = null
  load()
}

function actionText(a: string) {
  return a === 'create' ? '新增' : a === 'update' ? '修改' : a === 'delete' ? '删除' : a === 'copy' ? '复制' : a
}

function actionTagType(a: string) {
  return a === 'create' ? 'success' : a === 'update' ? 'warning' : a === 'delete' ? 'danger' : 'info'
}

function targetTypeText(t: string) {
  const map: Record<string, string> = {
    project: '项目',
    environment: '环境',
    api: '接口',
    testcase: '用例',
    user: '用户',
    api_group: '接口分组',
    case_group: '用例分组',
    dataset: '数据集',
  }
  return map[t] || t
}

// 清理旧日志
const cleanupVisible = ref(false)
const cleanupDays = ref(30)
const cleanupLoading = ref(false)

function openCleanup() {
  cleanupDays.value = 30
  cleanupVisible.value = true
}

async function onCleanup() {
  try {
    await ElMessageBox.confirm(
      `确认删除 ${cleanupDays.value} 天前的所有操作日志？此操作不可恢复`,
      '清理旧操作日志',
      { type: 'warning', confirmButtonText: '确认清理' },
    )
  } catch {
    return // 用户取消
  }
  cleanupLoading.value = true
  try {
    const res = await logApi.cleanup(cleanupDays.value)
    ElMessage.success(res.message || `已清理 ${res.deleted} 条日志`)
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
</script>

<style scoped>
.log-manage {
  display: flex;
  flex-direction: column;
  gap: 12px;
  height: 100%;
}
.detail-empty {
  color: var(--app-text-muted);
}
/* 详情单元格可点击查看完整内容（与报告页断言值展开一致） */
.cell-expand {
  cursor: pointer;
  border-bottom: 1px dashed var(--app-border);
}
.cell-expand:hover {
  color: var(--el-color-primary);
}
.detail-meta {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 13px;
  margin-bottom: 12px;
}
.detail-time {
  color: var(--app-text-muted);
  font-size: 12px;
}
.detail-text {
  margin: 0;
  padding: 12px;
  max-height: 320px;
  overflow: auto;
  font-size: 13px;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-all;
  background: var(--el-fill-color-light);
  border-radius: 8px;
}
.table-tip {
  margin-top: 8px;
  font-size: 12px;
  color: var(--app-text-muted);
}
.table-card {
  background: var(--app-card);
  border-radius: var(--app-radius-lg);
}
.pagination-wrap {
  display: flex;
  justify-content: flex-end;
  margin-top: 12px;
}
</style>

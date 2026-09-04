<template>
  <div class="page">
    <!-- 顶栏：返回 + 标题 + 状态 -->
    <div class="page-head">
      <div class="head-left">
        <el-button @click="router.back()">
          <el-icon><ArrowLeft /></el-icon>返回
        </el-button>
        <span class="page-title">套件报告</span>
        <template v-if="record">
          <span class="case-name">{{ record.case_name || `#${record.case_id}` }}</span>
          <el-tag type="warning" effect="plain">套件</el-tag>
          <el-tag :type="statusType(record.status)" effect="light">
            <el-icon v-if="record.status === 'running'" class="is-loading"><Loading /></el-icon>
            {{ statusText(record.status) }}
          </el-tag>
        </template>
      </div>
      <div class="head-right">
        <el-button @click="router.push({ path: '/executions', query: { case_id: record?.case_id } })">执行记录</el-button>
      </div>
    </div>

    <div v-loading="loading" class="report-body">
      <div v-if="loadError" class="app-load-error">
        <el-icon><WarningFilled /></el-icon>
        <span>{{ loadError }}</span>
        <el-button size="small" @click="load">重试</el-button>
      </div>

      <template v-else-if="record">
        <!-- 套件级摘要：计数 + 基本信息 + 共享变量终值 -->
        <el-card shadow="never" class="sum-card">
          <div class="sum-row">
            <div class="sum-item">
              <span class="sum-label">成员总数</span>
              <span class="sum-val">{{ summary.total ?? '—' }}</span>
            </div>
            <div class="sum-item ok">
              <span class="sum-label">通过</span>
              <span class="sum-val">{{ summary.passed ?? '—' }}</span>
            </div>
            <div class="sum-item bad">
              <span class="sum-label">失败</span>
              <span class="sum-val">{{ summary.failed ?? '—' }}</span>
            </div>
            <div class="sum-item warn">
              <span class="sum-label">阻断</span>
              <span class="sum-val">{{ summary.blocked ?? '—' }}</span>
            </div>
            <div class="sum-item">
              <span class="sum-label">环境</span>
              <span class="sum-val txt">{{ record.env_name || `#${record.env_id}` }}</span>
            </div>
            <div class="sum-item">
              <span class="sum-label">执行人</span>
              <span class="sum-val txt">{{ record.created_by_name || '—' }}</span>
            </div>
            <div class="sum-item">
              <span class="sum-label">开始</span>
              <span class="sum-val txt">{{ formatTime(record.started_at) }}</span>
            </div>
            <div class="sum-item">
              <span class="sum-label">结束</span>
              <span class="sum-val txt">{{ formatTime(record.ended_at) }}</span>
            </div>
          </div>
          <!-- 共享变量终值（白名单快照的最后有效值） -->
          <div v-if="sharedEntries.length" class="shared-box">
            <span class="shared-label">共享变量终值</span>
            <div class="shared-vars">
              <el-tag v-for="[k, v] in sharedEntries" :key="k" class="shared-tag">
                {{ k }} = {{ shortVal(v) }}
              </el-tag>
            </div>
          </div>
        </el-card>

        <!-- 成员明细：按执行顺序，逐成员卡片（含数据驱动行展开） -->
        <el-card v-for="(m, i) in memberReports" :key="i" shadow="never" class="member-card">
          <template #header>
            <div class="card-head">
              <div class="head-title">
                <span class="member-order">{{ i + 1 }}</span>
                <span class="member-name">{{ m.case_name || `用例#${m.case_id}` }}</span>
                <el-tag size="small" :type="statusType(m.status)">{{ statusText(m.status) }}</el-tag>
              </div>
              <el-tag v-if="(m.rows?.length ?? 0) > 1" size="small" type="info" effect="plain">数据驱动 {{ m.rows?.length }} 行</el-tag>
            </div>
          </template>
          <div v-if="m.error" class="member-error">
            <el-icon><WarningFilled /></el-icon>{{ m.error }}
          </div>
          <el-table v-if="m.rows?.length" :data="m.rows" size="small" stripe>
            <el-table-column label="数据行" width="100">
              <template #default="{ row }">
                {{ row.row_index != null ? `#${row.row_index}` : '—' }}
              </template>
            </el-table-column>
            <el-table-column label="状态" width="100">
              <template #default="{ row }">
                <el-tag size="small" :type="statusType(row.status)">{{ statusText(row.status) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="说明">
              <template #default="{ row }">{{ row.reason || (row.status === 'success' ? '执行通过' : '') }}</template>
            </el-table-column>
            <el-table-column label="执行报告" width="120" align="center">
              <template #default="{ row }">
                <el-button
                  v-if="row.execution_id"
                  link
                  type="primary"
                  size="small"
                  @click="router.push(`/reports/${row.execution_id}`)"
                >查看报告</el-button>
                <span v-else class="no-report">—</span>
              </template>
            </el-table-column>
          </el-table>
          <!-- 无 rows 的兜底（成员未展开行，如未配置数据集且执行异常的理论态） -->
          <div v-else class="no-rows">该成员无行执行记录</div>
        </el-card>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft, Loading, WarningFilled } from '@element-plus/icons-vue'
import { execApi, type ExecutionRecord } from '@/api'
import { formatTime, execStatusType as statusType, execStatusText as statusText } from '@/utils/format'
import { useExecutionRunner } from '@/composables/useExecutionRunner'

interface MemberReport {
  sort_order?: number
  case_id?: number
  case_name?: string
  status?: string
  error?: string
  rows?: { row_index?: number | null; execution_id?: number; status?: string; reason?: string }[]
}

const route = useRoute()
const router = useRouter()
const runner = useExecutionRunner()

const record = ref<ExecutionRecord | null>(null)
const loading = ref(false)
const loadError = ref('')

const summary = computed<Record<string, any>>(() => record.value?.summary || {})
const memberReports = computed<MemberReport[]>(() => summary.value.members || [])
const sharedEntries = computed<[string, any][]>(() =>
  Object.entries(summary.value.shared_vars || {}).filter(([, v]) => v !== null && v !== undefined))

function shortVal(v: any): string {
  const s = typeof v === 'object' ? JSON.stringify(v) : String(v)
  return s.length > 60 ? `${s.slice(0, 60)}...` : s
}

/** running 态自动轮询直到出结果；终态即停 */
let stopRefresh: (() => void) | null = null
function schedulePollIfRunning() {
  stopRefresh?.()
  if (record.value?.status !== 'running') return
  stopRefresh = runner.refreshWhileRunning(async () => {
    await load(true)
    return false // load 完成后由 schedulePollIfRunning 决定续排与否
  }, { interval: 3000 })
}

async function load(silent = false) {
  const id = Number(route.params.id)
  if (!id) return
  if (!silent) {
    loading.value = true
    loadError.value = ''
  }
  try {
    record.value = await execApi.report(id)
    // 非套件主记录（如直达普通报告链接）→ 转普通报告页，避免空白
    if (!record.value?.summary?.suite) {
      router.replace(`/reports/${id}`)
      return
    }
    schedulePollIfRunning()
  } catch (e: any) {
    if (!silent) loadError.value = e?.message || '加载失败'
  } finally {
    if (!silent) loading.value = false
  }
}

onMounted(load)
onUnmounted(() => stopRefresh?.())
</script>

<style scoped>
.page {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--app-bg);
}
.report-body {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 12px 20px 20px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.case-name {
  font-size: 15px;
  font-weight: 600;
  color: var(--app-text);
  max-width: 320px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
/* 套件级摘要 */
.sum-card {
  background: var(--app-card);
}
.sum-row {
  display: flex;
  align-items: center;
  gap: 28px;
  flex-wrap: wrap;
}
.sum-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 56px;
}
.sum-label {
  font-size: 12px;
  color: var(--app-text-muted);
}
.sum-val {
  font-size: 18px;
  font-weight: 600;
  color: var(--app-text);
  font-variant-numeric: tabular-nums;
}
.sum-val.txt {
  font-size: 13px;
  font-weight: 400;
  white-space: nowrap;
}
.sum-item.ok .sum-val { color: var(--el-color-success); }
.sum-item.bad .sum-val { color: var(--el-color-danger); }
.sum-item.warn .sum-val { color: var(--el-color-warning); }
.shared-box {
  margin-top: 12px;
  padding-top: 10px;
  border-top: 1px dashed var(--app-border);
  display: flex;
  align-items: baseline;
  gap: 10px;
  flex-wrap: wrap;
}
.shared-label {
  font-size: 12px;
  color: var(--app-text-muted);
  flex-shrink: 0;
}
.shared-vars {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}
.shared-tag {
  max-width: 100%;
}
/* 成员卡片 */
.member-card {
  background: var(--app-card);
}
.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.head-title {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}
.member-order {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: var(--app-active);
  color: var(--app-primary);
  font-size: 12px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.member-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--app-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.member-error {
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--el-color-danger);
  font-size: 13px;
  margin-bottom: 8px;
}
.no-rows,
.no-report {
  color: var(--app-text-muted);
  font-size: 12px;
}
</style>

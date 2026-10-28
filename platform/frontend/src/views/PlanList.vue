<template>
  <div class="page">
    <!-- 工具栏：项目过滤（默认当前项目，与其他列表页数据隔离一致）+ 新建入口 -->
    <div class="page-head">
      <div class="head-left">
        <span class="page-title">执行方案</span>
        <el-select
          v-model="filterProjectId"
          style="width: 150px"
          placeholder="项目"
          clearable
          filterable
          @change="load"
        >
          <el-option v-for="p in store.projects" :key="p.id" :label="p.name" :value="p.id" />
        </el-select>
        <span class="filter-count">共 {{ list.length }} 个方案</span>
      </div>
      <div class="head-right">
        <el-button type="primary" :icon="Plus" @click="openCreate">新建方案</el-button>
      </div>
    </div>

    <el-card shadow="never" class="card">
      <div v-if="loadError" class="app-load-error">
        <el-icon><WarningFilled /></el-icon>
        <span>{{ loadError }}</span>
        <el-button size="small" @click="load">重试</el-button>
      </div>
      <el-skeleton v-else-if="loading" :rows="6" animated class="skeleton-wrap" />
      <el-table v-else :data="list" stripe size="small" row-key="id">
        <template #empty>
          <EmptyState description="暂无执行方案" :image-size="80">
            <el-button type="primary" @click="openCreate">新建第一个方案</el-button>
          </EmptyState>
        </template>
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column label="方案名称" min-width="200" show-overflow-tooltip>
          <template #default="{ row }">
            <el-link type="primary" :underline="false" @click="router.push(`/plans/edit/${row.id}`)">
              {{ row.name }}
            </el-link>
            <el-tag v-if="row.mode === 'chain'" size="small" effect="plain" type="warning" class="mode-mark">串行链</el-tag>
            <span v-if="row.description" class="plan-desc" :title="row.description">· {{ row.description }}</span>
          </template>
        </el-table-column>
        <el-table-column label="项目" min-width="110" show-overflow-tooltip>
          <template #default="{ row }">
            {{ store.projects.find(p => p.id === row.project_id)?.name || (row.project_id ? `#${row.project_id}` : '全部项目') }}
          </template>
        </el-table-column>
        <el-table-column label="成员" width="70" align="center">
          <template #default="{ row }">
            <span class="app-data">{{ row.item_count }}</span>
          </template>
        </el-table-column>
        <el-table-column label="批量策略" width="90" align="center">
          <template #default="{ row }">
            <!-- combo：成员并行上限；chain：整链轮数×轮间并发（轮内恒串行） -->
            <el-tooltip v-if="row.mode === 'chain'" :content="`整链 ${row.rounds} 轮（轮内按序串行+相邻传参+失败阻断），轮间最多 ${row.concurrency} 轮并行`" placement="top" popper-class="app-tip">
              <span class="app-data">{{ row.rounds }}轮×{{ row.concurrency }}</span>
            </el-tooltip>
            <span v-else class="app-data">并发{{ row.concurrency }}</span>
          </template>
        </el-table-column>
        <el-table-column label="定时" min-width="150">
          <template #default="{ row }">
            <template v-if="row.schedule_type">
              <el-tag size="small" effect="plain" :type="row.schedule_enabled ? 'warning' : 'info'">
                {{ scheduleText(row) }}
              </el-tag>
              <el-tooltip v-if="row.next_run_at" :content="`下次触发：${formatTime(row.next_run_at)}`" placement="top" popper-class="app-tip">
                <span class="next-run">{{ formatRelativeTime(row.next_run_at) }}</span>
              </el-tooltip>
            </template>
            <span v-else class="no-schedule">未配置</span>
          </template>
        </el-table-column>
        <el-table-column label="总开关" width="70" align="center">
          <template #default="{ row }">
            <!-- 仅拦定时触发；手动一键不受限（tooltip 说明差异） -->
            <el-tooltip content="关=定时触发跳过；手动一键不受限" placement="top" popper-class="app-tip">
              <el-switch :model-value="row.enabled" size="small" @change="onToggleEnabled(row)" />
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="最近执行" width="110">
          <template #default="{ row }">
            <el-tooltip v-if="row.last_run_at" :content="formatTime(row.last_run_at)" placement="top" popper-class="app-tip">
              <span class="app-data">{{ formatRelativeTime(row.last_run_at) }}</span>
            </el-tooltip>
            <span v-else class="no-schedule">从未执行</span>
          </template>
        </el-table-column>
        <el-table-column label="更新人" width="90" align="center">
          <template #default="{ row }">{{ row.updated_by_name || row.created_by_name || '—' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="170" fixed="right" align="center">
          <template #default="{ row }">
            <el-tooltip :content="row.mode === 'chain' ? '一键执行（整链按轮驱动，轮内串行+传参）' : '一键执行（成员独立并行）'" placement="top">
              <el-button link type="success" size="small" :icon="VideoPlay" aria-label="一键执行方案" :loading="runningId === row.id" @click="onRun(row)" />
            </el-tooltip>
            <el-tooltip content="查看执行记录" placement="top">
              <el-button link type="primary" size="small" :icon="DataAnalysis" aria-label="查看执行记录" @click="router.push({ path: '/executions', query: { plan_id: String(row.id) } })" />
            </el-tooltip>
            <el-tooltip content="编辑方案" placement="top">
              <el-button link type="primary" size="small" :icon="Edit" aria-label="编辑方案" @click="router.push(`/plans/edit/${row.id}`)" />
            </el-tooltip>
            <el-tooltip content="删除方案" placement="top">
              <el-button link type="danger" size="small" :icon="Delete" aria-label="删除方案" @click="onRemove(row)" />
            </el-tooltip>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 新建方案：先建壳（名称/并发），成员与定时在编辑页配置 -->
    <el-dialog v-model="createVisible" title="新建执行方案" width="460px" align-center :close-on-click-modal="false">
      <el-form label-width="90px" @submit.prevent>
        <el-form-item label="所属项目">
          <el-select v-model="createForm.project_id" style="width: 100%" placeholder="选择项目（可空）" clearable>
            <el-option v-for="p in store.projects" :key="p.id" :label="p.name" :value="p.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="方案名称" required>
          <el-input v-model="createForm.name" placeholder="如：晨间冒烟" maxlength="200" @keyup.enter="onCreate" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="createForm.description" placeholder="方案用途说明（可选）" maxlength="500" />
        </el-form-item>
        <el-form-item label="执行并发">
          <el-input-number v-model="createForm.concurrency" :min="1" :max="16" />
          <span class="concurrency-tip">成员并行提交上限（1=串行）</span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="onCreate">创建并配置成员</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, VideoPlay, DataAnalysis, Edit, Delete, WarningFilled } from '@element-plus/icons-vue'
import { planApi, type ExecutionPlan } from '@/api'
import { useAppStore } from '@/stores'
import { storeToRefs } from 'pinia'
import { formatTime, formatRelativeTime } from '@/utils/format'
import { useExecutionRunner } from '@/composables/useExecutionRunner'
import EmptyState from '@/components/EmptyState.vue'

const router = useRouter()
const store = useAppStore()
const { currentProjectId } = storeToRefs(store)
const runner = useExecutionRunner()

const list = ref<ExecutionPlan[]>([])
const loading = ref(false)
const loadError = ref('')
const filterProjectId = ref<number | null>(currentProjectId.value)

// 一键执行防抖（同方案执行中不允许重复点击）
const runningId = ref<number | null>(null)

function scheduleText(row: ExecutionPlan): string {
  if (row.schedule_type === 'interval') return `每 ${row.schedule_interval_minutes} 分钟`
  return `每日 ${row.schedule_daily_time}`
}

async function load() {
  loading.value = true
  loadError.value = ''
  try {
    list.value = await planApi.list(filterProjectId.value ? { project_id: filterProjectId.value } : undefined)
  } catch (e: any) {
    loadError.value = e?.message || '加载失败'
  } finally {
    loading.value = false
  }
}

// 总开关：仅拦定时触发（手动一键不受限），与后端 enabled 语义一致
async function onToggleEnabled(row: ExecutionPlan) {
  try {
    const updated = await planApi.update(row.id, { enabled: !row.enabled })
    Object.assign(row, updated)
  } catch (e: any) {
    ElMessage.error(e.message || '切换失败')
  }
}

// 一键执行：确认（含成员摘要）→ runPlanWithFeedback（预检 400 直达提示）→ 跳方案过滤的执行记录
async function onRun(row: ExecutionPlan) {
  if (!row.item_count) return ElMessage.warning('方案未配置成员，请先编辑添加用例')
  try {
    const detail = row.mode === 'chain'
      ? `串行链共 ${row.item_count} 个成员，整链 ${row.rounds} 轮（轮内按序串行+相邻传参+失败阻断本轮下游，轮间最多 ${row.concurrency} 轮并行）`
      : `共 ${row.item_count} 个成员，按并发 ${row.concurrency} 独立并行执行（成员失败互不影响）`
    await ElMessageBox.confirm(`方案「${row.name}」${detail}，确认开始？`, '一键执行', {
      type: 'info',
      confirmButtonText: '开始执行',
    })
  } catch {
    return // 用户取消
  }
  runningId.value = row.id
  try {
    await runner.runPlanWithFeedback(row.id, row.name)
    router.push({ path: '/executions', query: { plan_id: String(row.id) } })
  } catch (e: any) {
    ElMessage.error(e.message || '执行失败')
  } finally {
    runningId.value = null
  }
}

async function onRemove(row: ExecutionPlan) {
  try {
    await ElMessageBox.confirm(
      `确认删除方案「${row.name}」？已产生的执行记录保留（溯源显示「方案 #${row.id}」）`,
      '删除方案',
      { type: 'warning', confirmButtonText: '确认删除' },
    )
  } catch {
    return // 用户取消
  }
  try {
    await planApi.remove(row.id)
    ElMessage.success('已删除')
    await load()
  } catch (e: any) {
    ElMessage.error(e.message || '删除失败')
  }
}

// ===== 新建 =====
const createVisible = ref(false)
const creating = ref(false)
const createForm = reactive({
  project_id: null as number | null,
  name: '',
  description: '',
  concurrency: 4,
})

function openCreate() {
  createForm.project_id = currentProjectId.value
  createForm.name = ''
  createForm.description = ''
  createForm.concurrency = 4
  createVisible.value = true
}

async function onCreate() {
  if (!createForm.name.trim()) return ElMessage.warning('请输入方案名称')
  creating.value = true
  try {
    const created = await planApi.create({
      project_id: createForm.project_id,
      name: createForm.name.trim(),
      description: createForm.description.trim() || undefined,
      concurrency: createForm.concurrency,
    })
    createVisible.value = false
    ElMessage.success('已创建，接下来添加成员')
    router.push(`/plans/edit/${created.id}`)
  } catch (e: any) {
    ElMessage.error(e.message || '创建失败')
  } finally {
    creating.value = false
  }
}

onMounted(load)

// 切换项目（顶栏全局上下文）：过滤跟随并重载，项目级数据隔离
watch(currentProjectId, (newId) => {
  filterProjectId.value = newId
  load()
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
.page-head {
  flex-shrink: 0;
}
.filter-count {
  margin-left: 4px;
  font-size: 12px;
  color: var(--app-text-muted);
}
.plan-desc {
  margin-left: 6px;
  font-size: 12px;
  color: var(--app-text-muted);
}
/* 串行链模式徽标（方案名称列） */
.mode-mark {
  margin-left: 6px;
}
.next-run {
  margin-left: 6px;
  font-size: 12px;
  color: var(--app-text-muted);
}
.no-schedule {
  font-size: 12px;
  color: var(--app-text-faint);
}
.concurrency-tip {
  margin-left: 8px;
  font-size: 12px;
  color: var(--app-text-muted);
}
</style>

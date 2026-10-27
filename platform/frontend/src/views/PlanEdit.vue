<template>
  <div class="page">
    <!-- 顶栏：返回 + 方案名编辑 + 保存/执行 -->
    <div class="page-head">
      <div class="head-left">
        <el-button @click="router.push('/plans')">
          <el-icon><ArrowLeft /></el-icon>返回
        </el-button>
        <span class="page-title">方案编辑</span>
        <el-input v-if="plan" v-model="name" style="width: 260px" placeholder="方案名称" maxlength="200" @input="dirty = true" />
        <el-tag v-if="plan" type="primary" effect="plain">方案 #{{ planId }}</el-tag>
      </div>
      <div class="head-right">
        <el-button :disabled="!dirty" :loading="saving" @click="onSave">保存 (Ctrl+S)</el-button>
        <el-button type="success" :loading="running" @click="onExecute">一键执行</el-button>
      </div>
    </div>

    <div v-loading="loading" class="edit-body">
      <div v-if="loadError" class="app-load-error">
        <el-icon><WarningFilled /></el-icon>
        <span>{{ loadError }}</span>
        <el-button size="small" @click="load">重试</el-button>
      </div>

      <template v-else-if="plan">
        <!-- 基础信息 -->
        <el-card shadow="never" class="meta-card">
          <el-form label-width="110px" @submit.prevent>
            <el-form-item label="描述">
              <el-input v-model="description" placeholder="方案用途说明（可选）" maxlength="500" @input="dirty = true" />
            </el-form-item>
            <el-form-item label="执行并发">
              <el-input-number v-model="concurrency" :min="1" :max="16" @change="dirty = true" />
              <span class="field-tip">成员并行提交上限（1=串行）；成员相互独立，失败互不影响</span>
            </el-form-item>
          </el-form>
        </el-card>

        <!-- 成员编辑：拖拽排序仅影响记录生成序（并行语义） -->
        <el-card shadow="never" class="member-card">
          <template #header>
            <div class="card-head">
              <span>方案成员（独立并行执行）</span>
              <span class="member-count">{{ items.length }} 个成员</span>
            </div>
          </template>

          <div v-if="items.length" ref="listRef" class="member-list">
            <div v-for="(m, i) in items" :key="m.case_id + '-' + i" class="member-row">
              <el-tooltip content="拖拽调整顺序（仅影响记录生成序）" placement="top" popper-class="app-tip">
                <el-icon class="drag-handle"><Rank /></el-icon>
              </el-tooltip>
              <span class="member-order">{{ i + 1 }}</span>
              <el-tag size="small" effect="plain" type="info">{{ projectName(m.project_id) }}</el-tag>
              <el-tag v-if="m.case_type === 'suite'" size="small" type="warning">套件</el-tag>
              <span class="member-name" :title="m.case_name">{{ m.case_name || `用例#${m.case_id}` }}</span>
              <el-tag v-if="m.case_missing" size="small" type="danger">用例已删除</el-tag>
              <el-tag v-else-if="m.case_type !== 'suite' && !m.env_id" size="small" type="danger">环境未绑定</el-tag>

              <div class="member-right">
                <!-- 数据集单选（换套执行）：选项懒加载（按用例隔离归属）；套件成员禁配覆盖 -->
                <el-select
                  v-if="m.case_type !== 'suite' && !m.case_missing"
                  :model-value="m.dataset_id ?? ''"
                  style="width: 240px"
                  size="small"
                  :loading="!dsOptions[m.case_id]"
                  :placeholder="m.dataset_id == null ? '用例默认绑定' : '数据集'"
                  @visible-change="(v: boolean) => v && loadDsOptions(m)"
                  @change="(v: any) => onPickDataset(m, v)"
                >
                  <el-option value="" label="用例默认绑定" />
                  <el-option
                    v-for="o in dsOptions[m.case_id] || []"
                    :key="o.id"
                    :label="o.label"
                    :value="o.id"
                    :disabled="o.disabled"
                  />
                </el-select>
                <el-tooltip v-else-if="m.case_type === 'suite'" content="套件成员各自绑定数据集，不能覆盖" placement="top" popper-class="app-tip">
                  <el-tag size="small" effect="plain" type="info">成员各自绑定</el-tag>
                </el-tooltip>
                <el-tooltip v-if="m.dataset_missing" :content="`覆盖数据集 #${m.dataset_id} 已删除，保存前请重选`" placement="top">
                  <el-tag size="small" type="danger">数据集悬空</el-tag>
                </el-tooltip>

                <span class="run-count-box">
                  <span class="run-count-label">×N</span>
                  <el-input-number v-model="m.run_count" :min="1" :max="9999" size="small" style="width: 100px" controls-position="right" @change="dirty = true" />
                </span>
                <el-button link type="danger" size="small" @click="removeItem(i)">移除</el-button>
              </div>
            </div>
          </div>
          <EmptyState v-else :image-size="80" description="暂无成员，从下方添加用例（可跨项目，可重复添加同一用例）" />

          <div class="add-row">
            <el-select v-model="addProjectId" style="width: 160px" placeholder="选择项目" filterable @change="onAddProjectChange">
              <el-option v-for="p in store.projects" :key="p.id" :label="p.name" :value="p.id" />
            </el-select>
            <el-select
              v-model="addCaseId"
              style="width: 280px"
              placeholder="选择用例（普通用例或套件）"
              filterable
              :loading="addCasesLoading"
              :disabled="!addProjectId"
            >
              <el-option
                v-for="c in addCases"
                :key="c.id"
                :label="`${c.name}${c.case_type === 'suite' ? '（套件）' : `（${c.dag_config?.nodes?.length || 0} 节点）`}`"
                :value="c.id"
              />
            </el-select>
            <el-button type="primary" :disabled="!addCaseId" @click="addItem">添加成员</el-button>
          </div>
          <div class="add-tip">
            普通用例需已绑定执行环境（未绑定的成员执行预检会精确报错）；套件作为成员时按其编排串行展开、数据集覆盖不生效
          </div>
        </el-card>

        <!-- 内嵌定时（B 方案：方案自带调度，与单用例定时互不影响） -->
        <el-card shadow="never" class="schedule-card">
          <template #header>
            <div class="card-head">
              <span>定时执行</span>
              <div class="schedule-head-right">
                <el-tooltip
                  :content="!plan.schedule_type
                    ? '尚未配置定时：先在下方选择调度类型并保存，之后可在此开关'
                    : scheduleEnabled
                      ? '停用后调度器跳过本轮（配置保留）· 保存后生效'
                      : '开启后由调度器接管定时执行 · 保存后生效'"
                  placement="top"
                  popper-class="app-tip"
                >
                  <el-switch
                    :model-value="!!plan.schedule_type && scheduleEnabled"
                    :disabled="!plan.schedule_type"
                    size="small"
                    @change="onToggleSchedule"
                  />
                </el-tooltip>
                <el-tag v-if="plan.next_run_at" size="small" effect="plain" type="info">
                  下次 {{ formatTime(plan.next_run_at) }}
                </el-tag>
                <el-button v-if="plan.schedule_type" link type="danger" size="small" @click="onClearSchedule">清除定时</el-button>
              </div>
            </div>
          </template>
          <el-form label-width="110px" @submit.prevent>
            <el-form-item label="调度类型">
              <el-radio-group v-model="scheduleType" @change="onScheduleTouched">
                <el-radio value="interval">间隔执行</el-radio>
                <el-radio value="daily">每日定时</el-radio>
              </el-radio-group>
            </el-form-item>
            <el-form-item v-if="scheduleType === 'interval'" label="间隔分钟">
              <el-input-number v-model="scheduleMinutes" :min="1" :max="525600" style="width: 180px" @change="onScheduleTouched" />
            </el-form-item>
            <el-form-item v-else label="每日时刻">
              <el-time-picker v-model="scheduleDaily" format="HH:mm" value-format="HH:mm" placeholder="如 08:30" style="width: 180px" @change="onScheduleTouched" />
            </el-form-item>
          </el-form>
          <div class="schedule-tip">
            保存后由调度器接管（时区 Asia/Shanghai；上轮未结束自动跳过合并，错过 60s 不补跑）。
            触发记录 trigger_type=方案定时，执行人归属方案创建者
          </div>
        </el-card>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, nextTick, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import Sortable from 'sortablejs'
import { ArrowLeft, Rank, WarningFilled } from '@element-plus/icons-vue'
import { caseApi, datasetApi, planApi, type TestCase } from '@/api'
import { useAppStore } from '@/stores'
import { useTabStore } from '@/stores/tabs'
import { useExecutionRunner } from '@/composables/useExecutionRunner'
import { formatTime } from '@/utils/format'
import EmptyState from '@/components/EmptyState.vue'

const route = useRoute()
const router = useRouter()
const store = useAppStore()
const tabStore = useTabStore()
const runner = useExecutionRunner()

const planId = Number(route.params.id)
const plan = ref<Awaited<ReturnType<typeof planApi.get>> | null>(null)
const loading = ref(false)
const loadError = ref('')
const dirty = ref(false)
const saving = ref(false)
const running = ref(false)

const name = ref('')
const description = ref('')
const concurrency = ref(4)

// 内嵌定时本地态（保存时随基础字段一并提交；清除走 schedule_off）
const scheduleType = ref<'interval' | 'daily'>('interval')
const scheduleMinutes = ref(30)
const scheduleDaily = ref('08:00')
const scheduleEnabled = ref(true)
// 本次编辑是否动过定时表单：决定保存时是否提交定时四件套
// （未配置的方案不得因普通保存被隐式配上默认 30 分钟定时；清除后不得随保存复活）
const scheduleTouched = ref(false)

function onScheduleTouched() {
  scheduleTouched.value = true
  dirty.value = true
}

function onToggleSchedule(v: string | number | boolean) {
  scheduleEnabled.value = !!v
  onScheduleTouched()
}

// 本地成员行（保存时整体替换提交）；env/project 信息由 caseApi.get 补全展示
interface ItemRow {
  case_id: number
  case_name: string
  case_type: string
  project_id: number | null
  env_id: number | null
  dataset_id: number | null
  case_dataset_id: number | null  // 用例自身绑定（dataset_id 空时实际生效）
  run_count: number
  case_missing: boolean
  dataset_missing: boolean
}
const items = ref<ItemRow[]>([])

// 数据集选项（按成员用例懒加载；单套语义：一个数据集 = 一套完整取值，无行选择）
interface DsOpt { id: number; label: string; disabled?: boolean }
const dsOptions = ref<Record<number, DsOpt[]>>({})

function projectName(pid: number | null): string {
  if (pid == null) return '未知项目'
  return store.projects.find(p => p.id === pid)?.name || `项目#${pid}`
}

// ===== 加载 =====
async function load() {
  if (!planId) return
  loading.value = true
  loadError.value = ''
  try {
    plan.value = await planApi.get(planId)
    name.value = plan.value.name
    description.value = plan.value.description || ''
    concurrency.value = plan.value.concurrency
    scheduleType.value = plan.value.schedule_type || 'interval'
    scheduleMinutes.value = plan.value.schedule_interval_minutes || 30
    scheduleDaily.value = plan.value.schedule_daily_time || '08:00'
    scheduleEnabled.value = plan.value.schedule_enabled
    scheduleTouched.value = false
    // 成员行回填 + caseApi.get 补全 env/project 展示（并行，成员数通常个位数）
    items.value = await Promise.all(plan.value.items.map(async (it) => {
      const base: ItemRow = {
        case_id: it.case_id, case_name: it.case_name || '', case_type: it.case_type || 'normal',
        project_id: null, env_id: null,
        dataset_id: it.dataset_id ?? null,
        case_dataset_id: it.case_dataset_id ?? null,
        run_count: it.run_count || 1,
        case_missing: !!it.case_missing, dataset_missing: !!it.dataset_missing,
      }
      if (base.case_missing) return base
      try {
        const c = await caseApi.get(it.case_id)
        base.case_name = c.name
        base.case_type = c.case_type || 'normal'
        base.project_id = c.project_id
        base.env_id = c.env_id ?? null
        base.case_dataset_id = c.dataset_id ?? null
      } catch { /* 用例详情取失败不阻塞编辑（执行预检兜底） */ }
      return base
    }))
    addProjectId.value = store.currentProjectId
    await onAddProjectChange(store.currentProjectId)
    dirty.value = false
    nextTick(initSortable)
  } catch (e: any) {
    loadError.value = e?.message || '加载失败'
  } finally {
    loading.value = false
  }
}

// ===== 拖拽排序 =====
const listRef = ref<HTMLElement | null>(null)
let sortable: Sortable | null = null

function initSortable() {
  destroySortable()
  if (!listRef.value) return
  sortable = Sortable.create(listRef.value, {
    handle: '.drag-handle',
    animation: 200,
    ghostClass: 'sortable-ghost',
    onEnd: (evt: any) => {
      const { oldIndex, newIndex } = evt
      if (oldIndex == null || newIndex == null || oldIndex === newIndex) return
      const arr = items.value
      const [moved] = arr.splice(oldIndex, 1)
      arr.splice(newIndex, 0, moved)
      dirty.value = true
    },
  })
}
function destroySortable() {
  if (sortable) { sortable.destroy(); sortable = null }
}

// ===== 添加成员（项目 → 用例两级级联，普通用例与套件均可） =====
const addProjectId = ref<number | null>(null)
const addCaseId = ref<number | null>(null)
const addCases = ref<TestCase[]>([])
const addCasesLoading = ref(false)

async function onAddProjectChange(pid: number | null) {
  addCaseId.value = null
  if (!pid) { addCases.value = []; return }
  addCasesLoading.value = true
  try {
    addCases.value = await caseApi.list(pid)
  } catch (e: any) {
    ElMessage.error(e.message || '加载项目用例失败')
    addCases.value = []
  } finally {
    addCasesLoading.value = false
  }
}

function addItem() {
  const c = addCases.value.find(x => x.id === addCaseId.value)
  if (!c) return
  items.value.push({
    case_id: c.id, case_name: c.name, case_type: c.case_type || 'normal',
    project_id: addProjectId.value, env_id: c.env_id ?? null,
    dataset_id: null, case_dataset_id: c.dataset_id ?? null, run_count: 1,
    case_missing: false, dataset_missing: false,
  })
  dirty.value = true
  addCaseId.value = null // 连续添加：保留项目选择
}

function removeItem(i: number) {
  items.value.splice(i, 1)
  dirty.value = true
}

// ===== 数据集选项（同执行面板「换套数据执行」口径：按用例隔离归属） =====
async function loadDsOptions(m: ItemRow) {
  if (dsOptions.value[m.case_id]) return
  try {
    // with_rows：判断「（无数据）」置灰必须有行数据（list 缺省不带 rows）
    const list = await datasetApi.list({ case_id: m.case_id, with_rows: true })
    dsOptions.value[m.case_id] = list.map(ds => ({
      id: ds.id,
      label: ds.rows.length
        ? ds.name + (ds.id === m.case_dataset_id ? '（用例绑定）' : '')
        : `${ds.name}（无数据）`,
      disabled: !ds.rows.length,
    }))
  } catch {
    dsOptions.value[m.case_id] = [{ id: -1, label: '数据集加载失败', disabled: true }]
  }
}

function onPickDataset(m: ItemRow, v: number | string) {
  m.dataset_id = v === '' ? null : Number(v)
  m.dataset_missing = false
  dirty.value = true
}

// ===== 保存（基础 + 定时一并提交，成员整体替换） =====
async function onSave(silent = false) {
  if (!name.value.trim()) return ElMessage.warning('请输入方案名称')
  saving.value = true
  try {
    plan.value = await planApi.update(planId, {
      name: name.value.trim(),
      description: description.value,
      concurrency: concurrency.value,
      // 已配置或本次动过定时才提交四件套：未配置不得隐式配上默认定时，清除后不得随保存复活
      ...(plan.value?.schedule_type || scheduleTouched.value
        ? {
            schedule_type: scheduleType.value,
            schedule_interval_minutes: scheduleType.value === 'interval' ? scheduleMinutes.value : null,
            schedule_daily_time: scheduleType.value === 'daily' ? scheduleDaily.value : null,
            schedule_enabled: scheduleEnabled.value,
          }
        : {}),
    })
    plan.value = await planApi.updateItems(planId, items.value.map((m, i) => ({
      case_id: m.case_id,
      dataset_id: m.dataset_id,
      run_count: m.run_count,
      sort_order: i,
    })))
    dirty.value = false
    if (!silent) ElMessage.success('已保存')
  } catch (e: any) {
    ElMessage.error(e.message || '保存失败')
    throw e
  } finally {
    saving.value = false
  }
}

// 清除定时：schedule_off 显式语义（schedule_type=null 在局部更新里表示「未提供」）
async function onClearSchedule() {
  try {
    plan.value = await planApi.update(planId, { schedule_off: true })
    // 本地表单一并复位，防后续普通保存让定时以默认值复活
    scheduleType.value = 'interval'
    scheduleMinutes.value = 30
    scheduleDaily.value = '08:00'
    scheduleEnabled.value = plan.value.schedule_enabled
    scheduleTouched.value = false
    ElMessage.success('已清除定时')
  } catch (e: any) {
    ElMessage.error(e.message || '清除失败')
  }
}

// ===== 一键执行：先落盘未保存的编辑，再走统一执行入口 =====
async function onExecute() {
  if (!items.value.length) return ElMessage.warning('请先添加成员用例')
  if (running.value) return
  try {
    if (dirty.value) await onSave(true)
  } catch {
    return // 保存失败已在 onSave 内提示
  }
  running.value = true
  try {
    await runner.runPlanWithFeedback(planId, name.value)
    await load() // 回写 last_run_at/next_run_at
  } catch (e: any) {
    ElMessage.error(e.message || '执行失败')
  } finally {
    running.value = false
  }
}

// ===== 未保存改动防丢失（与其余编辑器对齐） =====
watch(dirty, (v) => tabStore.setDirty(route.path, v ? '方案编辑' : null), { immediate: true })

const onBeforeUnload = (e: BeforeUnloadEvent) => {
  if (dirty.value) {
    e.preventDefault()
    e.returnValue = ''
  }
}
function onKeydown(e: KeyboardEvent) {
  if ((e.ctrlKey || e.metaKey) && e.key === 's') {
    e.preventDefault()
    onSave()
  }
}
onMounted(() => {
  window.addEventListener('beforeunload', onBeforeUnload)
  window.addEventListener('keydown', onKeydown)
})
onUnmounted(() => {
  window.removeEventListener('beforeunload', onBeforeUnload)
  window.removeEventListener('keydown', onKeydown)
})

onMounted(load)
onUnmounted(destroySortable)
</script>

<style scoped>
.page {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--app-bg);
}
.edit-body {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 12px 20px 20px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.meta-card,
.member-card,
.schedule-card {
  background: var(--app-card);
}
.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.member-count {
  font-size: 12px;
  color: var(--app-text-muted);
}
.field-tip {
  margin-left: 8px;
  font-size: 12px;
  color: var(--app-text-muted);
}
/* 成员列表 */
.member-list {
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius-sm);
  max-height: 420px;
  overflow-y: auto;
}
.member-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 12px;
  border-bottom: 1px solid var(--app-border);
  background: var(--el-bg-color);
}
.member-row:last-child {
  border-bottom: none;
}
.drag-handle {
  cursor: grab;
  color: var(--app-text-muted);
  font-size: 16px;
  flex-shrink: 0;
}
.drag-handle:active {
  cursor: grabbing;
}
.sortable-ghost {
  opacity: 0.4;
  background: var(--app-active) !important;
}
.member-order {
  width: 20px;
  text-align: center;
  font-size: 12px;
  color: var(--app-text-faint);
  font-variant-numeric: tabular-nums;
  flex-shrink: 0;
}
.member-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
}
.member-right {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}
.run-count-box {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.run-count-label {
  font-size: 12px;
  color: var(--app-text-muted);
}
/* 添加成员行 */
.add-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 14px;
  flex-wrap: wrap;
}
.add-tip {
  margin-top: 8px;
  font-size: 12px;
  color: var(--app-text-muted);
  line-height: 1.5;
}
/* 定时卡 */
.schedule-head-right {
  display: flex;
  align-items: center;
  gap: 10px;
}
.schedule-tip {
  font-size: 12px;
  color: var(--app-text-muted);
  line-height: 1.5;
}
</style>

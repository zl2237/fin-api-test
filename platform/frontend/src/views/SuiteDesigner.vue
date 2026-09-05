<template>
  <div class="page">
    <!-- 顶栏：返回 + 套件名/描述编辑 + 保存/执行 -->
    <div class="page-head">
      <div class="head-left">
        <el-button @click="router.push('/cases')">
          <el-icon><ArrowLeft /></el-icon>返回
        </el-button>
        <span class="page-title">套件编排</span>
        <el-input v-if="suite" v-model="name" style="width: 260px" placeholder="套件名称" maxlength="200" @input="dirty = true" />
        <el-tag v-if="suite" type="warning" effect="plain">套件 #{{ suiteId }}</el-tag>
      </div>
      <div class="head-right">
        <el-button :disabled="!dirty" :loading="saving" @click="onSave">保存</el-button>
        <el-button type="success" :loading="running" @click="onExecute">执行套件</el-button>
      </div>
    </div>

    <div v-loading="loading" class="suite-body">
      <div v-if="loadError" class="app-load-error">
        <el-icon><WarningFilled /></el-icon>
        <span>{{ loadError }}</span>
        <el-button size="small" @click="load">重试</el-button>
      </div>

      <template v-else-if="suite">
        <el-card shadow="never" class="meta-card">
          <el-form label-width="110px" @submit.prevent>
            <el-form-item label="描述">
              <el-input v-model="description" placeholder="套件用途说明（可选）" maxlength="500" @input="dirty = true" />
            </el-form-item>
            <el-form-item label="共享变量白名单">
              <div class="vars-box">
                <div v-if="sharedVars.length" class="vars-tags">
                  <el-tag
                    v-for="v in sharedVars"
                    :key="v"
                    closable
                    @close="removeVar(v)"
                  >{{ v }}</el-tag>
                </div>
                <div class="vars-input">
                  <el-input
                    v-model="newVar"
                    style="width: 220px"
                    placeholder="变量名，如 bl_no"
                    maxlength="100"
                    @keyup.enter="addVar"
                  />
                  <el-button @click="addVar">添加</el-button>
                </div>
                <div class="vars-tip">
                  上游成员每行执行结束后，按此名单从其变量池快照；下游成员执行时以最高优先级注入（
                  <code v-pre>${bl_no}</code> 引用，优先于数据集行值与环境变量）。下游用例单独执行不受影响（走自身数据集/环境变量）
                </div>
              </div>
            </el-form-item>
          </el-form>
        </el-card>

        <el-card shadow="never" class="member-card">
          <template #header>
            <div class="card-head">
              <span>成员链（按顺序串行执行）</span>
              <span class="member-count">{{ members.length }} 个成员</span>
            </div>
          </template>

          <!-- 成员列表：拖拽排序（自上而下即执行顺序） -->
          <div v-if="members.length" ref="listRef" class="member-list">
            <div v-for="(m, i) in members" :key="m.member_case_id + '-' + i" class="member-row">
              <el-tooltip content="拖拽调整执行顺序" placement="top" popper-class="app-tip">
                <el-icon class="drag-handle"><Rank /></el-icon>
              </el-tooltip>
              <span class="member-order">{{ i + 1 }}</span>
              <el-tag size="small" effect="plain" :type="m.project_id === suite.project_id ? 'info' : 'warning'">
                {{ m.project_name || `项目#${m.project_id}` }}
              </el-tag>
              <span class="member-name" :title="m.case_name">{{ m.case_name || `用例#${m.member_case_id}` }}</span>
              <el-tag v-if="m.member_case_type === 'suite'" size="small" type="danger">异常：成员是套件</el-tag>
              <span v-if="m.project_id !== suite.project_id" class="cross-mark">跨项目</span>
              <div class="member-right">
                <el-select
                  v-model="m.env_id"
                  size="small"
                  style="width: 180px"
                  placeholder="执行环境"
                  @change="dirty = true"
                >
                  <el-option
                    v-for="e in envsOf(m.project_id)"
                    :key="e.id"
                    :label="e.name"
                    :value="e.id"
                  />
                </el-select>
                <el-button link type="danger" size="small" @click="removeMember(i)">移除</el-button>
              </div>
            </div>
          </div>
          <EmptyState v-else :image-size="80" description="暂无成员，从下方添加用例（可跨项目引用）" />

          <!-- 添加成员：项目 → 用例 → 环境（三段级联） -->
          <div class="add-row">
            <el-select
              v-model="addProjectId"
              style="width: 160px"
              placeholder="选择项目"
              filterable
              @change="onAddProjectChange"
            >
              <el-option v-for="p in store.projects" :key="p.id" :label="p.name" :value="p.id" />
            </el-select>
            <el-select
              v-model="addCaseId"
              style="width: 260px"
              placeholder="选择用例（仅普通用例）"
              filterable
              :loading="addCasesLoading"
              :disabled="!addProjectId"
            >
              <el-option
                v-for="c in addCases"
                :key="c.id"
                :label="`${c.name}（${c.dag_config?.nodes?.length || 0} 节点）`"
                :value="c.id"
              />
            </el-select>
            <el-select
              v-model="addEnvId"
              style="width: 180px"
              placeholder="执行环境"
              filterable
              :disabled="!addProjectId"
            >
              <el-option v-for="e in envsOf(addProjectId)" :key="e.id" :label="e.name" :value="e.id" />
            </el-select>
            <el-button type="primary" :disabled="!addCaseId || !addEnvId" @click="addMember">添加成员</el-button>
          </div>
          <div class="add-tip">
            成员逐个绑定环境（跨系统各用各的）；上游成员若绑定数据集会按行展开，逐行快照注入下游对应行，上游某行失败则下游对应行阻断
          </div>
        </el-card>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import Sortable from 'sortablejs'
import { ArrowLeft, Rank, WarningFilled } from '@element-plus/icons-vue'
import { caseApi, envApi, type TestCase, type SuiteMember, type Environment } from '@/api'
import { useAppStore } from '@/stores'
import { useExecutionRunner } from '@/composables/useExecutionRunner'
import { useFaviconStatus } from '@/composables/useFaviconStatus'
import EmptyState from '@/components/EmptyState.vue'

const route = useRoute()
const router = useRouter()
const store = useAppStore()
const runner = useExecutionRunner()
const favicon = useFaviconStatus()

const suiteId = Number(route.params.id)
const suite = ref<TestCase | null>(null)
const loading = ref(false)
const loadError = ref('')
const dirty = ref(false)
const saving = ref(false)
const running = ref(false)

const name = ref('')
const description = ref('')
const sharedVars = ref<string[]>([])
const newVar = ref('')

// 本地成员行（保存时整体替换提交）
interface MemberRow {
  member_case_id: number
  env_id: number
  case_name: string
  project_id: number
  project_name: string
  member_case_type: string
}
const members = ref<MemberRow[]>([])

// 各项目环境缓存（成员可跨项目，环境按项目惰性加载）
const envCache = ref<Record<number, Environment[]>>({})
async function ensureEnvs(projectId: number | null | undefined) {
  if (!projectId || envCache.value[projectId]) return
  envCache.value[projectId] = await envApi.list(projectId)
}
function envsOf(projectId: number | null | undefined) {
  return (projectId && envCache.value[projectId]) || []
}

// 添加成员三段级联状态
const addProjectId = ref<number | null>(null)
const addCaseId = ref<number | null>(null)
const addEnvId = ref<number | null>(null)
const addCases = ref<TestCase[]>([])
const addCasesLoading = ref(false)

// ===== 拖拽排序（自上而下即执行顺序） =====
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
      const arr = members.value
      const [moved] = arr.splice(oldIndex, 1)
      arr.splice(newIndex, 0, moved)
      dirty.value = true
    },
  })
}
function destroySortable() {
  if (sortable) { sortable.destroy(); sortable = null }
}

// ===== 加载 =====
async function load() {
  if (!suiteId) return
  loading.value = true
  loadError.value = ''
  try {
    suite.value = await caseApi.get(suiteId)
    if (suite.value.case_type !== 'suite') {
      ElMessage.warning('该用例不是套件，已跳转到 DAG 编排页')
      router.replace(`/cases/designer/${suiteId}`)
      return
    }
    name.value = suite.value.name
    description.value = suite.value.description || ''
    sharedVars.value = [...(suite.value.shared_vars || [])]
    const outs: SuiteMember[] = await caseApi.getMembers(suiteId)
    members.value = outs.map(o => ({
      member_case_id: o.member_case_id,
      env_id: o.env_id,
      case_name: o.case_name || '',
      project_id: o.project_id || 0,
      project_name: o.project_name || '',
      member_case_type: o.member_case_type || 'normal',
    }))
    // 成员环境选项按项目惰性加载
    await Promise.all([...new Set(members.value.map(m => m.project_id).filter(Boolean))].map(ensureEnvs))
    await ensureEnvs(store.currentProjectId)
    // 添加面板默认当前项目，降低最常见路径（本项目管理员编排）的操作成本
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

async function onAddProjectChange(pid: number | null) {
  addCaseId.value = null
  addEnvId.value = null
  if (!pid) { addCases.value = []; return }
  addCasesLoading.value = true
  try {
    await ensureEnvs(pid)
    const all = await caseApi.list(pid)
    // 套件不能嵌套套件；也不能引用自身
    addCases.value = all.filter(c => c.case_type !== 'suite' && c.id !== suiteId)
    // 默认环境：本项目用顶栏当前环境，跨项目用其默认/首个
    const envs = envsOf(pid)
    addEnvId.value = pid === store.currentProjectId
      ? (store.currentEnvId ?? envs.find(e => e.is_default)?.id ?? envs[0]?.id ?? null)
      : (envs.find(e => e.is_default)?.id ?? envs[0]?.id ?? null)
  } catch (e: any) {
    ElMessage.error(e.message || '加载项目用例失败')
    addCases.value = []
  } finally {
    addCasesLoading.value = false
  }
}

function addMember() {
  if (!addCaseId.value || !addEnvId.value) return
  const c = addCases.value.find(x => x.id === addCaseId.value)
  if (!c) return
  const p = store.projects.find(x => x.id === addProjectId.value)
  members.value.push({
    member_case_id: c.id,
    env_id: addEnvId.value,
    case_name: c.name,
    project_id: addProjectId.value!,
    project_name: p?.name || '',
    member_case_type: 'normal',
  })
  dirty.value = true
  addCaseId.value = null  // 连续添加：保留项目与环境选择
}

function removeMember(i: number) {
  members.value.splice(i, 1)
  dirty.value = true
}

// ===== 共享变量白名单 =====
function addVar() {
  const v = newVar.value.trim()
  if (!v) return
  if (sharedVars.value.includes(v)) return ElMessage.warning(`变量 ${v} 已在白名单中`)
  sharedVars.value.push(v)
  newVar.value = ''
  dirty.value = true
}
function removeVar(v: string) {
  sharedVars.value = sharedVars.value.filter(x => x !== v)
  dirty.value = true
}

// ===== 保存（基本信息 + 成员整体替换） =====
async function onSave(silent = false) {
  if (!name.value.trim()) return ElMessage.warning('请输入套件名称')
  const badEnv = members.value.find(m => !m.env_id)
  if (badEnv) return ElMessage.warning(`成员「${badEnv.case_name}」未选择执行环境`)
  saving.value = true
  try {
    await caseApi.update(suiteId, {
      name: name.value.trim(),
      description: description.value,
      shared_vars: sharedVars.value,
    })
    await caseApi.updateMembers(suiteId, members.value.map(m => ({
      member_case_id: m.member_case_id, env_id: m.env_id,
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

// ===== 执行：先落盘未保存的编排，再走统一执行入口 =====
async function onExecute() {
  if (!members.value.length) return ElMessage.warning('请先添加成员用例')
  if (running.value) return
  try {
    if (dirty.value) await onSave(true)
  } catch {
    return  // 保存失败已在 onSave 内提示
  }
  running.value = true
  favicon.running()
  try {
    // env 仅作执行入参（套件主记录会对齐首成员环境）
    const rec = await caseApi.execute(suiteId, members.value[0].env_id)
    const cur = await runner.pollUntilDone(rec.id)
    if (cur.status === 'success') favicon.success()
    else favicon.failed()
    router.push(`/suite-reports/${rec.id}`)
  } catch (e: any) {
    favicon.reset()
    ElMessage.error(e.message || '执行失败')
  } finally {
    running.value = false
  }
}

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
.suite-body {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 12px 20px 20px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.meta-card,
.member-card {
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
.cross-mark {
  font-size: 12px;
  color: var(--el-color-warning);
  flex-shrink: 0;
}
.member-right {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
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
/* 共享变量白名单 */
.vars-box {
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: 100%;
}
.vars-tags {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}
.vars-input {
  display: flex;
  gap: 8px;
}
.vars-tip {
  font-size: 12px;
  color: var(--app-text-muted);
  line-height: 1.5;
}
</style>

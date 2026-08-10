<template>
  <div class="page">
    <div class="page-head">
      <div class="head-left">
        <el-button type="primary" @click="openCreate">+ 新建用例</el-button>
        <el-button @click="showGroupDialog = true">分组管理</el-button>
        <el-button
          :disabled="selectedCaseIds.length === 0"
          @click="onBatchMove"
        >批量移动到{{ selectedCaseIds.length ? `（已选 ${selectedCaseIds.length}）` : '' }}</el-button>
        <el-button
          type="success"
          :disabled="selectedCaseIds.length === 0 || batchRunning"
          :loading="batchRunning"
          @click="onBatchRun"
        >批量执行{{ selectedCaseIds.length ? `（已选 ${selectedCaseIds.length}）` : '' }}</el-button>
      </div>
      <div class="head-right">
        <el-select
          v-model="filterCreator"
          style="width: 140px"
          placeholder="创建人"
          clearable
          filterable
          @change="load"
        >
          <el-option v-for="u in users" :key="u.id" :label="u.name" :value="u.id" />
        </el-select>
        <el-select
          v-model="filterUpdater"
          style="width: 140px"
          placeholder="更新人"
          clearable
          filterable
          @change="load"
        >
          <el-option v-for="u in users" :key="u.id" :label="u.name" :value="u.id" />
        </el-select>
        <el-input v-model="keyword" style="width: 240px" placeholder="搜索用例名称" clearable />
      </div>
    </div>

    <div class="group-list">
      <el-collapse v-model="activeGroups">
        <el-collapse-item
          v-for="g in groupedCases"
          :key="g.group?.id ?? 'ungrouped'"
          :name="g.group?.id ?? 'ungrouped'"
        >
          <template #title>
            <div class="group-title">
              <el-icon class="group-icon"><Folder /></el-icon>
              <span class="group-name">{{ g.group?.name || '未分组' }}</span>
              <span class="group-count">{{ g.cases.length }}</span>
            </div>
          </template>
          <el-table
            :ref="(el: any) => setTableRef(g.group?.id ?? 'ungrouped', el)"
            :data="pagedCases(g.group?.id ?? 'ungrouped')"
            size="small"
            stripe
            row-key="id"
            @selection-change="(sel: any[]) => onSelectionChange(g.group?.id ?? 'ungrouped', sel)"
          >
            <el-table-column type="selection" width="42" />
            <el-table-column width="36" align="center">
              <template #default>
                <el-icon class="drag-handle" title="拖拽排序"><Rank /></el-icon>
              </template>
            </el-table-column>
            <el-table-column prop="id" label="ID" width="70" />
            <el-table-column prop="name" label="用例名称" min-width="180" show-overflow-tooltip />
            <el-table-column label="节点数" width="90">
              <template #default="{ row }">{{ row.dag_config?.nodes?.length || 0 }}</template>
            </el-table-column>
            <el-table-column prop="updated_at" label="更新时间" min-width="170" show-overflow-tooltip />
            <el-table-column label="创建人" width="100" align="center">
              <template #default="{ row }">{{ row.created_by_name || '未知' }}</template>
            </el-table-column>
            <el-table-column label="更新人" width="100" align="center">
              <template #default="{ row }">{{ row.updated_by_name || '未知' }}</template>
            </el-table-column>
            <el-table-column label="操作" width="320" fixed="right">
              <template #default="{ row }">
                <el-button link type="primary" size="small" @click="goDesign(row.id)">编排</el-button>
                <el-tooltip content="选中用例后按 Ctrl+Enter 可快速执行" placement="top">
                  <el-button link type="success" size="small" @click="runCase(row)">执行</el-button>
                </el-tooltip>
                <el-button link type="info" size="small" @click="goReport(row)">报告</el-button>
                <el-button link type="primary" size="small" @click="onCopy(row)">复制</el-button>
                <el-button link type="danger" size="small" @click="onRemove(row)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
          <div v-if="g.cases.length > pageSize" class="pagination-wrap">
            <el-pagination
              small
              :current-page="pageMap[String(g.group?.id ?? 'ungrouped')] || 1"
              :page-size="pageSize"
              :total="g.cases.length"
              :page-sizes="[10, 20, 50, 100]"
              layout="total, sizes, prev, pager, next"
              @current-change="(p: number) => onPageChange(g.group?.id ?? 'ungrouped', p)"
              @size-change="onPageSizeChange"
            />
          </div>
        </el-collapse-item>
      </el-collapse>
      <EmptyState v-if="!loading && !list.length" description="暂无用例">
        <div class="empty-actions">
          <el-button type="primary" @click="openCreate">+ 新建用例</el-button>
          <el-button text @click="router.push('/apis')">先去管理接口</el-button>
        </div>
      </EmptyState>
    </div>

    <!-- 新建用例弹窗 -->
    <el-dialog v-model="dialogVisible" title="新建用例" width="480px" align-center>
      <el-form :model="form" label-width="80px">
        <el-form-item label="名称">
          <el-input v-model="form.name" placeholder="创建订单-冒烟" />
        </el-form-item>
        <el-form-item label="分组">
          <el-select v-model="form.group_id" placeholder="选择分组" clearable style="width: 100%">
            <el-option v-for="g in groups" :key="g.id" :label="g.name" :value="g.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="form.description" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="onCreate">创建</el-button>
      </template>
    </el-dialog>

    <!-- 分组管理弹窗 -->
    <el-dialog v-model="showGroupDialog" title="用例分组管理" width="540px" align-center>
      <div class="group-dialog-body">
        <div class="group-add">
          <el-input v-model="newGroupName" placeholder="新分组名称（如：冒烟组/订单组/付款组）" style="flex: 1" @keyup.enter="onAddGroup" />
          <el-button type="primary" @click="onAddGroup">添加</el-button>
        </div>
        <div class="group-drag-tip">拖拽行可调整分组顺序，松开自动保存</div>
        <draggable
          v-model="groups"
          item-key="id"
          handle=".group-drag-handle"
          animation="200"
          class="group-drag-list"
          @end="onGroupDragEnd"
        >
          <template #item="{ element }">
            <div class="group-drag-row">
              <el-icon class="group-drag-handle" title="拖拽排序"><Rank /></el-icon>
              <span class="group-drag-name">{{ element.name }}</span>
              <div class="group-drag-actions">
                <el-button link type="primary" size="small" @click="onRenameGroup(element)">重命名</el-button>
                <el-button link type="danger" size="small" @click="onDeleteGroup(element)">删除</el-button>
              </div>
            </div>
          </template>
        </draggable>
      </div>
    </el-dialog>

    <!-- 批量移动弹窗 -->
    <el-dialog v-model="batchMoveVisible" title="批量移动到分组" width="420px" align-center>
      <div style="margin-bottom: 12px; color: var(--app-text-muted);">
        将 {{ selectedCaseIds.length }} 个用例移动到：
      </div>
      <el-select v-model="batchMoveTarget" placeholder="选择目标分组" style="width: 100%" filterable>
        <el-option label="未分组" :value="0" />
        <el-option v-for="g in groups" :key="g.id" :label="g.name" :value="g.id" />
      </el-select>
      <template #footer>
        <el-button @click="batchMoveVisible = false">取消</el-button>
        <el-button type="primary" :loading="batchMoveLoading" @click="confirmBatchMove">确定移动</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted, nextTick, toRef } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import draggable from 'vuedraggable'
import Sortable from 'sortablejs'
import { Rank, Folder } from '@element-plus/icons-vue'
import { caseApi, caseGroupApi, execApi, userApi, type TestCase, type CaseGroup, type SimpleUser } from '@/api'
import { useAppStore } from '@/stores'
import { useGroupMemory } from '@/composables/useGroupMemory'
import { useFaviconStatus } from '@/composables/useFaviconStatus'
import EmptyState from '@/components/EmptyState.vue'

const favicon = useFaviconStatus()

const store = useAppStore()
const router = useRouter()
const list = ref<TestCase[]>([])
const groups = ref<CaseGroup[]>([])
const users = ref<SimpleUser[]>([])
const filterCreator = ref<number | null>(null)
const filterUpdater = ref<number | null>(null)
const loading = ref(false)
const keyword = ref('')

// 分组展开/折叠记忆（按项目持久化）
const { activeNames: activeGroups, applyDefault: applyDefaultExpand } = useGroupMemory(
  toRef(store, 'currentProjectId'),
  'caseList',
)

// 分组内分页：每分组独立维护当前页码，全局共享每页条数
const pageSize = ref(10)
const pageMap = ref<Record<string, number>>({})
const dialogVisible = ref(false)
const showGroupDialog = ref(false)
const newGroupName = ref('')
const batchMoveVisible = ref(false)
const batchMoveTarget = ref<number | null>(null)
const batchMoveLoading = ref(false)
const batchRunning = ref(false)
const form = ref<{ name: string; group_id: number | null; description: string }>({ name: '', group_id: null, description: '' })

// ===== 批量移动：不支持跨分组勾选 =====
const tableRefs = new Map<string | number, any>()
let currentSelectGroupId: string | number | null = null
let isClearing = false
const selectedCaseIds = ref<number[]>([])

// ===== 组内拖拽排序（SortableJS 绑定 el-table tbody）=====
const sortableInstances = new Map<string | number, any>()

function setTableRef(groupId: string | number, el: any) {
  if (el) {
    tableRefs.set(groupId, el)
    nextTick(() => {
      const tbody = el.$el?.querySelector?.('.el-table__body-wrapper tbody')
      if (!tbody) return
      const old = sortableInstances.get(groupId)
      if (old) old.destroy()
      const inst = Sortable.create(tbody, {
        handle: '.drag-handle',
        animation: 200,
        ghostClass: 'sortable-ghost',
        onEnd: (evt: any) => onCaseRowDragEnd(groupId, evt.oldIndex, evt.newIndex),
      })
      sortableInstances.set(groupId, inst)
    })
  } else {
    tableRefs.delete(groupId)
    const old = sortableInstances.get(groupId)
    if (old) { old.destroy(); sortableInstances.delete(groupId) }
  }
}

async function onCaseRowDragEnd(groupId: string | number, oldIndex: number, newIndex: number) {
  if (oldIndex === newIndex) return
  const groupItem = groupedCases.value.find(g => (g.group?.id ?? 'ungrouped') === groupId)
  if (!groupItem) return
  const fullList = groupItem.cases
  const page = pageMap.value[String(groupId)] || 1
  const start = (page - 1) * pageSize.value
  // 在全量列表中移动（当前页内的拖拽映射到全量列表的全局位置）
  const moved = fullList.splice(start + oldIndex, 1)[0]
  fullList.splice(start + newIndex, 0, moved)
  // 对全量列表分配 sort_order（用索引作为唯一值，确保顺序持久化）
  const items = fullList.map((c, i) => ({ id: c.id, sort_order: i }))
  try {
    await caseApi.reorder(items)
    ElMessage.success('排序已保存')
    fullList.forEach((c, i) => { c.sort_order = i })
  } catch (e: any) {
    ElMessage.error(e.message || '排序保存失败')
    await load()
  }
}

async function onGroupDragEnd() {
  const items = groups.value.map((g, i) => ({ id: g.id, sort_order: i }))
  try {
    await Promise.all(items.map(it => caseGroupApi.update(it.id, { sort_order: it.sort_order })))
    ElMessage.success('分组顺序已保存')
  } catch (e: any) {
    ElMessage.error(e.message || '分组排序保存失败')
    await loadGroups()
  }
}

function onSelectionChange(groupId: string | number, selection: TestCase[]) {
  if (isClearing) return
  if (currentSelectGroupId !== null && currentSelectGroupId !== groupId) {
    isClearing = true
    tableRefs.forEach((tableRef, key) => {
      if (key !== groupId) tableRef?.clearSelection?.()
    })
    isClearing = false
  }
  currentSelectGroupId = groupId
  selectedCaseIds.value = selection.map(c => c.id)
}

function onBatchMove() {
  if (selectedCaseIds.value.length === 0) return
  batchMoveTarget.value = null
  batchMoveVisible.value = true
}

async function confirmBatchMove() {
  if (batchMoveTarget.value === null) {
    ElMessage.warning('请选择目标分组')
    return
  }
  batchMoveLoading.value = true
  try {
    const targetGroupId = batchMoveTarget.value === 0 ? null : batchMoveTarget.value
    const res = await caseApi.batchMove(selectedCaseIds.value, targetGroupId)
    ElMessage.success(res.message)
    batchMoveVisible.value = false
    selectedCaseIds.value = []
    currentSelectGroupId = null
    await load()
  } catch (e: any) {
    ElMessage.error(e.message || '批量移动失败')
  } finally {
    batchMoveLoading.value = false
  }
}

const filteredList = computed(() => {
  if (!keyword.value) return list.value
  const kw = keyword.value.toLowerCase()
  return list.value.filter(c => c.name.toLowerCase().includes(kw))
})

const groupedCases = computed(() => {
  const result: { group: CaseGroup | null; cases: TestCase[] }[] = []
  for (const g of groups.value) {
    const list = filteredList.value.filter(c => c.group_id === g.id)
    result.push({ group: g, cases: list })
  }
  const ungrouped = filteredList.value.filter(c => !c.group_id)
  if (ungrouped.length) {
    result.push({ group: null, cases: ungrouped })
  }
  return result
})

/** 返回某分组当前页的数据切片 */
function pagedCases(groupId: string | number): TestCase[] {
  const groupItem = groupedCases.value.find(g => (g.group?.id ?? 'ungrouped') === groupId)
  if (!groupItem) return []
  const page = pageMap.value[String(groupId)] || 1
  const start = (page - 1) * pageSize.value
  return groupItem.cases.slice(start, start + pageSize.value)
}

function onPageChange(groupId: string | number, page: number) {
  pageMap.value[String(groupId)] = page
}

/** 切换每页条数时，重置所有分组页码到第 1 页（避免越界） */
function onPageSizeChange(size: number) {
  pageSize.value = size
  pageMap.value = {}
}

async function load() {
  if (!store.currentProjectId) return
  loading.value = true
  try {
    list.value = await caseApi.list(store.currentProjectId, filterCreator.value ?? undefined, filterUpdater.value ?? undefined)
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

async function loadGroups() {
  if (!store.currentProjectId) return
  groups.value = await caseGroupApi.list(store.currentProjectId)
  // 无记忆时默认全部展开；有记忆则恢复上次展开的分组
  const allIds: (number | string)[] = groups.value.map(g => g.id)
  if (list.value.some(c => !c.group_id)) {
    allIds.push('ungrouped')
  }
  applyDefaultExpand(allIds)
  // 重置分页
  pageMap.value = {}
}

function openCreate() {
  form.value = { name: '', group_id: null, description: '' }
  dialogVisible.value = true
}

async function onCreate() {
  if (!form.value.name?.trim()) return ElMessage.warning('请输入用例名称')
  const created = await caseApi.create({
    project_id: store.currentProjectId!,
    group_id: form.value.group_id,
    name: form.value.name.trim(),
    description: form.value.description,
    dag_config: { nodes: [], edges: [] },
    node_configs: [],
  })
  ElMessage.success('已创建')
  dialogVisible.value = false
  goDesign(created.id)
}

function goDesign(id: number) {
  router.push(`/cases/designer/${id}`)
}

async function runCase(row: TestCase) {
  if (!store.currentEnvId) return ElMessage.warning('请先在顶部选择环境')
  try {
    // 异步执行：接口立即返回 running 状态的 record，后台线程池执行
    const rec = await caseApi.execute(row.id, store.currentEnvId)
    const execId = rec.id
    favicon.running()
    const msg = ElMessage({
      message: `用例「${row.name}」执行中...`,
      type: 'info',
      duration: 0,  // 不自动关闭
    })
    // 轮询执行状态，每 2 秒一次，最多 5 分钟
    const maxPolls = 150
    let pollCount = 0
    const poll = async () => {
      pollCount++
      try {
        const cur = await execApi.get(execId, true)
        if (cur.status === 'running' && pollCount < maxPolls) {
          setTimeout(poll, 2000)
        } else {
          msg.close()
          if (cur.status === 'success') {
            favicon.success()
            ElMessage.success(`执行通过：${cur.summary.passed}/${cur.summary.total}`)
          } else if (pollCount >= maxPolls) {
            favicon.reset()
            ElMessage.warning('执行超时，请到执行记录查看结果')
          } else {
            favicon.failed()
            ElMessage.warning(`执行失败：${cur.summary.failed} 项未通过`)
          }
          router.push(`/reports/${execId}`)
        }
      } catch (e: any) {
        msg.close()
        favicon.reset()
        ElMessage.error(e.message || '轮询执行状态失败')
      }
    }
    setTimeout(poll, 2000)
  } catch (e: any) {
    favicon.reset()
    ElMessage.error(e.message)
  }
}

// 批量执行：串行一个结束执行下一个（后端串行，前端逐个轮询）
async function onBatchRun() {
  if (!store.currentEnvId) return ElMessage.warning('请先在顶部选择环境')
  if (selectedCaseIds.value.length === 0) return ElMessage.warning('请先勾选用例')
  if (batchRunning.value) return
  batchRunning.value = true
  favicon.running()
  const msg = ElMessage({
    message: `批量执行中（共 ${selectedCaseIds.value.length} 个用例，串行执行）...`,
    type: 'info',
    duration: 0,
  })
  try {
    const records = await caseApi.batchExecute(selectedCaseIds.value, store.currentEnvId)
    // 逐个轮询：一个完成再查下一个（后端串行执行，record 会依次完成）
    const results: { name: string; status: string; summary: any }[] = []
    for (const rec of records) {
      const caseRow = list.value.find((c) => c.id === rec.case_id)
      const name = caseRow?.name || `用例#${rec.case_id}`
      const status = await pollOne(rec.id)
      results.push({ name, status: status.status, summary: status.summary })
    }
    msg.close()
    const passed = results.filter((r) => r.status === 'success').length
    const failed = results.length - passed
    if (failed === 0) favicon.success()
    else favicon.failed()
    const detail = results.map((r) => {
      if (r.status === 'success') return `✓ ${r.name}：通过（${r.summary?.passed}/${r.summary?.total}）`
      if (r.status === 'failed') return `✗ ${r.name}：失败（${r.summary?.failed} 项未通过）`
      return `! ${r.name}：${r.status}`
    }).join('\n')
    ElMessageBox.alert(detail, `批量执行完成：通过 ${passed}/${results.length}`, {
      confirmButtonText: '查看报告',
      cancelButtonText: '关闭',
      showCancelButton: true,
      type: passed === results.length ? 'success' : 'warning',
    }).then(() => {
      router.push('/executions')
    }).catch(() => {})
    await load()
  } catch (e: any) {
    msg.close()
    favicon.reset()
    ElMessage.error(e.message || '批量执行失败')
  } finally {
    batchRunning.value = false
  }
}

// 轮询单个执行记录直到完成，返回最终状态和汇总
function pollOne(execId: number): Promise<{ status: string; summary: any }> {
  return new Promise((resolve, reject) => {
    const maxPolls = 300
    let pollCount = 0
    const poll = async () => {
      pollCount++
      try {
        const cur = await execApi.get(execId, true)
        if (cur.status === 'running' && pollCount < maxPolls) {
          setTimeout(poll, 2000)
        } else {
          resolve({ status: cur.status, summary: cur.summary })
        }
      } catch (e: any) {
        reject(e)
      }
    }
    setTimeout(poll, 2000)
  })
}

function goReport(row: TestCase) {
  router.push({ path: '/executions', query: { case_id: row.id } })
}

async function onCopy(row: TestCase) {
  try {
    await caseApi.copy(row.id)
    ElMessage.success('已复制')
    await load()
  } catch (e: any) {
    ElMessage.error(e.message || '复制失败')
  }
}

async function onRemove(row: TestCase) {
  await ElMessageBox.confirm(`确定删除用例「${row.name}」？`, '提示', { type: 'warning' })
  await caseApi.remove(row.id)
  ElMessage.success('已删除')
  load()
}

async function onAddGroup() {
  if (!newGroupName.value.trim()) return
  try {
    await caseGroupApi.create({ project_id: store.currentProjectId!, name: newGroupName.value.trim() })
    newGroupName.value = ''
    await loadGroups()
    ElMessage.success('已添加')
  } catch (e: any) {
    ElMessage.error(e.message || '添加失败')
  }
}

async function onRenameGroup(row: CaseGroup) {
  try {
    const { value } = await ElMessageBox.prompt('分组名称', '重命名', { inputValue: row.name })
    if (value && value !== row.name) {
      await caseGroupApi.update(row.id, { name: value })
      await loadGroups()
      ElMessage.success('已重命名')
    }
  } catch (e) {
    // cancel
  }
}

async function onDeleteGroup(row: CaseGroup) {
  try {
    await ElMessageBox.confirm(`确认删除分组「${row.name}」？组内用例将变为未分组。`, '提示', { type: 'warning' })
    await caseGroupApi.remove(row.id)
    await loadGroups()
    await load()
    ElMessage.success('已删除')
  } catch (e: any) {
    if (e !== 'cancel') ElMessage.error(e.message || '删除失败')
  }
}

watch(() => store.currentProjectId, () => {
  load()
  loadGroups()
})
onMounted(() => {
  load()
  loadGroups()
  loadUsers()
  window.addEventListener('keydown', onGlobalKey)
})
onUnmounted(() => {
  window.removeEventListener('keydown', onGlobalKey)
})

// Ctrl+Enter：执行当前选中的用例（取第一个），无选中则提示
function onGlobalKey(e: KeyboardEvent) {
  if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
    if (selectedCaseIds.value.length === 0) {
      ElMessage.warning('请先勾选用例后再按 Ctrl+Enter 执行')
      return
    }
    e.preventDefault()
    const firstId = selectedCaseIds.value[0]
    const row = list.value.find((c) => c.id === firstId)
    if (row) runCase(row)
  }
}
</script>

<style scoped>
.page {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--app-bg);
}
.page-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 20px;
  background: var(--app-card);
  backdrop-filter: saturate(180%) blur(20px);
  border-bottom: 1px solid var(--app-border);
}
.head-left {
  display: flex;
  gap: 8px;
}
.group-list {
  flex: 1;
  overflow: auto;
  padding: 16px 20px;
}
/* 分组卡片化 */
:deep(.el-collapse) {
  border: none;
}
:deep(.el-collapse-item) {
  margin-bottom: 12px;
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius-lg);
  overflow: hidden;
  transition: border-color 0.18s ease, box-shadow 0.18s ease;
}
:deep(.el-collapse-item:hover) {
  border-color: var(--app-primary);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}
:deep(.el-collapse-item__header) {
  padding: 0 16px;
  height: 48px;
  line-height: 48px;
  background: var(--app-card);
  border-bottom: none;
  font-size: 14px;
}
:deep(.el-collapse-item__wrap) {
  border-bottom: none;
  background: transparent;
}
:deep(.el-collapse-item__content) {
  padding: 0 16px 12px;
}
.group-title {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
}
.group-icon {
  font-size: 16px;
  color: var(--app-primary);
}
.group-name {
  font-weight: 600;
  font-size: 14px;
  color: var(--app-text);
}
.group-count {
  background: var(--app-primary);
  color: #fff;
  border-radius: 10px;
  padding: 1px 10px;
  font-size: 12px;
  font-weight: 500;
  min-width: 24px;
  text-align: center;
}
.group-dialog-body {
  padding: 8px 4px;
}
.group-add {
  display: flex;
  gap: 8px;
}
.pagination-wrap {
  display: flex;
  justify-content: flex-end;
  margin-top: 8px;
}
.empty-actions {
  display: flex;
  flex-direction: column;
  gap: 10px;
  align-items: center;
}
.drag-handle {
  cursor: grab;
  color: var(--app-text-muted);
  font-size: 16px;
}
.drag-handle:active {
  cursor: grabbing;
}
.sortable-ghost {
  opacity: 0.4;
  background: var(--app-active) !important;
}
.group-drag-tip {
  font-size: 12px;
  color: var(--app-text-muted);
  margin: 12px 0 8px;
}
.group-drag-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.group-drag-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  background: var(--app-card-solid);
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius-sm);
}
.group-drag-handle {
  cursor: grab;
  color: var(--app-text-muted);
}
.group-drag-handle:active {
  cursor: grabbing;
}
.group-drag-name {
  flex: 1;
  font-size: 14px;
  color: var(--app-text);
}
.group-drag-actions {
  display: flex;
  gap: 4px;
}
</style>

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
              <span class="group-name">{{ g.group?.name || '未分组' }}</span>
              <span class="group-count">{{ g.cases.length }}</span>
            </div>
          </template>
          <el-table
            :ref="(el: any) => setTableRef(g.group?.id ?? 'ungrouped', el)"
            :data="sliceGroup(g.group?.id ?? 'ungrouped', g.cases)"
            size="small"
            stripe
            row-key="id"
            @selection-change="(sel: any[]) => onSelectionChange(g.group?.id ?? 'ungrouped', sel)"
          >
            <el-table-column type="selection" width="42" />
            <el-table-column prop="id" label="ID" width="70" />
            <el-table-column prop="name" label="用例名称" min-width="180" />
            <el-table-column label="节点数" width="90">
              <template #default="{ row }">{{ row.dag_config?.nodes?.length || 0 }}</template>
            </el-table-column>
            <el-table-column prop="updated_at" label="更新时间" min-width="170" />
            <el-table-column label="创建人" width="100" align="center">
              <template #default="{ row }">{{ row.created_by_name || '未知' }}</template>
            </el-table-column>
            <el-table-column label="更新人" width="100" align="center">
              <template #default="{ row }">{{ row.updated_by_name || '未知' }}</template>
            </el-table-column>
            <el-table-column label="操作" width="320" fixed="right">
              <template #default="{ row }">
                <el-button link type="primary" @click="goDesign(row.id)">编排</el-button>
                <el-tooltip content="选中用例后按 Ctrl+Enter 可快速执行" placement="top">
                  <el-button link type="success" @click="runCase(row)">执行</el-button>
                </el-tooltip>
                <el-button link type="info" @click="goReport(row)">报告</el-button>
                <el-button link type="primary" @click="onCopy(row)">复制</el-button>
                <el-button link type="danger" @click="onRemove(row)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
          <div v-if="g.cases.length > groupPageSize" class="pagination-wrap">
            <el-pagination
              :current-page="getGroupPage(g.group?.id ?? 'ungrouped')"
              :page-size="groupPageSize"
              :total="g.cases.length"
              layout="prev, pager, next"
              background
              small
              @current-change="(p: number) => setGroupPage(g.group?.id ?? 'ungrouped', p)"
            />
          </div>
        </el-collapse-item>
      </el-collapse>
      <el-empty v-if="!loading && !list.length" description="暂无用例">
        <div class="empty-actions">
          <el-button type="primary" @click="openCreate">+ 新建用例</el-button>
          <el-button text @click="router.push('/apis')">先去管理接口</el-button>
        </div>
      </el-empty>
    </div>

    <!-- 新建用例弹窗 -->
    <el-dialog v-model="dialogVisible" title="新建用例" width="480px">
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
    <el-dialog v-model="showGroupDialog" title="用例分组管理" width="540px">
      <div class="group-dialog-body">
        <div class="group-add">
          <el-input v-model="newGroupName" placeholder="新分组名称（如：冒烟组/订单组/付款组）" style="flex: 1" @keyup.enter="onAddGroup" />
          <el-button type="primary" @click="onAddGroup">添加</el-button>
        </div>
        <el-table :data="groups" size="small" border style="margin-top: 12px">
          <el-table-column label="分组名称" prop="name" />
          <el-table-column label="排序" width="100">
            <template #default="{ row }">
              <el-input-number v-model="row.sort_order" size="small" :min="0" controls-position="right" @change="onGroupSortChange(row)" />
            </template>
          </el-table-column>
          <el-table-column label="操作" width="120">
            <template #default="{ row }">
              <el-button link type="primary" size="small" @click="onRenameGroup(row)">重命名</el-button>
              <el-button link type="danger" size="small" @click="onDeleteGroup(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </el-dialog>

    <!-- 批量移动弹窗 -->
    <el-dialog v-model="batchMoveVisible" title="批量移动到分组" width="420px">
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
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { caseApi, caseGroupApi, execApi, userApi, type TestCase, type CaseGroup, type SimpleUser } from '@/api'
import { useAppStore } from '@/stores'

const store = useAppStore()
const router = useRouter()
const list = ref<TestCase[]>([])
const groups = ref<CaseGroup[]>([])
const users = ref<SimpleUser[]>([])
const filterCreator = ref<number | null>(null)
const filterUpdater = ref<number | null>(null)
const loading = ref(false)
const keyword = ref('')
const activeGroups = ref<(number | string)[]>([])
const dialogVisible = ref(false)
const showGroupDialog = ref(false)
const newGroupName = ref('')
const batchMoveVisible = ref(false)
const batchMoveTarget = ref<number | null>(null)
const batchMoveLoading = ref(false)
const form = ref<{ name: string; group_id: number | null; description: string }>({ name: '', group_id: null, description: '' })

// ===== 批量移动：不支持跨分组勾选 =====
const tableRefs = new Map<string | number, any>()
let currentSelectGroupId: string | number | null = null
let isClearing = false
const selectedCaseIds = ref<number[]>([])

// ===== 分组内分页 =====
const groupPages = ref<Record<string | number, number>>({})
const groupPageSize = ref(10)
function getGroupPage(id: string | number) {
  return groupPages.value[id] ?? 1
}
function setGroupPage(id: string | number, p: number) {
  groupPages.value[id] = p
}
function sliceGroup(id: string | number, arr: TestCase[]) {
  const p = getGroupPage(id)
  const start = (p - 1) * groupPageSize.value
  return arr.slice(start, start + groupPageSize.value)
}

function setTableRef(groupId: string | number, el: any) {
  if (el) tableRefs.set(groupId, el)
  else tableRefs.delete(groupId)
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

async function load() {
  if (!store.currentProjectId) return
  loading.value = true
  try {
    list.value = await caseApi.list(store.currentProjectId, filterCreator.value ?? undefined, filterUpdater.value ?? undefined)
    groupPages.value = {}
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
  activeGroups.value = groups.value.map(g => g.id)
  if (list.value.some(c => !c.group_id)) {
    activeGroups.value.push('ungrouped')
  }
}

function openCreate() {
  form.value = { name: '', group_id: null, description: '' }
  dialogVisible.value = true
}

async function onCreate() {
  if (!form.value.name) return ElMessage.warning('请输入用例名称')
  const created = await caseApi.create({
    project_id: store.currentProjectId!,
    group_id: form.value.group_id,
    name: form.value.name,
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
        const cur = await execApi.get(execId)
        if (cur.status === 'running' && pollCount < maxPolls) {
          setTimeout(poll, 2000)
        } else {
          msg.close()
          if (cur.status === 'success') {
            ElMessage.success(`执行通过：${cur.summary.passed}/${cur.summary.total}`)
          } else if (pollCount >= maxPolls) {
            ElMessage.warning('执行超时，请到执行记录查看结果')
          } else {
            ElMessage.warning(`执行失败：${cur.summary.failed} 项未通过`)
          }
          router.push(`/reports/${execId}`)
        }
      } catch (e: any) {
        msg.close()
        ElMessage.error(e.message || '轮询执行状态失败')
      }
    }
    setTimeout(poll, 2000)
  } catch (e: any) {
    ElMessage.error(e.message)
  }
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

async function onGroupSortChange(row: CaseGroup) {
  try {
    await caseGroupApi.update(row.id, { sort_order: row.sort_order })
    await loadGroups()
  } catch (e: any) {
    ElMessage.error(e.message || '排序失败')
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
.group-title {
  display: flex;
  align-items: center;
  gap: 8px;
}
.group-name {
  font-weight: 600;
  color: var(--app-text);
}
.group-count {
  background: var(--app-tag-bg);
  color: var(--app-text-muted);
  border-radius: 10px;
  padding: 1px 8px;
  font-size: 12px;
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
</style>

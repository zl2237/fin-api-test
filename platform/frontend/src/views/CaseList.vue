<template>
  <div class="page">
    <div class="page-head">
      <div class="head-left">
        <el-button type="primary" @click="openCreate">+ 新建用例</el-button>
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

    <!-- 左分组导航 + 右组内列表（master-detail）；页面级加载遮罩 -->
    <div v-loading="loading" class="group-layout">
      <aside class="group-side">
        <div
          class="side-node"
          :class="{ on: selectedRowKey === 'all' }"
          @click="selectedRowKey = 'all'"
        >
          <el-icon class="group-icon"><Folder /></el-icon>
          <span class="side-name">全部用例</span>
          <span class="side-cnt">{{ filteredList.length }}</span>
        </div>
        <div
          v-for="row in visibleGroupRows"
          :key="row.key"
          class="side-node"
          :class="{ on: selectedRowKey === row.key }"
          :style="{ paddingLeft: 10 + row.depth * 14 + 'px' }"
          @click="selectedRowKey = row.key"
        >
          <el-icon
            v-if="hasChildGroups(row.groupId)"
            class="expand-icon"
            :class="{ expanded: isGroupExpanded(row.groupId!) }"
            @click.stop="onToggleGroup(row)"
          ><CaretRight /></el-icon>
          <span v-else class="expand-spacer" />
          <span class="side-name">{{ row.name }}</span>
          <span class="side-cnt">{{ row.isUngrouped ? casesOf(null).length : countCasesWithDescendants(row.groupId!) }}</span>
        </div>
        <div class="side-foot">
          <el-button size="small" @click="showGroupDialog = true">分组管理</el-button>
        </div>
      </aside>

      <div class="group-main">
        <EmptyState v-if="!loading && !list.length" description="暂无用例">
          <div class="empty-actions">
            <el-button type="primary" @click="openCreate">+ 新建用例</el-button>
            <el-button text @click="router.push('/apis')">先去管理接口</el-button>
          </div>
        </EmptyState>

        <!-- 全部用例视图（跨分组平铺，无拖拽把手：跨组顺序无持久化语义） -->
        <template v-else-if="selectedRowKey === 'all'">
          <div class="main-head">
            <span class="main-title">全部用例</span>
            <span class="group-count">{{ filteredList.length }}</span>
          </div>
          <el-table
            :data="allPaged"
            size="small"
            stripe
            row-key="id"
            @selection-change="(sel: any[]) => onSelectionChange('all', sel)"
          >
            <el-table-column type="selection" width="42" />
            <el-table-column prop="id" label="ID" width="70" />
            <el-table-column prop="name" label="用例名称" min-width="180" show-overflow-tooltip />
            <el-table-column label="节点数" width="90">
              <template #default="{ row }">{{ row.dag_config?.nodes?.length || 0 }}</template>
            </el-table-column>
            <el-table-column prop="updated_at" label="更新时间" min-width="170" show-overflow-tooltip />
            <el-table-column label="创建人" width="100" align="center">
              <template #default="{ row }">{{ row.created_by_name || '—' }}</template>
            </el-table-column>
            <el-table-column label="更新人" width="100" align="center">
              <template #default="{ row }">{{ row.updated_by_name || '—' }}</template>
            </el-table-column>
            <el-table-column label="操作" width="320" fixed="right">
              <template #default="{ row }">
                <el-button link type="primary" size="small" @click="goDesign(row.id)">编排</el-button>
                <el-tooltip content="执行本行用例；勾选多行后按 Ctrl+Enter 从第一个勾选项开始执行" placement="top">
                  <el-button link type="success" size="small" @click="runCase(row)">执行</el-button>
                </el-tooltip>
                <el-button link type="primary" size="small" @click="goReport(row)">报告</el-button>
                <el-button link type="primary" size="small" @click="onCopy(row)">复制</el-button>
                <el-button link type="danger" size="small" @click="onRemove(row)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
          <div class="pagination-wrap">
            <el-pagination
              small
              background
              :current-page="allPage"
              :page-size="pageSize"
              :total="filteredList.length"
              :page-sizes="[10, 20, 50, 100]"
              layout="total, sizes, prev, pager, next"
              @current-change="(p: number) => onPageChange('all', p)"
              @size-change="onPageSizeChange"
            />
          </div>
        </template>

        <!-- 选中分组视图：单表 + 组内分页/勾选/拖拽（沿用 composable 按 key 驱动） -->
        <template v-else-if="selectedRow">
          <div class="main-head">
            <span class="main-title">{{ selectedRow.name }}</span>
            <span class="group-count">{{ selectedRow.isUngrouped ? casesOf(null).length : countCasesWithDescendants(selectedRow.groupId!) }}</span>
          </div>
          <el-table
            v-if="casesOf(selectedRow!.groupId).length"
            :ref="(el: any) => setTableRef(selectedRow!.key, el)"
            :data="pagedDataMap[String(selectedRow!.key)]"
            size="small"
            stripe
            row-key="id"
            @selection-change="(sel: any[]) => onSelectionChange(selectedRow!.key, sel)"
          >
            <el-table-column type="selection" width="42" :reserve-selection="true" />
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
              <template #default="{ row }">{{ row.created_by_name || '—' }}</template>
            </el-table-column>
            <el-table-column label="更新人" width="100" align="center">
              <template #default="{ row }">{{ row.updated_by_name || '—' }}</template>
            </el-table-column>
            <el-table-column label="操作" width="320" fixed="right">
              <template #default="{ row }">
                <el-button link type="primary" size="small" @click="goDesign(row.id)">编排</el-button>
                <el-tooltip content="执行本行用例；勾选多行后按 Ctrl+Enter 从第一个勾选项开始执行" placement="top">
                  <el-button link type="success" size="small" @click="runCase(row)">执行</el-button>
                </el-tooltip>
                <el-button link type="primary" size="small" @click="goReport(row)">报告</el-button>
                <el-button link type="primary" size="small" @click="onCopy(row)">复制</el-button>
                <el-button link type="danger" size="small" @click="onRemove(row)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
          <el-empty v-else-if="!loading" :image-size="80" description="该分组暂无用例" />
          <div v-if="casesOf(selectedRow!.groupId).length" class="pagination-wrap">
            <el-pagination
              small
              background
              :current-page="pageMap[String(selectedRow!.key)] || 1"
              :page-size="pageSize"
              :total="casesOf(selectedRow!.groupId).length"
              :page-sizes="[10, 20, 50, 100]"
              layout="total, sizes, prev, pager, next"
              @current-change="(p: number) => onPageChange(selectedRow!.key, p)"
              @size-change="onPageSizeChange"
            />
          </div>
        </template>
      </div>
    </div>

    <!-- 新建用例弹窗 -->
    <el-dialog v-model="dialogVisible" title="新建用例" width="480px" align-center>
      <el-form :model="form" label-width="80px">
        <el-form-item label="名称" required>
          <el-input v-model="form.name" placeholder="创建订单-冒烟" />
        </el-form-item>
        <el-form-item label="分组">
          <el-tree-select
            v-model="form.group_id"
            :data="treeSelectData"
            node-key="id"
            :props="treeProps"
            placeholder="选择分组"
            clearable
            check-strictly
            style="width: 100%"
          />
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

    <!-- 分组管理弹窗（多级：el-tree 拖拽调整层级与顺序） -->
    <el-dialog v-model="showGroupDialog" title="用例分组管理" width="620px" align-center class="group-manage-dialog">
      <div class="group-dialog-body">
        <div class="group-add">
          <el-input
            v-model="newGroupName"
            placeholder="新分组名称（如：冒烟组/订单组/付款组）"
            style="flex: 1"
            @keyup.enter="onAddGroup"
          />
          <el-tree-select
            v-model="newGroupParentId"
            :data="treeSelectData"
            node-key="id"
            :props="treeProps"
            placeholder="父分组（留空为顶层）"
            clearable
            check-strictly
            style="width: 220px"
          />
          <el-button type="primary" @click="onAddGroup">添加</el-button>
        </div>
        <div class="group-drag-tip">拖拽节点可调整层级与顺序，松开自动保存</div>
        <div class="group-tree-scroll">
          <el-tree
            ref="groupTreeRef"
            :data="groupTreeNodes"
            node-key="id"
            :props="treeProps"
            :expand-on-click-node="false"
            default-expand-all
            draggable
            @node-drop="onTreeNodeDrop"
          >
            <template #default="{ data }">
              <div class="group-tree-row">
                <span class="group-tree-name">{{ data.label }}</span>
                <div class="group-tree-actions">
                  <el-button link type="primary" size="small" @click.stop="onRenameGroup(data)">重命名</el-button>
                  <el-button link type="danger" size="small" @click.stop="onDeleteGroup(data)">删除</el-button>
                </div>
              </div>
            </template>
          </el-tree>
          <el-empty v-if="!groupTreeNodes.length" description="暂无分组" :image-size="60" />
        </div>
      </div>
    </el-dialog>

    <!-- 批量移动弹窗 -->
    <el-dialog v-model="batchMoveVisible" title="批量移动到分组" width="420px" align-center>
      <div style="margin-bottom: 12px; color: var(--app-text-muted);">
        将 {{ selectedCaseIds.length }} 个用例移动到：
      </div>
      <el-tree-select
        v-model="batchMoveTarget"
        :data="treeSelectWithUngrouped"
        node-key="id"
        :props="treeProps"
        placeholder="选择目标分组"
        clearable
        check-strictly
        style="width: 100%"
      />
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
import Sortable from 'sortablejs'
import { Rank, Folder, CaretRight } from '@element-plus/icons-vue'
import { caseApi, caseGroupApi, execApi, userApi, type TestCase, type CaseGroup, type SimpleUser } from '@/api'
import { useAppStore } from '@/stores'
import { useGroupTree, type GroupTreeNode } from '@/composables/useGroupTree'
import { useGroupedTable, collectTreeUpdates, setGroupSwitchNotifier } from '@/composables/useGroupedTable'
import { useFaviconStatus } from '@/composables/useFaviconStatus'
import EmptyState from '@/components/EmptyState.vue'

const favicon = useFaviconStatus()

const store = useAppStore()
const router = useRouter()

// 追踪所有执行轮询定时器，组件卸载时统一清理，避免切页后继续请求已失效的执行记录
const pollTimers: ReturnType<typeof setTimeout>[] = []
const list = ref<TestCase[]>([])
const groups = ref<CaseGroup[]>([])
const users = ref<SimpleUser[]>([])
const filterCreator = ref<number | null>(null)
const filterUpdater = ref<number | null>(null)
const loading = ref(false)
const keyword = ref('')

const filteredList = computed(() => {
  if (!keyword.value) return list.value
  const kw = keyword.value.toLowerCase()
  return list.value.filter(c => c.name.toLowerCase().includes(kw))
})

// 多级分组表格：树构建 + 展开记忆 + 分组过滤/计数/可见行/组内分页（样板已收敛进 composable）
const tableSel = useGroupedTable(groups, toRef(store, 'currentProjectId'), 'caseList', filteredList)
// 切分组勾选时提示（互斥勾选设计：不支持跨分组累计）
setGroupSwitchNotifier(() => ElMessage.info('不支持跨分组勾选，已切换为当前分组的选择'))
const {
  tree,
  treeSelectData,
  treeSelectWithUngrouped,
  isExpanded: isGroupExpanded,
  applyDefaultExpand,
  itemsOf: casesOf,
  countWithDescendants: countCasesWithDescendants,
  visibleGroupRows,
  onToggleGroup,
  pagedDataMap,
  pageSize,
  pageMap,
  onPageChange,
  onPageSizeChange,
  applyPageDragReorder,
  resetSelection,
  resetPages,
} = tableSel

// 搜索条件变化即回第 1 页，避免「第 3 页 + 结果不足一页」的空白死局
watch(keyword, () => resetPages())

// ===== 左分组导航选中态（master-detail）=====
const selectedRowKey = ref<string | number>('all')
const selectedRow = computed(() => visibleGroupRows.value.find(r => r.key === selectedRowKey.value))
// 左栏 caret 仅在「有子分组」时显示（composable 的 expandable 含"组内有数据"的旧手风琴语义，叶子分组展开无意义）
function hasChildGroups(groupId: number | null): boolean {
  if (groupId == null) return false
  return groups.value.some(g => g.parent_id === groupId)
}
// 分组重载/删除后选中项可能消失，回退到「全部」
watch(visibleGroupRows, (rows) => {
  if (selectedRowKey.value !== 'all' && !rows.some(r => r.key === selectedRowKey.value)) {
    selectedRowKey.value = 'all'
  }
})
// 「全部」视图分页：复用 composable 的 pageMap/pageSize（键 'all' 不与分组键冲突）
const allPage = computed(() => pageMap.value['all'] || 1)
const allPaged = computed(() => {
  const start = (allPage.value - 1) * pageSize.value
  return filteredList.value.slice(start, start + pageSize.value)
})

// el-tree / el-tree-select 公共字段映射
const treeProps = { label: 'label', children: 'children' }

const dialogVisible = ref(false)
const showGroupDialog = ref(false)
const newGroupName = ref('')
const newGroupParentId = ref<number | null>(null)
// el-tree 可变数据（管理弹窗拖拽用），groups 变化时重建
const groupTreeNodes = ref<GroupTreeNode[]>([])
const groupTreeRef = ref<any>(null)
const batchMoveVisible = ref(false)
const batchMoveTarget = ref<number | null>(null)
const batchMoveLoading = ref(false)
const batchRunning = ref(false)
const form = ref<{ name: string; group_id: number | null; description: string }>({ name: '', group_id: null, description: '' })

// ===== 批量移动：互斥勾选状态机在 useGroupedTable；视图只持有表格实例引用 =====
const tableRefs = new Map<string | number, any>()
const selectedCaseIds = tableSel.selectedIds

function clearOtherTables(keep: string | number) {
  tableRefs.forEach((tableRef, key) => {
    if (key !== keep) tableRef?.clearSelection?.()
  })
}

function clearAllTables() {
  tableRefs.forEach((tableRef) => tableRef?.clearSelection?.())
}

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
  try {
    const applied = await applyPageDragReorder(groupId, oldIndex, newIndex, (items) => caseApi.reorder(items))
    if (applied) ElMessage.success('排序已保存')
  } catch (e: any) {
    ElMessage.error(e.message || '排序保存失败')
    await load()
  }
}

/** el-tree 拖拽落点：持久化 parent_id + sort_order */
async function onTreeNodeDrop() {
  // el-tree 拖拽后已就地更新 groupTreeNodes，收集树平面更新载荷
  const updates = collectTreeUpdates(groupTreeNodes.value)
  try {
    await Promise.all(updates.map(it => caseGroupApi.update(it.id, { parent_id: it.parent_id, sort_order: it.sort_order })))
    ElMessage.success('分组层级与顺序已保存')
    await loadGroups()
  } catch (e: any) {
    ElMessage.error(e.message || '分组排序保存失败')
    await loadGroups()
  }
}

function onSelectionChange(groupId: string | number, selection: TestCase[]) {
  tableSel.onSelectionChange(groupId, selection, clearOtherTables)
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
    // 清空选中与 el-table 内部勾选态（reserve-selection 按 row-key 缓存，需主动 clearSelection）
    resetSelection(clearAllTables)
    await load()
  } catch (e: any) {
    ElMessage.error(e.message || '批量移动失败')
  } finally {
    batchMoveLoading.value = false
  }
}

// 分组过滤/计数/可见行/组内分页等样板已收敛至 useGroupedTable（见顶部解构）

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
  // 重建 el-tree 可变数据（深拷贝，供管理弹窗拖拽就地修改）
  groupTreeNodes.value = JSON.parse(JSON.stringify(treeSelectData.value))
  // 无记忆时默认全部展开
  applyDefaultExpand()
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
          const t = setTimeout(poll, 2000)
          pollTimers.push(t)
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
    const t = setTimeout(poll, 2000)
    pollTimers.push(t)
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
  // 二次确认：批量执行耗时长且产生一批执行记录，门槛不应低于「批量移动」
  try {
    await ElMessageBox.confirm(
      `将串行执行 ${selectedCaseIds.value.length} 个用例，可能需要较长时间。现在开始？`,
      '批量执行确认',
      { type: 'warning', confirmButtonText: '开始执行', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
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
          const t = setTimeout(poll, 2000)
          pollTimers.push(t)
        } else {
          resolve({ status: cur.status, summary: cur.summary })
        }
      } catch (e: any) {
        reject(e)
      }
    }
    const t = setTimeout(poll, 2000)
    pollTimers.push(t)
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
  // 对齐 ApiManage 的删除交互：取消静默（不产生 unhandled rejection），失败有提示
  try {
    await ElMessageBox.confirm(`确定删除用例「${row.name}」？`, '提示', { type: 'warning' })
  } catch {
    return
  }
  try {
    await caseApi.remove(row.id)
    ElMessage.success('已删除')
    load()
  } catch (e: any) {
    ElMessage.error(e.message || '删除失败')
  }
}

async function onAddGroup() {
  if (!newGroupName.value.trim()) return
  try {
    await caseGroupApi.create({
      project_id: store.currentProjectId!,
      parent_id: newGroupParentId.value,
      name: newGroupName.value.trim(),
    })
    newGroupName.value = ''
    newGroupParentId.value = null
    await loadGroups()
    ElMessage.success('已添加')
  } catch (e: any) {
    ElMessage.error(e.message || '添加失败')
  }
}

async function onRenameGroup(data: GroupTreeNode) {
  try {
    const { value } = await ElMessageBox.prompt('分组名称', '重命名', { inputValue: data.label })
    if (value && value !== data.label) {
      await caseGroupApi.update(data.id, { name: value })
      await loadGroups()
      ElMessage.success('已重命名')
    }
  } catch (e) {
    // cancel
  }
}

async function onDeleteGroup(data: GroupTreeNode) {
  try {
    await ElMessageBox.confirm(
      `确认删除分组「${data.label}」？\n注意：含子分组或用例时将阻止删除，请先处理。`,
      '提示',
      { type: 'warning' },
    )
    await caseGroupApi.remove(data.id)
    await loadGroups()
    await load()
    ElMessage.success('已删除')
  } catch (e: any) {
    if (e !== 'cancel') ElMessage.error(e.message || '删除失败')
  }
}

// 项目切换时：重置筛选并回第 1 页（统一行为，避免携带旧项目筛选）
watch(() => store.currentProjectId, () => {
  keyword.value = ''
  filterCreator.value = null
  filterUpdater.value = null
  resetPages()
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
  // 清理所有执行轮询定时器，防止切页后继续请求
  pollTimers.forEach(t => clearTimeout(t))
  pollTimers.length = 0
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
/* 左分组导航 + 右组内列表（master-detail） */
.group-layout {
  flex: 1;
  min-height: 0;
  display: flex;
}
.group-side {
  width: 220px;
  flex-shrink: 0;
  overflow: auto;
  padding: 12px 8px;
  background: var(--app-card);
  border-right: 1px solid var(--app-border);
  display: flex;
  flex-direction: column;
}
.side-node {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 0 10px;
  height: 32px;
  border-radius: var(--app-radius-sm);
  cursor: pointer;
  user-select: none;
  font-size: 13px;
  color: var(--app-text-muted);
  white-space: nowrap;
}
.side-node:hover {
  background: var(--app-hover);
  color: var(--app-text);
}
.side-node.on {
  background: var(--app-active);
  color: var(--app-primary);
  font-weight: 500;
}
.side-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
}
.side-cnt {
  font-size: 11px;
  font-variant-numeric: tabular-nums;
  color: var(--app-text-faint);
}
.side-node.on .side-cnt {
  color: var(--app-primary);
}
.side-foot {
  margin-top: auto;
  padding: 10px 6px 2px;
  border-top: 1px solid var(--app-border);
}
.group-main {
  flex: 1;
  min-width: 0;
  overflow: auto;
  padding: 16px 20px;
  display: flex;
  flex-direction: column;
}
.main-head {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
}
.main-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--app-text);
}
.expand-icon {
  font-size: 14px;
  color: var(--app-text-muted);
  transition: transform 0.18s ease;
}
.expand-icon.expanded {
  transform: rotate(90deg);
}
.expand-spacer {
  display: inline-block;
  width: 14px;
}
.group-icon {
  font-size: 16px;
  color: var(--app-primary);
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
  margin-right: 16px;
}
.group-body {
  padding: 0 16px 12px;
}
.group-dialog-body {
  padding: 8px 4px;
  display: flex;
  flex-direction: column;
  height: 100%;
}
.group-add {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-shrink: 0;
}
.group-tree-scroll {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding-right: 6px;
}
.group-tree-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  padding-right: 8px;
}
.group-tree-name {
  font-size: 14px;
  color: var(--app-text);
}
.group-tree-actions {
  display: flex;
  gap: 4px;
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
  flex-shrink: 0;
}
</style>
<!-- group-manage-dialog 全局样式已收敛至 style.css（原与 ApiManage 逐字符重复，两处漂移风险） -->

<template>
  <div class="api-manage">
    <!-- 顶部工具栏 -->
    <div class="toolbar">
      <div class="toolbar-left">
        <el-button type="primary" @click="onCreate">+ 新建接口</el-button>
        <el-button @click="showImportDialog = true">导入 Swagger</el-button>
        <el-button @click="showGroupDialog = true">分组管理</el-button>
        <el-button
          :disabled="selectedApiIds.length === 0"
          @click="onBatchMove"
        >批量移动到{{ selectedApiIds.length ? `（已选 ${selectedApiIds.length}）` : '' }}</el-button>
      </div>
      <div class="toolbar-right">
        <el-select
          v-model="filterCreator"
          style="width: 140px"
          placeholder="创建人"
          clearable
          filterable
          @change="loadApis"
        >
          <el-option v-for="u in users" :key="u.id" :label="u.name" :value="u.id" />
        </el-select>
        <el-select
          v-model="filterUpdater"
          style="width: 140px"
          placeholder="更新人"
          clearable
          filterable
          @change="loadApis"
        >
          <el-option v-for="u in users" :key="u.id" :label="u.name" :value="u.id" />
        </el-select>
        <el-input
          v-model="keyword"
          style="width: 240px"
          placeholder="搜索接口名/编码/路径"
          clearable
        />
      </div>
    </div>

    <!-- 分组折叠列表 -->
    <div class="group-list">
      <el-collapse v-model="activeGroups">
        <el-collapse-item
          v-for="g in groupedApis"
          :key="g.group?.id ?? 'ungrouped'"
          :name="g.group?.id ?? 'ungrouped'"
        >
          <template #title>
            <div class="group-title">
              <span class="group-name">{{ g.group?.name || '未分组' }}</span>
              <span class="group-count">{{ g.apis.length }}</span>
            </div>
          </template>
          <el-table
            :ref="(el: any) => setTableRef(g.group?.id ?? 'ungrouped', el)"
            :data="pagedApis(g.group?.id ?? 'ungrouped')"
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
            <el-table-column label="名称" prop="name" min-width="140" />
            <el-table-column label="编码" prop="code" width="160" />
            <el-table-column label="方法" prop="method" width="80">
              <template #default="{ row }">
                <el-tag :type="methodTag(row.method)" size="small" effect="plain">{{ row.method }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="路径" prop="path" min-width="220" show-overflow-tooltip />
            <el-table-column label="字段数" width="80" align="center">
              <template #default="{ row }">
                {{ (row.fields || []).length }}
              </template>
            </el-table-column>
            <el-table-column label="创建人" width="100" align="center">
              <template #default="{ row }">{{ row.created_by_name || '未知' }}</template>
            </el-table-column>
            <el-table-column label="更新人" width="100" align="center">
              <template #default="{ row }">{{ row.updated_by_name || '—' }}</template>
            </el-table-column>
            <el-table-column label="操作" width="200" fixed="right">
              <template #default="{ row }">
                <el-button link type="primary" size="small" @click="onEdit(row)">编辑</el-button>
                <el-button link type="primary" size="small" @click="onCopy(row)">复制</el-button>
                <el-button link type="danger" size="small" @click="onDelete(row)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
          <div v-if="g.apis.length > pageSize" class="pagination-wrap">
            <el-pagination
              small
              :current-page="pageMap[String(g.group?.id ?? 'ungrouped')] || 1"
              :page-size="pageSize"
              :total="g.apis.length"
              :page-sizes="[10, 20, 50, 100]"
              layout="total, sizes, prev, pager, next"
              @current-change="(p: number) => onPageChange(g.group?.id ?? 'ungrouped', p)"
              @size-change="onPageSizeChange"
            />
          </div>
        </el-collapse-item>
      </el-collapse>
      <el-empty v-if="!loading && !apis.length" description="暂无接口">
        <div class="empty-actions">
          <el-button type="primary" @click="onCreate">+ 新建接口</el-button>
          <el-button @click="showImportDialog = true">导入 Swagger</el-button>
          <el-button text @click="router.push('/envs')">先去配置环境</el-button>
        </div>
      </el-empty>
    </div>

    <!-- 分组管理弹窗 -->
    <el-dialog v-model="showGroupDialog" title="接口分组管理" width="540px">
      <div class="group-dialog-body">
        <div class="group-add">
          <el-input v-model="newGroupName" placeholder="新分组名称" style="flex: 1" @keyup.enter="onAddGroup" />
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

    <!-- 导入 Swagger 弹窗 -->
    <el-dialog v-model="showImportDialog" title="导入 Swagger/OpenAPI 接口" width="640px">
      <div class="import-body">
        <el-form label-width="80px">
          <el-form-item label="目标分组">
            <el-select v-model="importGroupId" placeholder="选择分组（可选）" clearable style="width: 100%">
              <el-option v-for="g in groups" :key="g.id" :label="g.name" :value="g.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="Swagger JSON">
            <el-input
              v-model="importSpecText"
              type="textarea"
              :rows="14"
              placeholder="粘贴完整的 Swagger/OpenAPI JSON（支持 2.0 和 3.0）"
            />
          </el-form-item>
        </el-form>
        <div v-if="importResult" class="import-result">
          <el-alert :title="importResult.message" :type="importResult.skipped.length ? 'warning' : 'success'" :closable="false" />
          <div v-if="importResult.skipped.length" class="import-skipped">
            <div class="skipped-title">跳过的接口：</div>
            <div v-for="(s, i) in importResult.skipped" :key="i" class="skipped-item">- {{ s }}</div>
          </div>
        </div>
      </div>
      <template #footer>
        <el-button @click="showImportDialog = false">关闭</el-button>
        <el-button type="primary" :loading="importLoading" @click="onImport">导入</el-button>
      </template>
    </el-dialog>

    <!-- 批量移动弹窗 -->
    <el-dialog v-model="batchMoveVisible" title="批量移动到分组" width="420px">
      <div style="margin-bottom: 12px; color: var(--app-text-muted);">
        将 {{ selectedApiIds.length }} 个接口移动到：
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
import { ref, computed, onMounted, watch, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import draggable from 'vuedraggable'
import Sortable from 'sortablejs'
import { apiApi, apiGroupApi, userApi, type ApiDef, type ApiGroup, type SimpleUser } from '@/api'

// 项目 ID 获取
import { useAppStore } from '@/stores'
import { storeToRefs } from 'pinia'
import { Rank } from '@element-plus/icons-vue'
import { useGroupMemory } from '@/composables/useGroupMemory'
const store = useAppStore()
const { currentProjectId } = storeToRefs(store)

const router = useRouter()
const apis = ref<ApiDef[]>([])
const groups = ref<ApiGroup[]>([])
const users = ref<SimpleUser[]>([])
const loading = ref(false)
const filterCreator = ref<number | null>(null)
const filterUpdater = ref<number | null>(null)
const keyword = ref('')

// 分组展开/折叠记忆（按项目持久化）
const { activeNames: activeGroups, applyDefault: applyDefaultExpand } = useGroupMemory(
  currentProjectId,
  'apiManage',
)

// 分组内分页：每分组独立维护当前页码，全局共享每页条数
const pageSize = ref(10)
const pageMap = ref<Record<string, number>>({})
const showGroupDialog = ref(false)
const newGroupName = ref('')
const batchMoveVisible = ref(false)
const batchMoveTarget = ref<number | null>(null)
const batchMoveLoading = ref(false)

// ===== 导入 Swagger =====
const showImportDialog = ref(false)
const importSpecText = ref('')
const importGroupId = ref<number | null>(null)
const importLoading = ref(false)
const importResult = ref<{ message: string; imported: any[]; skipped: string[] } | null>(null)

async function onImport() {
  if (!currentProjectId.value) return ElMessage.warning('请先选择项目')
  if (!importSpecText.value.trim()) return ElMessage.warning('请粘贴 Swagger JSON')
  let spec: Record<string, any>
  try {
    spec = JSON.parse(importSpecText.value)
  } catch (e: any) {
    return ElMessage.error('JSON 解析失败：' + e.message)
  }
  importLoading.value = true
  importResult.value = null
  try {
    const res = await apiApi.importSpec(currentProjectId.value, spec, importGroupId.value)
    importResult.value = res
    ElMessage.success(res.message)
    await loadApis()
  } catch (e: any) {
    ElMessage.error(e.message || '导入失败')
  } finally {
    importLoading.value = false
  }
}

// ===== 批量移动：不支持跨分组勾选 =====
// 每个分组的 el-table 实例引用
const tableRefs = new Map<string | number, any>()
// 当前选中所在的分组 id（切换分组时清空其他分组选中）
let currentSelectGroupId: string | number | null = null
// 清空其他分组选中时的标志位，避免触发循环 selection-change
let isClearing = false
const selectedApiIds = ref<number[]>([])

// ===== 组内拖拽排序（SortableJS 绑定 el-table tbody）=====
const sortableInstances = new Map<string | number, any>()

function setTableRef(groupId: string | number, el: any) {
  if (el) {
    tableRefs.set(groupId, el)
    // 初始化 SortableJS 行拖拽
    nextTick(() => {
      const tbody = el.$el?.querySelector?.('.el-table__body-wrapper tbody')
      if (!tbody) return
      // 已初始化则先销毁，避免重复
      const old = sortableInstances.get(groupId)
      if (old) old.destroy()
      const inst = Sortable.create(tbody, {
        handle: '.drag-handle',
        animation: 200,
        ghostClass: 'sortable-ghost',
        onEnd: (evt: any) => onApiRowDragEnd(groupId, evt.oldIndex, evt.newIndex),
      })
      sortableInstances.set(groupId, inst)
    })
  } else {
    tableRefs.delete(groupId)
    const old = sortableInstances.get(groupId)
    if (old) { old.destroy(); sortableInstances.delete(groupId) }
  }
}

async function onApiRowDragEnd(groupId: string | number, oldIndex: number, newIndex: number) {
  if (oldIndex === newIndex) return
  // 找到该分组的接口列表
  const groupItem = groupedApis.value.find(g => (g.group?.id ?? 'ungrouped') === groupId)
  if (!groupItem) return
  const fullList = groupItem.apis
  const page = pageMap.value[String(groupId)] || 1
  const start = (page - 1) * pageSize.value
  // 当前页在全量列表中的切片
  const pageSlice = fullList.slice(start, start + pageSize.value)
  // 取出当前页的 sort_order 值并排序，用于重新分配（不影响其他页的排序）
  const sortOrders = pageSlice.map(a => a.sort_order ?? 0).sort((a, b) => a - b)
  // 在当前页切片内移动
  const moved = pageSlice.splice(oldIndex, 1)[0]
  pageSlice.splice(newIndex, 0, moved)
  // 用排序后的原 sort_order 值重新分配
  const items = pageSlice.map((a, i) => ({ id: a.id, sort_order: sortOrders[i] }))
  try {
    await apiApi.reorder(items)
    ElMessage.success('排序已保存')
    pageSlice.forEach((a, i) => { a.sort_order = sortOrders[i] })
    // 同步全量列表：当前页前的 + 当前页（新顺序）+ 当前页后的
    const before = fullList.slice(0, start)
    const after = fullList.slice(start + pageSlice.length)
    fullList.splice(0, fullList.length, ...before, ...pageSlice, ...after)
  } catch (e: any) {
    ElMessage.error(e.message || '排序保存失败')
    await loadApis()
  }
}

async function onGroupDragEnd() {
  // 分组拖拽后，groups 数组顺序已变，批量更新 sort_order
  const items = groups.value.map((g, i) => ({ id: g.id, sort_order: i }))
  try {
    await Promise.all(items.map(it => apiGroupApi.update(it.id, { sort_order: it.sort_order })))
    ElMessage.success('分组顺序已保存')
  } catch (e: any) {
    ElMessage.error(e.message || '分组排序保存失败')
    await loadGroups()
  }
}

function onSelectionChange(groupId: string | number, selection: ApiDef[]) {
  // 清空操作触发的空 selection 不处理，避免循环
  if (isClearing) return
  // 切换到不同分组勾选时，清空其他分组的选中（不支持跨分组）
  if (currentSelectGroupId !== null && currentSelectGroupId !== groupId) {
    isClearing = true
    tableRefs.forEach((tableRef, key) => {
      if (key !== groupId) tableRef?.clearSelection?.()
    })
    isClearing = false
  }
  currentSelectGroupId = groupId
  selectedApiIds.value = selection.map(a => a.id)
}

function onBatchMove() {
  if (selectedApiIds.value.length === 0) return
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
    const res = await apiApi.batchMove(selectedApiIds.value, targetGroupId)
    ElMessage.success(res.message)
    batchMoveVisible.value = false
    selectedApiIds.value = []
    currentSelectGroupId = null
    await loadApis()
  } catch (e: any) {
    ElMessage.error(e.message || '批量移动失败')
  } finally {
    batchMoveLoading.value = false
  }
}

const filteredApis = computed(() => {
  if (!keyword.value) return apis.value
  const kw = keyword.value.toLowerCase()
  return apis.value.filter(a =>
    a.name.toLowerCase().includes(kw) ||
    a.code.toLowerCase().includes(kw) ||
    a.path.toLowerCase().includes(kw)
  )
})

const groupedApis = computed(() => {
  const result: { group: ApiGroup | null; apis: ApiDef[] }[] = []
  // 有分组的
  for (const g of groups.value) {
    const list = filteredApis.value.filter(a => a.group_id === g.id)
    result.push({ group: g, apis: list })
  }
  // 未分组的
  const ungrouped = filteredApis.value.filter(a => !a.group_id)
  if (ungrouped.length) {
    result.push({ group: null, apis: ungrouped })
  }
  return result
})

/** 返回某分组当前页的数据切片 */
function pagedApis(groupId: string | number): ApiDef[] {
  const groupItem = groupedApis.value.find(g => (g.group?.id ?? 'ungrouped') === groupId)
  if (!groupItem) return []
  const page = pageMap.value[String(groupId)] || 1
  const start = (page - 1) * pageSize.value
  return groupItem.apis.slice(start, start + pageSize.value)
}

function onPageChange(groupId: string | number, page: number) {
  pageMap.value[String(groupId)] = page
}

/** 切换每页条数时，重置所有分组页码到第 1 页（避免越界） */
function onPageSizeChange(size: number) {
  pageSize.value = size
  pageMap.value = {}
}

function methodTag(method: string) {
  const map: Record<string, any> = { GET: 'success', POST: 'primary', PUT: 'warning', DELETE: 'danger' }
  return map[method] || 'info'
}

async function loadApis() {
  if (!currentProjectId.value) return
  loading.value = true
  try {
    apis.value = await apiApi.list(currentProjectId.value, filterCreator.value ?? undefined, filterUpdater.value ?? undefined)
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
  if (!currentProjectId.value) return
  groups.value = await apiGroupApi.list(currentProjectId.value)
  // 无记忆时默认全部展开；有记忆则恢复上次展开的分组
  const allIds: (number | string)[] = groups.value.map(g => g.id)
  if (apis.value.some(a => !a.group_id)) {
    allIds.push('ungrouped')
  }
  applyDefaultExpand(allIds)
  // 重置分页
  pageMap.value = {}
}

function onCreate() {
  router.push('/apis/edit')
}

function onEdit(row: ApiDef) {
  router.push(`/apis/edit/${row.id}`)
}

async function onCopy(row: ApiDef) {
  try {
    await apiApi.copy(row.id)
    ElMessage.success('已复制')
    await loadApis()
  } catch (e: any) {
    ElMessage.error(e.message || '复制失败')
  }
}

async function onDelete(row: ApiDef) {
  try {
    await ElMessageBox.confirm(`确认删除接口「${row.name}」？`, '提示', { type: 'warning' })
    await apiApi.remove(row.id)
    ElMessage.success('已删除')
    await loadApis()
  } catch (e: any) {
    if (e !== 'cancel') ElMessage.error(e.message || '删除失败')
  }
}

async function onAddGroup() {
  if (!newGroupName.value.trim()) return
  try {
    await apiGroupApi.create({ project_id: currentProjectId.value!, name: newGroupName.value.trim() })
    newGroupName.value = ''
    await loadGroups()
    ElMessage.success('已添加')
  } catch (e: any) {
    ElMessage.error(e.message || '添加失败')
  }
}

async function onRenameGroup(row: ApiGroup) {
  try {
    const { value } = await ElMessageBox.prompt('分组名称', '重命名', { inputValue: row.name })
    if (value && value !== row.name) {
      await apiGroupApi.update(row.id, { name: value })
      await loadGroups()
      ElMessage.success('已重命名')
    }
  } catch (e) {
    // cancel
  }
}

async function onDeleteGroup(row: ApiGroup) {
  try {
    await ElMessageBox.confirm(
      `确认删除分组「${row.name}」？\n注意：组内仍有接口时将阻止删除，请先将接口移到其他分组。`,
      '提示',
      { type: 'warning' },
    )
    await apiGroupApi.remove(row.id)
    await loadGroups()
    await loadApis()
    ElMessage.success('已删除')
  } catch (e: any) {
    if (e !== 'cancel') ElMessage.error(e.message || '删除失败')
  }
}

onMounted(async () => {
  await loadApis()
  await loadGroups()
  await loadUsers()
})

// 项目切换时重新加载（与 CaseList/EnvManage 保持一致，避免初始化时 projectId 为空导致 no data）
watch(currentProjectId, () => {
  loadApis()
  loadGroups()
})
</script>

<style scoped>
.api-manage {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--app-bg);
}
.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 20px;
  background: var(--app-card);
  backdrop-filter: saturate(180%) blur(20px);
  border-bottom: 1px solid var(--app-border);
}
.toolbar-left {
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
.import-body {
  padding: 8px 4px;
}
.import-result {
  margin-top: 12px;
}
.import-skipped {
  margin-top: 8px;
  padding: 8px 12px;
  background: var(--app-warn-bg);
  color: var(--app-warn-text);
  border-radius: 6px;
  font-size: 12px;
  color: #8c6e2a;
  max-height: 160px;
  overflow: auto;
}
.skipped-title {
  font-weight: 600;
  margin-bottom: 4px;
}
.skipped-item {
  line-height: 1.6;
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

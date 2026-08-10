<template>
  <div class="api-manage">
    <!-- 顶部工具栏 -->
    <div class="toolbar">
      <div class="toolbar-left">
        <el-button type="primary" @click="onCreate">+ 新建接口</el-button>
        <el-button @click="showImportDialog = true">导入接口</el-button>
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
              <el-icon class="group-icon"><Files /></el-icon>
              <span class="group-name">{{ g.group?.name || '未分组' }}</span>
              <span class="group-count">{{ g.apis.length }}</span>
            </div>
          </template>
          <el-table
            v-loading="loading"
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
            <el-table-column label="名称" prop="name" min-width="140" show-overflow-tooltip />
            <el-table-column label="编码" prop="code" width="160" show-overflow-tooltip />
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
      <EmptyState v-if="!loading && !apis.length" description="暂无接口">
        <div class="empty-actions">
          <el-button type="primary" @click="onCreate">+ 新建接口</el-button>
          <el-button @click="showImportDialog = true">导入接口</el-button>
          <el-button text @click="router.push('/envs')">先去配置环境</el-button>
        </div>
      </EmptyState>
    </div>

    <!-- 分组管理弹窗 -->
    <el-dialog v-model="showGroupDialog" title="接口分组管理" width="540px" align-center>
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

    <!-- 导入接口弹窗（OpenAPI 粘贴 / HAR 上传） -->
    <el-dialog v-model="showImportDialog" title="导入接口" width="780px" align-center @close="onImportDialogClose">
      <el-tabs v-model="importTab" class="import-tabs">
        <!-- Tab 1: HAR 文件上传（默认） -->
        <el-tab-pane label="HAR 文件上传" name="har">
          <div class="import-body">
            <el-form label-width="80px">
              <el-form-item label="目标分组">
                <el-select v-model="importGroupId" placeholder="选择分组（可选）" clearable style="width: 100%">
                  <el-option v-for="g in groups" :key="g.id" :label="g.name" :value="g.id" />
                </el-select>
              </el-form-item>
              <el-form-item label="HAR 文件">
                <el-upload
                  :auto-upload="true"
                  :show-file-list="false"
                  :before-upload="onHarBeforeUpload"
                  :http-request="onHarUpload"
                  accept=".har"
                >
                  <el-button type="primary" :loading="harParsing">
                    <el-icon style="margin-right: 4px;"><Upload /></el-icon>
                    选择 HAR 文件
                  </el-button>
                  <template #tip>
                    <div class="el-upload__tip">浏览器开发者工具 → Network → 右键 → Save all as HAR，直接上传</div>
                  </template>
                </el-upload>
              </el-form-item>
            </el-form>

            <!-- HAR 解析预览：接口列表 + 勾选 -->
            <div v-if="harPreviews.length" class="har-preview">
              <div class="har-preview-header">
                <el-checkbox v-model="harSelectAll" @change="onHarSelectAll">全选</el-checkbox>
                <span class="har-preview-count">
                  共 {{ harPreviews.length }} 个接口，已选 {{ harSelectedCount }} 个
                </span>
              </div>
              <el-table ref="harTableRef" :data="harPreviews" max-height="360" border size="small" @selection-change="onHarSelectionChange">
                <el-table-column type="selection" width="42" />
                <el-table-column label="方法" width="72">
                  <template #default="{ row }">
                    <el-tag :type="methodTagType(row.method)" size="small" effect="plain">{{ row.method }}</el-tag>
                  </template>
                </el-table-column>
                <el-table-column label="路径" prop="path" min-width="200" show-overflow-tooltip />
                <el-table-column label="字段数" width="70" align="center">
                  <template #default="{ row }">{{ row.field_count }}</template>
                </el-table-column>
                <el-table-column label="数组体" width="60" align="center">
                  <template #default="{ row }">
                    <el-tag v-if="row.is_array_body" type="warning" size="small">[]</el-tag>
                    <span v-else style="color: var(--app-text-muted);">{{ '{}' }}</span>
                  </template>
                </el-table-column>
              </el-table>
            </div>
          </div>
        </el-tab-pane>

        <!-- Tab 2: OpenAPI 粘贴 -->
        <el-tab-pane label="OpenAPI / Swagger" name="openapi">
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
                  :rows="12"
                  placeholder="粘贴完整的 Swagger/OpenAPI JSON（支持 2.0 和 3.0）"
                />
              </el-form-item>
            </el-form>
          </div>
        </el-tab-pane>
      </el-tabs>

      <!-- 导入结果（两种模式共用） -->
      <div v-if="importResult" class="import-result">
        <el-alert :title="importResult.message" :type="importResult.skipped.length ? 'warning' : 'success'" :closable="false" />
        <div v-if="importResult.skipped.length" class="import-skipped">
          <div class="skipped-title">跳过的接口：</div>
          <div v-for="(s, i) in importResult.skipped" :key="i" class="skipped-item">- {{ s }}</div>
        </div>
      </div>

      <template #footer>
        <el-button @click="showImportDialog = false">关闭</el-button>
        <!-- OpenAPI 模式：导入按钮 -->
        <el-button v-if="importTab === 'openapi'" type="primary" :loading="importLoading" @click="onImport">导入</el-button>
        <!-- HAR 模式：导入按钮 -->
        <el-button v-if="importTab === 'har'" type="primary" :loading="importLoading" :disabled="harSelectedCount === 0" @click="onHarImport">导入勾选接口</el-button>
      </template>
    </el-dialog>

    <!-- 批量移动弹窗 -->
    <el-dialog v-model="batchMoveVisible" title="批量移动到分组" width="420px" align-center>
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
import EmptyState from '@/components/EmptyState.vue'
import { apiApi, apiGroupApi, userApi, type ApiDef, type ApiGroup, type SimpleUser, type HarPreviewItem } from '@/api'

// 项目 ID 获取
import { useAppStore } from '@/stores'
import { storeToRefs } from 'pinia'
import { Rank, Upload, Files } from '@element-plus/icons-vue'
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

// ===== 导入接口（OpenAPI 粘贴 / HAR 上传）=====
const showImportDialog = ref(false)
const importTab = ref<'openapi' | 'har'>('har')
const importSpecText = ref('')
const importGroupId = ref<number | null>(null)
const importLoading = ref(false)
const importResult = ref<{ message: string; imported: any[]; skipped: string[] } | null>(null)

// HAR 导入相关
const harParsing = ref(false)
const harPreviews = ref<HarPreviewItem[]>([])
const harSelectedPreviews = ref<HarPreviewItem[]>([])
const harSelectAll = ref(false)
const harTableRef = ref<any>(null)

const harSelectedCount = computed(() => harSelectedPreviews.value.length)

// 方法标签颜色
function methodTagType(method: string): 'primary' | 'success' | 'warning' | 'danger' | 'info' {
  const m = method.toUpperCase()
  if (m === 'GET') return 'success'
  if (m === 'POST') return 'primary'
  if (m === 'PUT') return 'warning'
  if (m === 'DELETE') return 'danger'
  return 'info'
}

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

// HAR 文件上传前校验
function onHarBeforeUpload(file: File): boolean {
  if (!file.name.toLowerCase().endsWith('.har')) {
    ElMessage.error('请上传 .har 文件')
    return false
  }
  if (file.size > 50 * 1024 * 1024) {
    ElMessage.error('文件超过 50MB 限制')
    return false
  }
  return true
}

// HAR 文件上传 + 解析预览
async function onHarUpload(options: any) {
  if (!currentProjectId.value) return ElMessage.warning('请先选择项目')
  const file = options.file as File
  harParsing.value = true
  harPreviews.value = []
  harSelectedPreviews.value = []
  harSelectAll.value = false
  importResult.value = null
  try {
    const res = await apiApi.previewHar(file)
    harPreviews.value = res.previews
    if (res.total === 0) {
      ElMessage.warning('HAR 文件中未解析出有效接口')
    } else {
      ElMessage.success(`解析出 ${res.total} 个接口，请勾选要导入的接口`)
    }
  } catch (e: any) {
    ElMessage.error(e.message || 'HAR 解析失败')
  } finally {
    harParsing.value = false
  }
}

// HAR 勾选变化
function onHarSelectionChange(selection: HarPreviewItem[]) {
  harSelectedPreviews.value = selection
  harSelectAll.value = selection.length === harPreviews.value.length && selection.length > 0
}

// HAR 全选/取消全选
function onHarSelectAll(val: any) {
  const checked = !!val
  if (!harTableRef.value) return
  harPreviews.value.forEach((_, index) => {
    harTableRef.value.toggleRowSelection(harPreviews.value[index], checked)
  })
}

// HAR 导入
async function onHarImport() {
  if (!currentProjectId.value) return ElMessage.warning('请先选择项目')
  if (harSelectedPreviews.value.length === 0) return ElMessage.warning('请勾选要导入的接口')
  importLoading.value = true
  importResult.value = null
  try {
    const res = await apiApi.importHar(currentProjectId.value, harSelectedPreviews.value, importGroupId.value)
    importResult.value = res
    ElMessage.success(res.message)
    await loadApis()
  } catch (e: any) {
    ElMessage.error(e.message || '导入失败')
  } finally {
    importLoading.value = false
  }
}

// 关闭导入弹窗时重置 HAR 状态
function onImportDialogClose() {
  harPreviews.value = []
  harSelectedPreviews.value = []
  harSelectAll.value = false
  importResult.value = null
  importSpecText.value = ''
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
  // 在全量列表中移动（当前页内的拖拽映射到全量列表的全局位置）
  const moved = fullList.splice(start + oldIndex, 1)[0]
  fullList.splice(start + newIndex, 0, moved)
  // 对全量列表分配 sort_order（用索引作为唯一值，确保顺序持久化）
  const items = fullList.map((a, i) => ({ id: a.id, sort_order: i }))
  try {
    await apiApi.reorder(items)
    ElMessage.success('排序已保存')
    fullList.forEach((a, i) => { a.sort_order = i })
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
.import-body {
  padding: 8px 4px;
}
.import-tabs {
  min-height: 320px;
}
.har-preview {
  margin-top: 12px;
}
.har-preview-header {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 8px;
  padding: 8px 0;
}
.har-preview-count {
  font-size: 13px;
  color: var(--app-text-muted);
}
.import-result {
  margin-top: 12px;
}
.import-skipped {
  margin-top: 8px;
  padding: 8px 12px;
  background: var(--app-warn-bg);
  color: var(--app-warn-text);
  border-radius: var(--app-radius-sm);
  font-size: 12px;
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

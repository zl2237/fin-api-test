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

    <!-- 分组树形列表（多级分组，展开/折叠带祖先可见性） -->
    <div class="group-list">
      <div
        v-for="row in visibleGroupRows"
        :key="row.key"
        class="group-card"
      >
        <div
          class="group-header"
          :style="{ paddingLeft: 14 + row.depth * 22 + 'px' }"
          @click="onToggleGroup(row)"
        >
          <el-icon
            v-if="row.hasChildren"
            class="expand-icon"
            :class="{ expanded: isGroupExpanded(row.groupId!) }"
          ><CaretRight /></el-icon>
          <span v-else class="expand-spacer" />
          <el-icon class="group-icon"><Files /></el-icon>
          <span class="group-name">{{ row.name }}</span>
          <span class="group-count">{{ row.isUngrouped ? apisOf(null).length : countApisWithDescendants(row.groupId!) }}</span>
        </div>
        <div v-show="(row.isUngrouped || isGroupExpanded(row.groupId!)) && apisOf(row.groupId).length > 0" class="group-body">
          <el-table
            v-loading="loading"
            :ref="(el: any) => setTableRef(row.key, el)"
            :data="pagedDataMap[String(row.key)]"
            size="small"
            stripe
            row-key="id"
            @selection-change="(sel: any[]) => onSelectionChange(row.key, sel)"
          >
            <el-table-column type="selection" width="42" :reserve-selection="true" />
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
          <div v-if="apisOf(row.groupId).length > pageSize" class="pagination-wrap">
            <el-pagination
              small
              :current-page="pageMap[String(row.key)] || 1"
              :page-size="pageSize"
              :total="apisOf(row.groupId).length"
              :page-sizes="[10, 20, 50, 100]"
              layout="total, sizes, prev, pager, next"
              @current-change="(p: number) => onPageChange(row.key, p)"
              @size-change="onPageSizeChange"
            />
          </div>
        </div>
      </div>
      <EmptyState v-if="!loading && !apis.length" description="暂无接口">
        <div class="empty-actions">
          <el-button type="primary" @click="onCreate">+ 新建接口</el-button>
          <el-button @click="showImportDialog = true">导入接口</el-button>
          <el-button text @click="router.push('/envs')">先去配置环境</el-button>
        </div>
      </EmptyState>
    </div>

    <!-- 分组管理弹窗（多级：el-tree 拖拽调整层级与顺序） -->
    <el-dialog v-model="showGroupDialog" title="接口分组管理" width="620px" align-center>
      <div class="group-dialog-body">
        <div class="group-add">
          <el-input
            v-model="newGroupName"
            placeholder="新分组名称"
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
    </el-dialog>

    <!-- 导入接口弹窗（cURL 粘贴 / HAR 上传 / OpenAPI 粘贴） -->
    <el-dialog v-model="showImportDialog" title="导入接口" width="780px" align-center @close="onImportDialogClose">
      <el-tabs v-model="importTab" class="import-tabs">
        <!-- Tab 1: cURL 命令粘贴（默认） -->
        <el-tab-pane label="cURL 命令" name="curl">
          <div class="import-body">
            <el-form label-width="80px">
              <el-form-item label="目标分组">
                <el-tree-select
                  v-model="importGroupId"
                  :data="treeSelectData"
                  node-key="id"
                  :props="treeProps"
                  placeholder="选择分组（可选）"
                  clearable
                  check-strictly
                  style="width: 100%"
                />
              </el-form-item>
              <el-form-item label="cURL 命令">
                <el-input
                  v-model="curlText"
                  type="textarea"
                  :rows="8"
                  placeholder="粘贴一条或多条 cURL 命令（多条以空行分隔），例如：&#10;curl -X POST 'http://host/api/order/create' -H 'Content-Type: application/json' -d '{&quot;bl_no&quot;:&quot;BL001&quot;}'"
                />
              </el-form-item>
              <el-form-item>
                <el-button type="primary" :loading="curlParsing" @click="onCurlPreview">
                  <el-icon style="margin-right: 4px;"><Search /></el-icon>
                  解析预览
                </el-button>
              </el-form-item>
            </el-form>

            <!-- cURL 解析错误提示 -->
            <el-alert
              v-if="curlErrors.length"
              type="warning"
              :closable="false"
              title="部分命令解析失败"
            >
              <div v-for="(e, i) in curlErrors" :key="i" style="font-size: 12px;">- {{ e }}</div>
            </el-alert>

            <!-- cURL 解析预览：接口列表 + 勾选（复用 HAR 预览表格） -->
            <div v-if="curlPreviews.length" class="har-preview">
              <div class="har-preview-header">
                <el-checkbox v-model="curlSelectAll" @change="onCurlSelectAll">全选</el-checkbox>
                <span class="har-preview-count">
                  共 {{ curlPreviews.length }} 个接口，已选 {{ curlSelectedCount }} 个
                </span>
              </div>
              <el-table ref="curlTableRef" :data="curlPreviews" max-height="360" border size="small" @selection-change="onCurlSelectionChange">
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

        <!-- Tab 2: HAR 文件上传 -->
        <el-tab-pane label="HAR 文件上传" name="har">
          <div class="import-body">
            <el-form label-width="80px">
              <el-form-item label="目标分组">
                <el-tree-select
                  v-model="importGroupId"
                  :data="treeSelectData"
                  node-key="id"
                  :props="treeProps"
                  placeholder="选择分组（可选）"
                  clearable
                  check-strictly
                  style="width: 100%"
                />
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

        <!-- Tab 3: OpenAPI 粘贴 -->
        <el-tab-pane label="OpenAPI / Swagger" name="openapi">
          <div class="import-body">
            <el-form label-width="80px">
              <el-form-item label="目标分组">
                <el-tree-select
                  v-model="importGroupId"
                  :data="treeSelectData"
                  node-key="id"
                  :props="treeProps"
                  placeholder="选择分组（可选）"
                  clearable
                  check-strictly
                  style="width: 100%"
                />
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
        <!-- cURL 模式：导入勾选接口 -->
        <el-button v-if="importTab === 'curl'" type="primary" :loading="importLoading" :disabled="curlSelectedCount === 0" @click="onCurlImport">导入勾选接口</el-button>
        <!-- HAR 模式：导入按钮 -->
        <el-button v-if="importTab === 'har'" type="primary" :loading="importLoading" :disabled="harSelectedCount === 0" @click="onHarImport">导入勾选接口</el-button>
        <!-- OpenAPI 模式：导入按钮 -->
        <el-button v-if="importTab === 'openapi'" type="primary" :loading="importLoading" @click="onImport">导入</el-button>
      </template>
    </el-dialog>

    <!-- 批量移动弹窗 -->
    <el-dialog v-model="batchMoveVisible" title="批量移动到分组" width="420px" align-center>
      <div style="margin-bottom: 12px; color: var(--app-text-muted);">
        将 {{ selectedApiIds.length }} 个接口移动到：
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
import { ref, computed, onMounted, watch, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import Sortable from 'sortablejs'
import EmptyState from '@/components/EmptyState.vue'
import { apiApi, apiGroupApi, userApi, type ApiDef, type ApiGroup, type SimpleUser, type HarPreviewItem } from '@/api'

// 项目 ID 获取
import { useAppStore } from '@/stores'
import { storeToRefs } from 'pinia'
import { Rank, Upload, Files, Search, CaretRight } from '@element-plus/icons-vue'
import { useGroupTree, collectDescendantIds, type GroupTreeNode } from '@/composables/useGroupTree'
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

// 多级分组：树构建 + 展开记忆（按项目持久化）
const {
  tree,
  treeSelectData,
  treeSelectWithUngrouped,
  isExpanded: isGroupExpanded,
  toggleExpand: toggleGroupExpand,
  applyDefaultExpand,
  computeVisibleRows,
} = useGroupTree(groups, currentProjectId, 'apiManage')

// el-tree / el-tree-select 公共字段映射
const treeProps = { label: 'label', children: 'children' }

// 分组内分页：每分组独立维护当前页码，全局共享每页条数
const pageSize = ref(10)
const pageMap = ref<Record<string, number>>({})
const showGroupDialog = ref(false)
const newGroupName = ref('')
const newGroupParentId = ref<number | null>(null)
// el-tree 可变数据（管理弹窗拖拽用），groups 变化时重建
const groupTreeNodes = ref<GroupTreeNode[]>([])
const groupTreeRef = ref<any>(null)
const batchMoveVisible = ref(false)
const batchMoveTarget = ref<number | null>(null)
const batchMoveLoading = ref(false)

// ===== 导入接口（cURL 粘贴 / HAR 上传 / OpenAPI 粘贴）=====
const showImportDialog = ref(false)
const importTab = ref<'curl' | 'har' | 'openapi'>('curl')
const importSpecText = ref('')
const importGroupId = ref<number | null>(null)
const importLoading = ref(false)
const importResult = ref<{ message: string; imported: any[]; skipped: string[] } | null>(null)

// cURL 导入相关
const curlText = ref('')
const curlParsing = ref(false)
const curlPreviews = ref<HarPreviewItem[]>([])
const curlSelectedPreviews = ref<HarPreviewItem[]>([])
const curlSelectAll = ref(false)
const curlErrors = ref<string[]>([])
const curlTableRef = ref<any>(null)
const curlSelectedCount = computed(() => curlSelectedPreviews.value.length)

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

// cURL 解析预览
async function onCurlPreview() {
  if (!currentProjectId.value) return ElMessage.warning('请先选择项目')
  if (!curlText.value.trim()) return ElMessage.warning('请粘贴 cURL 命令')
  curlParsing.value = true
  curlPreviews.value = []
  curlSelectedPreviews.value = []
  curlSelectAll.value = false
  curlErrors.value = []
  importResult.value = null
  try {
    const res = await apiApi.previewCurl(curlText.value)
    curlPreviews.value = res.previews
    curlErrors.value = res.errors || []
    if (res.total === 0) {
      ElMessage.warning('未解析出有效接口')
    } else {
      ElMessage.success(`解析出 ${res.total} 个接口，请勾选要导入的接口`)
    }
  } catch (e: any) {
    ElMessage.error(e.message || 'cURL 解析失败')
  } finally {
    curlParsing.value = false
  }
}

// cURL 勾选变化
function onCurlSelectionChange(selection: HarPreviewItem[]) {
  curlSelectedPreviews.value = selection
  curlSelectAll.value = selection.length === curlPreviews.value.length && selection.length > 0
}

// cURL 全选/取消全选
function onCurlSelectAll(val: any) {
  const checked = !!val
  if (!curlTableRef.value) return
  curlPreviews.value.forEach((_, index) => {
    curlTableRef.value.toggleRowSelection(curlPreviews.value[index], checked)
  })
}

// cURL 导入
async function onCurlImport() {
  if (!currentProjectId.value) return ElMessage.warning('请先选择项目')
  if (curlSelectedPreviews.value.length === 0) return ElMessage.warning('请勾选要导入的接口')
  importLoading.value = true
  importResult.value = null
  try {
    const res = await apiApi.importCurl(currentProjectId.value, curlSelectedPreviews.value, importGroupId.value)
    importResult.value = res
    ElMessage.success(res.message)
    await loadApis()
  } catch (e: any) {
    ElMessage.error(e.message || '导入失败')
  } finally {
    importLoading.value = false
  }
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

// 关闭导入弹窗时重置状态
function onImportDialogClose() {
  curlText.value = ''
  curlPreviews.value = []
  curlSelectedPreviews.value = []
  curlSelectAll.value = false
  curlErrors.value = []
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
  // 找到该分组的接口列表（apisOf 返回新数组，元素仍为 apis.value 中的同引用对象）
  const gid = groupId === 'ungrouped' ? null : (groupId as number)
  const fullList = apisOf(gid)
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

/** el-tree 拖拽落点：持久化 parent_id + sort_order */
async function onTreeNodeDrop() {
  // el-tree 拖拽后已就地更新 groupTreeNodes，遍历树重建 parent_id / sort_order
  const updates: { id: number; parent_id: number | null; sort_order: number }[] = []
  const walk = (nodes: GroupTreeNode[], parentId: number | null) => {
    nodes.forEach((n, i) => {
      updates.push({ id: n.id, parent_id: parentId, sort_order: i })
      walk(n.children, n.id)
    })
  }
  walk(groupTreeNodes.value, null)
  try {
    await Promise.all(updates.map(it => apiGroupApi.update(it.id, { parent_id: it.parent_id, sort_order: it.sort_order })))
    ElMessage.success('分组层级与顺序已保存')
    await loadGroups()
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
    // 清空 el-table 内部勾选态（reserve-selection 按 row-key 缓存，需主动 clearSelection）
    isClearing = true
    tableRefs.forEach((tableRef) => tableRef?.clearSelection?.())
    isClearing = false
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

/** 某分组的接口列表（未分组传 null） */
function apisOf(groupId: number | null): ApiDef[] {
  return filteredApis.value.filter(a => a.group_id === groupId)
}

/** 统计分组的接口数量（含所有子孙分组，用于分组头部计数展示） */
function countApisWithDescendants(groupId: number): number {
  const ids = [groupId, ...collectDescendantIds(tree.value, groupId)]
  return filteredApis.value.filter(a => a.group_id != null && ids.includes(a.group_id)).length
}

/** 主列表可见行：树扁平化 + 祖先展开可见性 + 未分组行 */
const visibleGroupRows = computed(() => computeVisibleRows(apisOf(null).length > 0))

/** 切换分组展开/折叠（未分组行不响应） */
function onToggleGroup(row: { groupId: number | null; isUngrouped: boolean }) {
  if (row.isUngrouped || row.groupId == null) return
  toggleGroupExpand(row.groupId)
}

/** 各分组当前页数据（computed 缓存：避免 selectedApiIds 变化时 :data 引用变化导致 el-table 重置 selection） */
const pagedDataMap = computed(() => {
  const map: Record<string, ApiDef[]> = {}
  for (const row of visibleGroupRows.value) {
    const list = apisOf(row.groupId)
    const page = pageMap.value[String(row.key)] || 1
    const start = (page - 1) * pageSize.value
    map[String(row.key)] = list.slice(start, start + pageSize.value)
  }
  return map
})

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
  // 重建 el-tree 可变数据（深拷贝，供管理弹窗拖拽就地修改）
  groupTreeNodes.value = JSON.parse(JSON.stringify(treeSelectData.value))
  // 无记忆时默认全部展开
  applyDefaultExpand()
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
    await apiGroupApi.create({
      project_id: currentProjectId.value!,
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
      await apiGroupApi.update(data.id, { name: value })
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
      `确认删除分组「${data.label}」？\n注意：含子分组或接口时将阻止删除，请先处理。`,
      '提示',
      { type: 'warning' },
    )
    await apiGroupApi.remove(data.id)
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
/* 分组卡片（多级树形） */
.group-card {
  margin-bottom: 12px;
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius-lg);
  overflow: hidden;
  background: var(--app-card);
  transition: border-color 0.18s ease, box-shadow 0.18s ease;
}
.group-card:hover {
  border-color: var(--app-primary);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}
.group-header {
  display: flex;
  align-items: center;
  gap: 8px;
  height: 48px;
  cursor: pointer;
  user-select: none;
  font-size: 14px;
  border-bottom: 1px solid var(--app-border);
}
.group-header:hover {
  background: var(--app-hover, rgba(0, 0, 0, 0.02));
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
.group-name {
  font-weight: 600;
  font-size: 14px;
  color: var(--app-text);
  flex: 1;
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
}
.group-add {
  display: flex;
  gap: 8px;
  align-items: center;
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
</style>

<template>
  <div class="api-manage">
    <!-- 顶部工具栏 -->
    <div class="page-head">
      <div class="head-left">
        <span class="page-title">接口管理</span>
        <el-button type="primary" @click="onCreate">+ 新建接口</el-button>
        <el-button @click="showImportDialog = true">导入接口</el-button>
        <el-dropdown style="margin-left: 12px" @command="(fmt: string) => onExport(fmt as 'excel' | 'json')">
          <el-button>
            导出<el-icon class="el-icon--right"><ArrowDown /></el-icon>
          </el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="excel">Excel 简表</el-dropdown-item>
              <el-dropdown-item command="json">JSON 全量（含字段明细）</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
      <div class="head-right">
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
        >
          <template #prefix><el-icon><Search /></el-icon></template>
        </el-input>
      </div>
    </div>

    <!-- 批量操作条：仅在有选中时浮现（GitHub 惯例），未选中不占空间 -->
    <Transition name="bulk-bar">
      <div v-if="selectedApiIds.length" class="bulk-bar">
        <span class="bulk-count">已选 {{ selectedApiIds.length }} 项</span>
        <el-button size="small" @click="onBatchMove">移动到分组</el-button>
        <el-button size="small" text @click="clearAllTables()">取消选择</el-button>
      </div>
    </Transition>

    <!-- 左分组导航 + 右组内列表（master-detail）；页面级单一加载遮罩 -->
    <div v-loading="loading" class="group-layout">
      <aside class="group-side">
        <div
          class="side-node"
          :class="{ on: selectedRowKey === 'all' }"
          @click="selectedRowKey = 'all'"
        >
          <el-icon class="group-icon"><Folder /></el-icon>
          <span class="side-name">全部接口</span>
          <span class="side-cnt">{{ filteredApis.length }}</span>
        </div>
        <div
          v-for="row in visibleGroupRows"
          :key="row.key"
          class="side-node"
          :class="{ on: selectedRowKey === row.key }"
          :style="{ paddingLeft: 10 + row.depth * 14 + 'px' }"
          @click="onSideNodeClick(row)"
        >
          <el-tooltip
            v-if="hasChildGroups(row.groupId)"
            content="展开/折叠子分组"
            placement="top"
          >
            <el-icon
              class="expand-icon"
              :class="{ expanded: isGroupExpanded(row.groupId!) }"
              @click.stop="onToggleGroup(row)"
            ><CaretRight /></el-icon>
          </el-tooltip>
          <span v-else class="expand-spacer" />
          <el-tooltip :content="row.name" placement="top" popper-class="app-tip" :disabled="row.name.length <= 12">
            <span class="side-name">{{ row.name }}</span>
          </el-tooltip>
          <span class="side-cnt">{{ row.isUngrouped ? apisOf(null).length : countApisWithDescendants(row.groupId!) }}</span>
        </div>
        <div class="side-foot">
          <el-button size="small" @click="showGroupDialog = true">分组管理</el-button>
        </div>
      </aside>

      <div class="group-main">
        <div v-if="loadError" class="app-load-error" style="margin-bottom: 12px">
          <el-icon><WarningFilled /></el-icon>
          <span>{{ loadError }}</span>
          <el-button size="small" @click="loadApis">重试</el-button>
        </div>

        <EmptyState v-else-if="!loading && !apis.length" description="暂无接口">
          <div class="empty-actions">
            <el-button type="primary" @click="onCreate">+ 新建接口</el-button>
            <el-button @click="showImportDialog = true">导入接口</el-button>
            <el-button text @click="router.push('/envs')">先去配置环境</el-button>
          </div>
        </EmptyState>

        <!-- 全部接口视图（跨分组平铺，无拖拽把手：跨组顺序无持久化语义） -->
        <template v-else-if="selectedRowKey === 'all'">
          <div class="main-head">
            <span class="main-title">全部接口</span>
            <span class="group-count">{{ filteredApis.length }}</span>
          </div>
          <el-table
            :data="allPaged"
            size="small"
            stripe
            row-key="id"
            @selection-change="(sel: any[]) => onSelectionChange('all', sel)"
          >
            <el-table-column type="selection" width="42" />
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
              <template #default="{ row }">{{ row.created_by_name || '—' }}</template>
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
          <div class="pagination-wrap">
            <el-pagination
              small
              background
              :current-page="allPage"
              :page-size="pageSize"
              :total="filteredApis.length"
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
            <span class="group-count">{{ selectedRow.isUngrouped ? apisOf(null).length : countApisWithDescendants(selectedRow.groupId!) }}</span>
          </div>
          <el-table
            v-if="selectedApis.length"
            :ref="(el: any) => setTableRef(selectedRow?.key, el)"
            :data="selectedPaged"
            size="small"
            stripe
            row-key="id"
            @selection-change="(sel: any[]) => onSelectionChange(selectedRow!.key, sel)"
          >
            <el-table-column type="selection" width="42" :reserve-selection="true" />
            <el-table-column width="36" align="center">
              <template #default>
                <!-- 父分组视图是跨组聚合列表，顺序无持久化语义，不提供拖拽 -->
                <el-tooltip v-if="!isSubtreeView" content="拖拽排序" placement="top" popper-class="app-tip">
                  <el-icon class="drag-handle"><Rank /></el-icon>
                </el-tooltip>
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
              <template #default="{ row }">{{ row.created_by_name || '—' }}</template>
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
          <EmptyState v-else-if="!loading" :image-size="80" description="该分组暂无接口" />
          <div v-if="apisOf(selectedRow!.groupId).length" class="pagination-wrap">
            <el-pagination
              small
              background
              :current-page="pageMap[String(selectedRow!.key)] || 1"
              :page-size="pageSize"
              :total="apisOf(selectedRow!.groupId).length"
              :page-sizes="[10, 20, 50, 100]"
              layout="total, sizes, prev, pager, next"
              @current-change="(p: number) => onPageChange(selectedRow!.key, p)"
              @size-change="onPageSizeChange"
            />
          </div>
        </template>
      </div>
    </div>

    <!-- 分组管理弹窗（多级：el-tree 拖拽调整层级与顺序；CRUD 与拖拽保存收敛在组件内） -->
    <GroupManageDialog
      v-model="showGroupDialog"
      title="接口分组管理"
      :tree-data="treeSelectData"
      :api="apiGroupApi"
      :project-id="currentProjectId"
      item-word="接口"
      @changed="onGroupsChanged"
    />

    <!-- 导入接口弹窗（cURL 粘贴 / HAR 上传 / OpenAPI 粘贴） -->
    <el-dialog v-model="showImportDialog" title="导入接口" width="80%" align-center :close-on-click-modal="false" @close="onImportDialogClose">
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
                <el-table-column label="名称" min-width="160">
                  <template #default="{ row }">
                    <el-input v-model="row.name" size="small" placeholder="接口名称，可直接修改" />
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
                <el-table-column label="名称" min-width="160">
                  <template #default="{ row }">
                    <el-input v-model="row.name" size="small" placeholder="接口名称，可直接修改" />
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

    <!-- 批量移动弹窗（目标选择与移动执行收敛在组件内，成功后自关） -->
    <BatchMoveDialog
      v-model="batchMoveVisible"
      :count="selectedApiIds.length"
      :tree-data="treeSelectWithUngrouped"
      item-word="接口"
      :move="doBatchMove"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import EmptyState from '@/components/EmptyState.vue'
import { apiApi, apiGroupApi, userApi, type ApiDef, type ApiGroup, type SimpleUser, type HarPreviewItem } from '@/api'

// 项目 ID 获取
import { useAppStore } from '@/stores'
import { storeToRefs } from 'pinia'
import { Rank, Upload, Folder, Search, CaretRight, WarningFilled, ArrowDown } from '@element-plus/icons-vue'
import { useGroupedTable, setGroupSwitchNotifier } from '@/composables/useGroupedTable'
import { useGroupMasterDetail } from '@/composables/useGroupMasterDetail'
import GroupManageDialog from '@/components/GroupManageDialog.vue'
import BatchMoveDialog from '@/components/BatchMoveDialog.vue'
import { debounce } from '@/utils/ui'
const store = useAppStore()
const { currentProjectId } = storeToRefs(store)

const router = useRouter()
const apis = ref<ApiDef[]>([])
const groups = ref<ApiGroup[]>([])
const users = ref<SimpleUser[]>([])
const loading = ref(false)
const loadError = ref('')
const filterCreator = ref<number | null>(null)
const filterUpdater = ref<number | null>(null)
const keyword = ref('')

const filteredApis = computed(() => {
  if (!keyword.value) return apis.value
  const kw = keyword.value.toLowerCase()
  return apis.value.filter(a =>
    a.name.toLowerCase().includes(kw) ||
    a.code.toLowerCase().includes(kw) ||
    a.path.toLowerCase().includes(kw)
  )
})

// 多级分组表格：树构建 + 展开记忆 + 分组过滤/计数/可见行/组内分页（样板已收敛进 composable）
const tableSel = useGroupedTable(groups, currentProjectId, 'apiManage', filteredApis)
// 切分组勾选时提示（互斥勾选设计：不支持跨分组累计）
setGroupSwitchNotifier(() => ElMessage.info('不支持跨分组勾选，已切换为当前分组的选择'))
const {
  tree,
  treeSelectData,
  treeSelectWithUngrouped,
  isExpanded: isGroupExpanded,
  applyDefaultExpand,
  itemsOf: apisOf,
  countWithDescendants: countApisWithDescendants,
  visibleGroupRows,
  onToggleGroup,
  pageSize,
  pageMap,
  onPageChange,
  onPageSizeChange,
  resetPages,
  applyPageDragReorder,
  resetSelection,
} = tableSel

// 搜索条件变化即回第 1 页，避免「第 3 页 + 结果不足一页」的空白死局
// 150ms 防抖：输入过程不逐键重算全量过滤链（对齐 DictManage/FileCenter 既有模式）
watch(keyword, debounce(() => resetPages(), 150))

// ===== 左分组导航选中态（master-detail 状态机收敛进 composable，与 CaseList 共用）=====
const {
  selectedRowKey,
  selectedRow,
  hasChildGroups,
  onSideNodeClick,
  isSubtreeView,
  selectedItems: selectedApis,
  selectedPaged,
  allPage,
  allPaged,
  setTableRef,
  clearOtherTables,
  clearAllTables,
} = useGroupMasterDetail({
  groups,
  tree,
  visibleGroupRows,
  itemsOf: apisOf,
  filteredItems: filteredApis,
  pageMap,
  pageSize,
  onRowDragEnd: onApiRowDragEnd,
})

// el-tree / el-tree-select 公共字段映射
const treeProps = { label: 'label', children: 'children' }

// 分组管理弹窗与批量移动弹窗的开合态（交互收敛在组件内，见模板）
const showGroupDialog = ref(false)
const batchMoveVisible = ref(false)

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

// ===== 批量移动：互斥勾选状态机在 useGroupedTable，表格实例/SortableJS 绑定在 useGroupMasterDetail =====
const selectedApiIds = tableSel.selectedIds

function onSelectionChange(groupId: string | number, selection: ApiDef[]) {
  tableSel.onSelectionChange(groupId, selection, clearOtherTables)
}

async function onApiRowDragEnd(groupId: string | number, oldIndex: number, newIndex: number) {
  try {
    const applied = await applyPageDragReorder(groupId, oldIndex, newIndex, (items) => apiApi.reorder(items))
    if (applied) ElMessage.success('排序已保存')
  } catch (e: any) {
    ElMessage.error(e.message || '排序保存失败')
    await loadApis()
  }
}

function onBatchMove() {
  if (selectedApiIds.value.length === 0) return
  batchMoveVisible.value = true
}

/** 批量移动执行（BatchMoveDialog 确认时调用；成功 resolve 弹窗自关，失败 throw 由弹窗报错） */
async function doBatchMove(targetGroupId: number | null) {
  const res = await apiApi.batchMove(selectedApiIds.value, targetGroupId)
  ElMessage.success(res.message)
  // 清空选中与 el-table 内部勾选态（reserve-selection 按 row-key 缓存，需主动 clearSelection）
  resetSelection(clearAllTables)
  await loadApis()
}

// ===== 列表导出（Excel 简表 / JSON 全量，筛选条件与列表页一致）=====
async function onExport(format: 'excel' | 'json') {
  if (!currentProjectId.value) return
  if (!filteredApis.value.length) return ElMessage.warning('当前没有可导出的接口')
  try {
    const blob = await apiApi.exportList({
      project_id: currentProjectId.value,
      format,
      created_by: filterCreator.value ?? undefined,
      updated_by: filterUpdater.value ?? undefined,
    })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    const stamp = new Date().toISOString().replace(/[-:T]/g, '').slice(0, 14)
    link.href = url
    link.download = `apis_${stamp}.${format === 'excel' ? 'xlsx' : 'json'}`
    link.click()
    URL.revokeObjectURL(url)
    // 不报具体数量：keyword 是前端本地过滤、不参与后端导出，报数会与文件实际条数不符
    ElMessage.success(format === 'excel' ? '已导出 Excel 简表' : '已导出 JSON 全量')
  } catch (e: any) {
    ElMessage.error(e.message || '导出失败')
  }
}

// 分组过滤/计数/可见行/组内分页等样板已收敛至 useGroupedTable（见顶部解构）

function methodTag(method: string) {
  const map: Record<string, any> = { GET: 'success', POST: 'primary', PUT: 'warning', DELETE: 'danger' }
  return map[method] || 'info'
}

async function loadApis() {
  if (!currentProjectId.value) return
  loading.value = true
  loadError.value = ''
  try {
    apis.value = await apiApi.list(currentProjectId.value, filterCreator.value ?? undefined, filterUpdater.value ?? undefined)
  } catch (e: any) {
    loadError.value = e?.message || '加载失败'
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

/** GroupManageDialog 变更回调：重载分组；删除时同步重载接口（其余变更不影响条目） */
async function onGroupsChanged(kind: 'add' | 'rename' | 'delete' | 'reorder') {
  await loadGroups()
  if (kind === 'delete') await loadApis()
}

onMounted(async () => {
  await loadApis()
  await loadGroups()
  await loadUsers()
})

// 项目切换时：重置筛选并回第 1 页（旧项目筛选会带着过期用户 id 请求新项目，结果集莫名变少）
watch(currentProjectId, () => {
  keyword.value = ''
  filterCreator.value = null
  filterUpdater.value = null
  resetPages()
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
/* 批量操作条：选中即浮现（高度过渡避免布局跳变） */
.bulk-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 20px;
  background: color-mix(in srgb, var(--app-primary) 7%, var(--app-card));
  border-bottom: 1px solid color-mix(in srgb, var(--app-primary) 22%, var(--app-border));
}
.bulk-count {
  font-size: 13px;
  font-weight: 600;
  color: var(--app-primary);
}
.bulk-bar-enter-active,
.bulk-bar-leave-active {
  transition: opacity 0.18s ease, transform 0.18s ease;
}
.bulk-bar-enter-from,
.bulk-bar-leave-to {
  opacity: 0;
  transform: translateY(-4px);
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
  cursor: pointer; /* caret 单击展开/折叠（与整行选中分离） */
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
  border-radius: var(--app-radius-sm);
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
/* 分组管理弹窗样式已随 GroupManageDialog 组件迁移（原与 CaseList 逐字重复） */
.pagination-wrap {
  display: flex;
  justify-content: flex-end;
  margin-top: 12px;
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
</style>
<!-- group-manage-dialog 全局样式已收敛至 style.css（原与 CaseList 逐字符重复，两处漂移风险） -->

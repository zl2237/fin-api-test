<template>
  <div class="page">
    <div class="page-head">
      <div class="head-left">
        <span class="page-title">用例管理</span>
        <el-button type="primary" @click="openCreate">+ 新建用例</el-button>
        <el-dropdown style="margin-left: 12px" @command="(fmt: string) => onExport(fmt as 'excel' | 'json')">
          <el-button>
            导出<el-icon class="el-icon--right"><ArrowDown /></el-icon>
          </el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="excel">Excel 简表</el-dropdown-item>
              <el-dropdown-item command="json">JSON 全量（含 DAG/断言/提取）</el-dropdown-item>
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
        <el-input v-model="keyword" style="width: 240px" placeholder="搜索用例（名称 / ID / 描述）" clearable>
          <template #prefix><el-icon><Search /></el-icon></template>
        </el-input>
      </div>
    </div>

    <!-- 批量操作条：仅在有选中时浮现（与接口管理一致），未选中不占空间 -->
    <Transition name="bulk-bar">
      <div v-if="selectedCaseIds.length" class="bulk-bar">
        <span class="bulk-count">已选 {{ selectedCaseIds.length }} 项</span>
        <el-button size="small" @click="onBatchMove">移动到分组</el-button>
        <el-button
          size="small"
          type="success"
          :disabled="batchRunning"
          :loading="batchRunning"
          @click="onBatchRun"
        >批量执行</el-button>
        <el-button size="small" :disabled="selectedCaseIds.length < 2" @click="openCombine">组合</el-button>
        <el-button size="small" text @click="clearAllTables()">取消选择</el-button>
      </div>
    </Transition>

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
          <span class="side-cnt">{{ row.isUngrouped ? casesOf(null).length : countCasesWithDescendants(row.groupId!) }}</span>
        </div>
        <div class="side-foot">
          <el-button size="small" @click="showGroupDialog = true">分组管理</el-button>
        </div>
      </aside>

      <div class="group-main">
        <!-- 页面级加载失败：内联错误块 + 重试（不用 toast 一闪而过） -->
        <div v-if="loadError" class="app-load-error">
          <el-icon><WarningFilled /></el-icon>
          <span>{{ loadError }}</span>
          <el-button size="small" @click="load">重试</el-button>
        </div>

        <EmptyState v-else-if="!loading && !list.length" description="暂无用例">
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
            @sort-change="onSortChange"
            @selection-change="(sel: any[]) => onSelectionChange('all', sel)"
          >
            <el-table-column type="selection" width="42" />
            <el-table-column prop="id" label="ID" width="70" sortable="custom" />
            <el-table-column prop="name" label="用例名称" min-width="180" show-overflow-tooltip sortable="custom">
              <template #default="{ row }">
                <el-tooltip v-if="hasEnabledSchedule(row.id)" content="已配置定时任务" placement="top">
                  <el-icon class="schedule-mark"><Timer /></el-icon>
                </el-tooltip>{{ row.name }}
              </template>
            </el-table-column>
            <el-table-column label="节点数" width="90">
              <template #default="{ row }">{{ row.dag_config?.nodes?.length || 0 }}</template>
            </el-table-column>
            <el-table-column prop="updated_at" label="更新时间" width="120" sortable="custom">
              <template #default="{ row }">
                <el-tooltip :content="formatTime(row.updated_at)" placement="top" popper-class="app-tip">
                  <span>{{ formatRelativeTime(row.updated_at) }}</span>
                </el-tooltip>
              </template>
            </el-table-column>
            <el-table-column label="创建人" width="100" align="center">
              <template #default="{ row }">{{ row.created_by_name || '—' }}</template>
            </el-table-column>
            <el-table-column label="更新人" width="100" align="center">
              <template #default="{ row }">{{ row.updated_by_name || '—' }}</template>
            </el-table-column>
            <el-table-column label="操作" width="240" fixed="right">
              <template #default="{ row }">
                <el-button link type="primary" size="small" @click="goDesign(row.id)">编排</el-button>
                <el-tooltip content="执行本行用例；勾选多行后按 Ctrl+Enter 从第一个勾选项开始执行" placement="top">
                  <el-button link type="success" size="small" @click="runCase(row)">执行</el-button>
                </el-tooltip>
                <el-tooltip :content="row.dataset_id ? '数据驱动：已绑定数据集，点击更换/解绑' : '绑定数据集启用数据驱动'" placement="top">
                  <el-button link :type="row.dataset_id ? 'warning' : 'primary'" size="small" @click="openBind(row)">数据</el-button>
                </el-tooltip>
                <!-- 低频操作收纳：报告/定时/复制/删除 -->
                <el-dropdown trigger="click" @command="(cmd: string) => onRowCommand(cmd, row)">
                  <el-button link type="primary" size="small">
                    更多<el-icon class="row-more-icon"><ArrowDown /></el-icon>
                  </el-button>
                  <template #dropdown>
                    <el-dropdown-menu>
                      <el-dropdown-item command="report">查看报告</el-dropdown-item>
                      <el-dropdown-item command="schedule">定时任务</el-dropdown-item>
                      <el-dropdown-item command="copy">复制用例</el-dropdown-item>
                      <el-dropdown-item command="remove" divided>删除用例</el-dropdown-item>
                    </el-dropdown-menu>
                  </template>
                </el-dropdown>
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
            v-if="selectedCases.length"
            :ref="(el: any) => setTableRef(selectedRow?.key, el)"
            :data="selectedPaged"
            size="small"
            stripe
            row-key="id"
            @sort-change="onSortChange"
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
            <el-table-column prop="id" label="ID" width="70" sortable="custom" />
            <el-table-column prop="name" label="用例名称" min-width="180" show-overflow-tooltip sortable="custom">
              <template #default="{ row }">
                <el-tooltip v-if="hasEnabledSchedule(row.id)" content="已配置定时任务" placement="top">
                  <el-icon class="schedule-mark"><Timer /></el-icon>
                </el-tooltip>{{ row.name }}
              </template>
            </el-table-column>
            <el-table-column label="节点数" width="90">
              <template #default="{ row }">{{ row.dag_config?.nodes?.length || 0 }}</template>
            </el-table-column>
            <el-table-column prop="updated_at" label="更新时间" width="120" sortable="custom">
              <template #default="{ row }">
                <el-tooltip :content="formatTime(row.updated_at)" placement="top" popper-class="app-tip">
                  <span>{{ formatRelativeTime(row.updated_at) }}</span>
                </el-tooltip>
              </template>
            </el-table-column>
            <el-table-column label="创建人" width="100" align="center">
              <template #default="{ row }">{{ row.created_by_name || '—' }}</template>
            </el-table-column>
            <el-table-column label="更新人" width="100" align="center">
              <template #default="{ row }">{{ row.updated_by_name || '—' }}</template>
            </el-table-column>
            <el-table-column label="操作" width="240" fixed="right">
              <template #default="{ row }">
                <el-button link type="primary" size="small" @click="goDesign(row.id)">编排</el-button>
                <el-tooltip content="执行本行用例；勾选多行后按 Ctrl+Enter 从第一个勾选项开始执行" placement="top">
                  <el-button link type="success" size="small" @click="runCase(row)">执行</el-button>
                </el-tooltip>
                <el-tooltip :content="row.dataset_id ? '数据驱动：已绑定数据集，点击更换/解绑' : '绑定数据集启用数据驱动'" placement="top">
                  <el-button link :type="row.dataset_id ? 'warning' : 'primary'" size="small" @click="openBind(row)">数据</el-button>
                </el-tooltip>
                <!-- 低频操作收纳：报告/定时/复制/删除 -->
                <el-dropdown trigger="click" @command="(cmd: string) => onRowCommand(cmd, row)">
                  <el-button link type="primary" size="small">
                    更多<el-icon class="row-more-icon"><ArrowDown /></el-icon>
                  </el-button>
                  <template #dropdown>
                    <el-dropdown-menu>
                      <el-dropdown-item command="report">查看报告</el-dropdown-item>
                      <el-dropdown-item command="schedule">定时任务</el-dropdown-item>
                      <el-dropdown-item command="copy">复制用例</el-dropdown-item>
                      <el-dropdown-item command="remove" divided>删除用例</el-dropdown-item>
                    </el-dropdown-menu>
                  </template>
                </el-dropdown>
              </template>
            </el-table-column>
          </el-table>
          <EmptyState v-else-if="!loading" :image-size="80" description="该分组暂无用例" />
          <div v-if="selectedCases.length" class="pagination-wrap">
            <el-pagination
              small
              background
              :current-page="pageMap[String(selectedRow!.key)] || 1"
              :page-size="pageSize"
              :total="selectedCases.length"
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
    <el-dialog v-model="dialogVisible" title="新建用例" width="420px" align-center :close-on-click-modal="false">
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

    <!-- 分组管理弹窗（多级：el-tree 拖拽调整层级与顺序；CRUD 与拖拽保存收敛在组件内） -->
    <GroupManageDialog
      v-model="showGroupDialog"
      title="用例分组管理"
      :tree-data="treeSelectData"
      :api="caseGroupApi"
      :project-id="store.currentProjectId"
      item-word="用例"
      @changed="onGroupsChanged"
    />

    <!-- 批量移动弹窗（目标选择与移动执行收敛在组件内，成功后自关） -->
    <BatchMoveDialog
      v-model="batchMoveVisible"
      :count="selectedCaseIds.length"
      :tree-data="treeSelectWithUngrouped"
      item-word="用例"
      :move="doBatchMove"
    />

    <!-- 批量执行配置弹窗：逐用例设置执行次数 + 并发数（配置 UI 收敛在组件，执行编排在父视图） -->
    <BatchRunDialog v-model="batchRunVisible" :items="batchRunItems" @confirm="confirmBatchRun" />

    <!-- 组合弹窗：拖拽调整拼接顺序，复制式生成新用例 -->
    <el-dialog v-model="combineVisible" title="组合用例" width="540px" align-center :close-on-click-modal="false">
      <div class="combine-tip">拖拽调整拼接顺序（自上而下依次执行）；组合将复制生成新用例，不影响原用例。前段提取的变量后段可直接引用。</div>
      <div ref="combineListRef" class="combine-list">
        <div v-for="c in combineItems" :key="c.id" class="combine-item">
          <el-tooltip content="拖拽排序" placement="top" popper-class="app-tip">
            <el-icon class="drag-handle"><Rank /></el-icon>
          </el-tooltip>
          <el-tooltip :content="c.name" placement="top" popper-class="app-tip">
            <span class="combine-name">{{ c.name }}</span>
          </el-tooltip>
          <span class="combine-nodes">{{ c.dag_config?.nodes?.length || 0 }} 节点</span>
        </div>
      </div>
      <el-form :model="combineForm" label-width="90px" style="margin-top: 14px">
        <el-form-item label="新用例名" required>
          <el-input v-model="combineForm.name" placeholder="如：冒烟全流程组合" maxlength="200" />
        </el-form-item>
        <el-form-item label="分组">
          <el-tree-select
            v-model="combineForm.group_id"
            :data="treeSelectData"
            node-key="id"
            :props="treeProps"
            placeholder="选择分组"
            clearable
            check-strictly
            style="width: 100%"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="combineVisible = false">取消</el-button>
        <el-button type="primary" :loading="combineLoading" @click="confirmCombine">组合生成</el-button>
      </template>
    </el-dialog>

    <!-- 定时任务弹窗（自治子系统：列表+表单+增删改启停/立即执行收敛在组件内） -->
    <ScheduleDialog
      v-model="scheduleVisible"
      :case-item="scheduleCase"
      :schedules="caseSchedules"
      :envs="store.environments"
      :default-env-id="store.currentEnvId"
      @changed="loadSchedules"
    />

    <!-- 绑定数据集（数据驱动） -->
    <el-dialog v-model="bindVisible" title="绑定数据集" width="480px">
      <div class="bind-tip">
        绑定后执行该用例时按数据行展开：N 行数据 = N 次执行，行值以
        <code v-pre>${列名}</code> 注入变量（优先于同名环境变量）。数据集按用例隔离，仅可选本用例名下的数据集
      </div>
      <el-select v-model="bindDatasetId" placeholder="选择数据集（空=不绑定）" clearable style="width: 100%">
        <el-option v-for="d in projectDatasets" :key="d.id" :label="`${d.name}（${d.rows?.length ?? 0} 行）`" :value="d.id" />
      </el-select>
      <div v-if="!projectDatasets.length" class="bind-empty">
        该用例暂无数据集（数据集为用例私有），
        <el-button link type="primary" @click="router.push('/datasets')">去创建</el-button>
      </div>
      <template #footer>
        <el-button @click="bindVisible = false">取消</el-button>
        <el-button type="primary" :loading="bindSaving" @click="saveBind">保存</el-button>
      </template>
    </el-dialog>

    <!-- 数据驱动执行确认面板（选行/换数据集/快照过期检测收敛在组件，执行编排在父视图） -->
    <DataDrivenRunDialog
      v-model="ddVisible"
      :case-item="ddCase"
      :datasets="projectDatasets"
      @confirm="confirmDataDrivenRun"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted, nextTick, toRef } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import Sortable from 'sortablejs'
import { Rank, Folder, CaretRight, Search, WarningFilled, Timer, ArrowDown } from '@element-plus/icons-vue'
import { caseApi, caseGroupApi, userApi, scheduleApi, datasetApi, type TestCase, type CaseGroup, type SimpleUser, type TestSchedule, type DataSet } from '@/api'
import { useAppStore } from '@/stores'
import { formatTime, formatRelativeTime, execStatusText, fileTimestamp } from '@/utils/format'
import { useGroupedTable, setGroupSwitchNotifier } from '@/composables/useGroupedTable'
import { useGroupMasterDetail } from '@/composables/useGroupMasterDetail'
import GroupManageDialog from '@/components/GroupManageDialog.vue'
import BatchMoveDialog from '@/components/BatchMoveDialog.vue'
import ScheduleDialog from '@/components/ScheduleDialog.vue'
import DataDrivenRunDialog from '@/components/DataDrivenRunDialog.vue'
import BatchRunDialog from '@/components/BatchRunDialog.vue'
import { useFaviconStatus } from '@/composables/useFaviconStatus'
import { useExecutionRunner } from '@/composables/useExecutionRunner'
import { debounce } from '@/utils/ui'
import { useClientSort } from '@/composables/useClientSort'
import EmptyState from '@/components/EmptyState.vue'

const favicon = useFaviconStatus()

const store = useAppStore()
const router = useRouter()

// 执行轮询统一走 useExecutionRunner（定时器注册/卸载清理/超时策略单点管理）
const runner = useExecutionRunner()
const list = ref<TestCase[]>([])
const loadError = ref('')
const groups = ref<CaseGroup[]>([])
const users = ref<SimpleUser[]>([])
const filterCreator = ref<number | null>(null)
const filterUpdater = ref<number | null>(null)
const loading = ref(false)
const keyword = ref('')

const filteredList = computed(() => {
  if (!keyword.value) return list.value
  // 搜索范围与 placeholder 一致：名称 / ID / 描述
  const kw = keyword.value.toLowerCase()
  const kwNum = Number(keyword.value)
  return list.value.filter(c =>
    c.name.toLowerCase().includes(kw) ||
    (!Number.isNaN(kwNum) && kw !== '' && c.id === kwNum) ||
    (c.description || '').toLowerCase().includes(kw),
  )
})

// 表头排序（sortable="custom"）：作用在过滤后的全量列表，分组/分页下游自然继承排序，
// 避免 el-table 默认前端排序只排当前页切片的假象；取消排序回到后端 sort_order（拖拽手序）
const { onSortChange, sorted: sortedList } = useClientSort(filteredList, {
  id: c => c.id,
  name: c => c.name,
  updated_at: c => c.updated_at ?? '',
}, (): void => tableSel.resetPages())

// 多级分组表格：树构建 + 展开记忆 + 分组过滤/计数/可见行/组内分页（样板已收敛进 composable）
const tableSel = useGroupedTable(groups, toRef(store, 'currentProjectId'), 'caseList', sortedList)
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
  pageSize,
  pageMap,
  onPageChange,
  onPageSizeChange,
  applyPageDragReorder,
  resetSelection,
  resetPages,
} = tableSel

// 搜索条件变化即回第 1 页，避免「第 3 页 + 结果不足一页」的空白死局
// 150ms 防抖：输入过程不逐键重算全量过滤链（对齐 DictManage/FileCenter 既有模式）
watch(keyword, debounce(() => resetPages(), 150))

// ===== 左分组导航选中态（master-detail 状态机收敛进 composable，与 ApiManage 共用）=====
const {
  selectedRowKey,
  selectedRow,
  hasChildGroups,
  onSideNodeClick,
  isSubtreeView,
  selectedItems: selectedCases,
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
  itemsOf: casesOf,
  filteredItems: sortedList,
  pageMap,
  pageSize,
  onRowDragEnd: onCaseRowDragEnd,
})

// el-tree / el-tree-select 公共字段映射
const treeProps = { label: 'label', children: 'children' }

const dialogVisible = ref(false)
// 分组管理弹窗与批量移动弹窗的开合态（交互收敛在组件内，见模板）
const showGroupDialog = ref(false)
const batchMoveVisible = ref(false)
// 批量执行配置弹窗状态（次数/并发配置在 BatchRunDialog 内；视图只持开合态与展示行快照）
const batchRunning = ref(false)
const batchRunVisible = ref(false)
// 弹窗内所选用例的展示行（打开时按勾选快照生成，避免执行中列表刷新干扰）
const batchRunItems = ref<{ id: number; name: string }[]>([])
const form = ref<{ name: string; group_id: number | null; description: string }>({ name: '', group_id: null, description: '' })

// ===== 批量移动：互斥勾选状态机在 useGroupedTable，表格实例/SortableJS 绑定在 useGroupMasterDetail =====
const selectedCaseIds = tableSel.selectedIds

async function onCaseRowDragEnd(groupId: string | number, oldIndex: number, newIndex: number) {
  try {
    const applied = await applyPageDragReorder(groupId, oldIndex, newIndex, (items) => caseApi.reorder(items))
    if (applied) ElMessage.success('已保存')
  } catch (e: any) {
    ElMessage.error(e.message || '排序保存失败')
    await load()
  }
}

function onSelectionChange(groupId: string | number, selection: TestCase[]) {
  tableSel.onSelectionChange(groupId, selection, clearOtherTables)
}

function onBatchMove() {
  if (selectedCaseIds.value.length === 0) return
  batchMoveVisible.value = true
}

/** 批量移动执行（BatchMoveDialog 确认时调用；成功 resolve 弹窗自关，失败 throw 由弹窗报错） */
async function doBatchMove(targetGroupId: number | null) {
  const res = await caseApi.batchMove(selectedCaseIds.value, targetGroupId)
  ElMessage.success(res.message)
  // 清空选中与 el-table 内部勾选态（reserve-selection 按 row-key 缓存，需主动 clearSelection）
  resetSelection(clearAllTables)
  await load()
}

// ===== 用例组合（复制式拼接，弹窗拖排序确定顺序）=====
const combineVisible = ref(false)
const combineItems = ref<TestCase[]>([])
const combineForm = ref<{ name: string; group_id: number | null }>({ name: '', group_id: null })
const combineLoading = ref(false)
const combineListRef = ref<HTMLElement | null>(null)
let combineSortable: Sortable | null = null

function openCombine() {
  const sel = selectedCaseIds.value
  if (sel.length < 2) return ElMessage.warning('组合至少需要勾选 2 个用例')
  // 按当前列表顺序排列（勾选顺序不稳定），弹窗内拖拽可再调整
  const selSet = new Set(sel)
  combineItems.value = list.value.filter(c => selSet.has(c.id))
  combineForm.value = { name: '', group_id: null }
  combineVisible.value = true
  nextTick(() => {
    if (combineSortable) { combineSortable.destroy(); combineSortable = null }
    if (combineListRef.value) {
      combineSortable = Sortable.create(combineListRef.value, {
        handle: '.drag-handle',
        animation: 200,
        ghostClass: 'sortable-ghost',
        onEnd: (evt: any) => {
          const { oldIndex, newIndex } = evt
          if (oldIndex == null || newIndex == null || oldIndex === newIndex) return
          const arr = combineItems.value
          const [moved] = arr.splice(oldIndex, 1)
          arr.splice(newIndex, 0, moved)
        },
      })
    }
  })
}

async function confirmCombine() {
  if (!combineForm.value.name?.trim()) return ElMessage.warning('请输入新用例名称')
  if (combineItems.value.length < 2) return ElMessage.warning('组合至少需要 2 个用例')
  combineLoading.value = true
  try {
    const created = await caseApi.combine(
      combineItems.value.map(c => c.id),
      combineForm.value.name.trim(),
      combineForm.value.group_id,
    )
    ElMessage.success(`已组合生成「${created.name}」（${created.dag_config?.nodes?.length || 0} 节点）`)
    combineVisible.value = false
    resetSelection(clearAllTables)
    await load()
    // 组合结果直接跳编排页检查
    router.push(`/cases/designer/${created.id}`)
  } catch (e: any) {
    ElMessage.error(e.message || '组合失败')
  } finally {
    combineLoading.value = false
  }
}

// ===== 列表导出（Excel 简表 / JSON 全量，筛选条件与列表页一致）=====
function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}

async function onExport(format: 'excel' | 'json') {
  if (!store.currentProjectId) return
  if (!filteredList.value.length) return ElMessage.warning('当前没有可导出的用例')
  try {
    const blob = await caseApi.exportList({
      project_id: store.currentProjectId,
      format,
      created_by: filterCreator.value ?? undefined,
      updated_by: filterUpdater.value ?? undefined,
    })
    const stamp = new Date().toISOString().replace(/[-:T]/g, '').slice(0, 14)
    downloadBlob(blob, `cases_${stamp}.${format === 'excel' ? 'xlsx' : 'json'}`)
    // 不报具体数量：keyword 是前端本地过滤、不参与后端导出，报数会与文件实际条数不符
    ElMessage.success(format === 'excel' ? '已导出 Excel 简表' : '已导出 JSON 全量')
  } catch (e: any) {
    ElMessage.error(e.message || '导出失败')
  }
}

// 分组过滤/计数/可见行/组内分页等样板已收敛至 useGroupedTable（见顶部解构）

async function load() {
  if (!store.currentProjectId) return
  loading.value = true
  loadError.value = ''
  try {
    list.value = await caseApi.list(store.currentProjectId, filterCreator.value ?? undefined, filterUpdater.value ?? undefined)
  } catch (e: any) {
    // 页面级失败：内联错误块 + 重试
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
  if (!store.currentProjectId) return
  groups.value = await caseGroupApi.list(store.currentProjectId)
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
  // 数据驱动：绑定数据集的用例先弹确认面板（N 行执行 N 次，可临时换数据集/选行）
  if (row.dataset_id) {
    await openDataDrivenRun(row)
    return
  }
  try {
    // 执行→进度消息→轮询→三态 favicon→结果提示（超时返回 running 态记录，同样跳报告页）
    const cur = await runner.runWithFeedback(row.id, store.currentEnvId, {
      runningMsg: `用例「${row.name}」执行中...`,
      maxPolls: 150,
    })
    router.push(`/reports/${cur.id}`)
  } catch (e: any) {
    favicon.reset()
    ElMessage.error(e.message || '轮询执行状态失败')
  }
}

// 批量执行入口：先弹配置窗（每个用例可设执行次数），确认后由 confirmBatchRun 提交
function onBatchRun() {
  if (!store.currentEnvId) return ElMessage.warning('请先在顶部选择环境')
  if (selectedCaseIds.value.length === 0) return ElMessage.warning('请先勾选用例')
  // 按当前勾选快照生成展示行；次数/并发配置与重置在 BatchRunDialog 内部
  batchRunItems.value = selectedCaseIds.value
    .map((id) => ({ id, name: list.value.find((c) => c.id === id)?.name || `用例#${id}` }))
  batchRunVisible.value = true
}

// 确认批量执行：按配置的并发数提交（1=串行），同环境共享登录 token，前端并发轮询各记录
async function confirmBatchRun({ caseIds, counts, concurrency }: { caseIds: number[]; counts: number[]; concurrency: number }) {
  if (batchRunning.value) return
  // 弹窗开着期间环境可能被清空，提交前再守卫一次（同时收窄类型）
  if (!store.currentEnvId) return ElMessage.warning('请先在顶部选择环境')
  // caseIds 与 counts 等长（BatchRunDialog 按展示行顺序给出），重建 case_id → 次数查表供轮次标注
  const countByCase = new Map(caseIds.map((id, i) => [id, counts[i] || 1]))
  const total = counts.reduce((a, b) => a + b, 0)
  batchRunVisible.value = false
  batchRunning.value = true
  favicon.running()
  const msg = ElMessage({
    message: `批量执行中（${caseIds.length} 个用例共 ${total} 轮，${concurrency === 1 ? '串行执行' : `并发 ${concurrency}`}）...`,
    type: 'info',
    duration: 0,
  })
  try {
    const records = await caseApi.batchExecute(caseIds, store.currentEnvId, counts, concurrency)
    // 并发轮询：各记录独立轮询，全部完成后汇总；同一用例多轮时标注轮次
    const seen: Record<number, number> = {}
    const results = await Promise.all(records.map(async (rec) => {
      const caseRow = list.value.find((c) => c.id === rec.case_id)
      const name = caseRow?.name || `用例#${rec.case_id}`
      seen[rec.case_id] = (seen[rec.case_id] || 0) + 1
      const multi = (countByCase.get(rec.case_id) || 1) > 1
      const label = multi ? `${name}（第 ${seen[rec.case_id]} 轮）` : name
      const status = await runner.pollUntilDone(rec.id)
      return { name: label, status: status.status, summary: status.summary }
    }))
    msg.close()
    const passed = results.filter((r) => r.status === 'success').length
    const failed = results.length - passed
    if (failed === 0) favicon.success()
    else favicon.failed()
    const detail = results.map((r) => {
      if (r.status === 'success') return `✓ ${r.name}：通过（${r.summary?.passed}/${r.summary?.total}）`
      if (r.status === 'failed') return `✗ ${r.name}：失败（${r.summary?.failed} 项未通过）`
      return `! ${r.name}：${execStatusText(r.status)}`
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

function goReport(row: TestCase) {
  router.push({ path: '/executions', query: { case_id: row.id } })
}

/** 行内「更多」下拉分发：低频操作收纳（见操作列注释） */
function onRowCommand(cmd: string, row: TestCase) {
  if (cmd === 'report') goReport(row)
  else if (cmd === 'schedule') openSchedule(row)
  else if (cmd === 'copy') onCopy(row)
  else if (cmd === 'remove') onRemove(row)
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
    await ElMessageBox.confirm(
      `确认删除用例「${row.name}」？其编排、绑定的数据集与定时任务将一并删除，此操作不可恢复`,
      '删除用例',
      { type: 'warning', confirmButtonText: '删除' },
    )
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

// ===== 定时任务（列表图标标识 + 弹窗数据源；弹窗自治子系统见 ScheduleDialog）=====
const schedules = ref<TestSchedule[]>([])
const scheduleVisible = ref(false)
const scheduleCase = ref<TestCase | null>(null)

// 当前弹窗用例的定时任务（父视图持有的单一数据源，弹窗 changed 后 loadSchedules 重载）
const caseSchedules = computed(() =>
  scheduleCase.value ? schedules.value.filter(s => s.case_id === scheduleCase.value!.id) : [],
)

// 用例名称列的图标标识：存在启用中的定时任务才显示
function hasEnabledSchedule(caseId: number): boolean {
  return schedules.value.some(s => s.case_id === caseId && s.enabled)
}

async function loadSchedules() {
  if (!store.currentProjectId) return
  try {
    schedules.value = await scheduleApi.list({ project_id: store.currentProjectId })
  } catch {
    schedules.value = []  // 定时列表失败不阻塞页面主体
  }
}

function openSchedule(row: TestCase) {
  scheduleCase.value = row
  scheduleVisible.value = true  // 有无配置决定列表/表单首屏，由弹窗组件打开时自判
}

// ============ 数据集绑定 + 数据驱动执行（周期 6/7） ============

const projectDatasets = ref<DataSet[]>([])
const bindVisible = ref(false)
const bindSaving = ref(false)
const bindCase = ref<TestCase | null>(null)
const bindDatasetId = ref<number | null>(null)

async function loadDatasets(caseId: number) {
  if (!store.currentProjectId) return
  try {
    projectDatasets.value = await datasetApi.list({
      project_id: store.currentProjectId, case_id: caseId, with_rows: true,
    })
  } catch {
    projectDatasets.value = []  // 数据集加载失败不阻塞列表主体
  }
}

async function openBind(row: TestCase) {
  bindCase.value = row
  bindDatasetId.value = row.dataset_id ?? null
  await loadDatasets(row.id)
  bindVisible.value = true
}

async function saveBind() {
  if (!bindCase.value) return
  bindSaving.value = true
  try {
    await caseApi.update(bindCase.value.id, { dataset_id: bindDatasetId.value ?? null })
    bindCase.value.dataset_id = bindDatasetId.value ?? null
    ElMessage.success(bindDatasetId.value ? '已绑定数据集' : '已解绑')
    bindVisible.value = false
  } catch (e: any) {
    ElMessage.error(e.message || '保存失败')
  } finally {
    bindSaving.value = false
  }
}

// ---------- 数据驱动执行确认面板（选行/换数据集/快照检测见 DataDrivenRunDialog） ----------
const ddVisible = ref(false)
const ddRunning = ref(false)
const ddCase = ref<TestCase | null>(null)

async function openDataDrivenRun(row: TestCase) {
  ddCase.value = row
  await loadDatasets(row.id)
  ddVisible.value = true
}

/** DataDrivenRunDialog 确认回调：后端按选行展开 N 条记录（失败聚合成一条通知），轮询首条代表整批 */
async function confirmDataDrivenRun({ datasetId, rowIds }: { datasetId: number | null; rowIds: number[] }) {
  if (!ddCase.value || !rowIds.length) return
  ddRunning.value = true
  favicon.running()
  const msg = ElMessage({
    message: `数据驱动执行中（${rowIds.length} 行并行）...`,
    type: 'info',
    duration: 0,
  })
  try {
    const first = await caseApi.execute(ddCase.value.id, store.currentEnvId!, {
      dataset_id: datasetId,
      row_ids: rowIds,
    })
    // 轮询首条记录（代表整批）；完成后去执行记录看全部
    const status = await runner.pollUntilDone(first.id)
    msg.close()
    if (status.status === 'success') {
      favicon.success()
      ElMessage.success(`数据驱动执行完成：首行通过（全部 ${rowIds.length} 条见执行记录）`)
    } else {
      favicon.failed()
      ElMessage.warning('数据驱动执行完成，存在失败行，详见执行记录')
    }
    router.push({ path: '/executions', query: { case_id: ddCase.value.id } })
  } catch (e: any) {
    msg.close()
    favicon.reset()
    ElMessage.error(e.message || '执行失败')
  } finally {
    ddRunning.value = false
  }
}

/** GroupManageDialog 变更回调：重载分组；删除时同步重载用例（其余变更不影响条目） */
async function onGroupsChanged(kind: 'add' | 'rename' | 'delete' | 'reorder') {
  await loadGroups()
  if (kind === 'delete') await load()
}

// 项目切换时：重置筛选并回第 1 页（统一行为，避免携带旧项目筛选）
watch(() => store.currentProjectId, () => {
  keyword.value = ''
  filterCreator.value = null
  filterUpdater.value = null
  resetPages()
  load()
  loadGroups()
  loadSchedules()
  projectDatasets.value = []  // 数据集按项目隔离，切换后按需重载
})
onMounted(() => {
  load()
  loadGroups()
  loadUsers()
  loadSchedules()
  window.addEventListener('keydown', onGlobalKey)
})
onUnmounted(() => {
  window.removeEventListener('keydown', onGlobalKey)
  // 执行轮询定时器由 useExecutionRunner 统一清理
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
/* 批量操作条（与接口管理一致） */
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
/* 分组管理弹窗样式已随 GroupManageDialog 组件迁移（原与 ApiManage 逐字重复） */
.pagination-wrap {
  display: flex;
  justify-content: flex-end;
  margin-top: 12px;
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
/* ===== 组合弹窗 ===== */
.combine-tip {
  font-size: 12px;
  color: var(--app-text-muted);
  margin-bottom: 10px;
  line-height: 1.5;
}
.combine-list {
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius-sm);
  max-height: 260px;
  overflow-y: auto;
}
.combine-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  border-bottom: 1px solid var(--app-border);
  background: var(--el-bg-color);
}
.combine-item:last-child {
  border-bottom: none;
}
.combine-item .drag-handle {
  cursor: grab;
  color: var(--app-text-muted);
  font-size: 16px;
  flex-shrink: 0;
}
.combine-item .drag-handle:active {
  cursor: grabbing;
}
.combine-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.combine-nodes {
  flex-shrink: 0;
  font-size: 12px;
  color: var(--app-text-muted);
}
/* ===== 定时任务：列表图标标识 + 弹窗 ===== */
.schedule-mark {
  color: var(--el-color-warning);
  margin-right: 4px;
  vertical-align: -2px;
}
/* 行内「更多」下拉触发按钮：与链接按钮同高，图标小箭头 */
.row-more-icon {
  font-size: 12px;
  margin-left: 1px;
}
/* 数据集绑定弹窗 */
.bind-tip {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  color: var(--el-text-color-secondary);
  font-size: 13px;
  margin-bottom: 12px;
  line-height: 1.6;
}
.bind-empty {
  margin-top: 10px;
  color: var(--el-text-color-secondary);
  font-size: 13px;
}
</style>
<!-- group-manage-dialog 全局样式已收敛至 style.css（原与 ApiManage 逐字符重复，两处漂移风险） -->

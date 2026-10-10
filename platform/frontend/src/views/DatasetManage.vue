<template>
  <div class="page">
    <div class="page-head">
      <div class="head-left">
        <span class="page-title">数据集</span>
      </div>
      <div class="head-right">
        <span class="head-tip">每个数据集是一套完整的节点入参取值，多数据集即多场景；入参在各节点 tab 内配置</span>
      </div>
    </div>

    <!-- 左用例分组树 + 右该用例数据集（用例维度，数据集互相隔离） -->
    <div v-loading="loading" class="group-layout">
      <aside class="group-side">
        <template v-for="row in sideRows" :key="row.kind === 'group' ? `g${row.id}` : `c${row.id}`">
          <!-- 分组节点：折叠/展开组内用例 -->
          <div
            v-if="row.kind === 'group'"
            class="side-node"
            :style="{ paddingLeft: 10 + row.depth * 14 + 'px' }"
            @click="toggleGroup(row.id)"
          >
            <el-icon v-if="groupHasContent(row.id)" class="expand-icon" :class="{ expanded: isExpanded(row.id) }"><CaretRight /></el-icon>
            <span v-else class="expand-spacer" />
            <el-tooltip :content="row.name" placement="top" popper-class="app-tip" :disabled="row.name.length <= 12">
              <span class="side-name">{{ row.name }}</span>
            </el-tooltip>
            <span class="side-cnt">{{ groupDatasetCount(row.id) }}</span>
          </div>
          <!-- 用例节点：选中查看其数据集 -->
          <div
            v-else
            class="side-node"
            :class="{ on: currentCase?.id === row.id }"
            :style="{ paddingLeft: 10 + row.depth * 14 + 'px' }"
            @click="selectCaseById(row.id)"
          >
            <span class="expand-spacer" />
            <el-icon class="case-icon"><Document /></el-icon>
            <el-tooltip :content="row.name" placement="top" popper-class="app-tip" :disabled="row.name.length <= 12">
              <span class="side-name">{{ row.name }}</span>
            </el-tooltip>
            <span class="side-cnt">{{ caseDatasetCount(row.id) }}</span>
          </div>
        </template>
        <EmptyState v-if="!loading && !cases.length" description="当前项目暂无用例" :image-size="60" />
      </aside>

      <div class="group-main">
        <div v-if="loadError" class="app-load-error">
          <el-icon><WarningFilled /></el-icon>
          <span>{{ loadError }}</span>
          <el-button size="small" @click="load">重试</el-button>
        </div>

        <EmptyState v-else-if="!loading && !currentCase" description="选择左侧用例查看其数据集" />

        <template v-else-if="currentCase">
          <!-- 该用例的数据集切换条 -->
          <div class="ds-bar">
            <div
              v-for="d in caseDatasets"
              :key="d.id"
              class="ds-chip"
              :class="{ on: current?.id === d.id }"
              @click="select(d)"
            >
              <el-icon class="ds-icon"><Grid /></el-icon>
              <span class="ds-name">{{ d.name }}</span>
              <span v-if="currentCase.dataset_id === d.id" class="ds-bound">使用中</span>
              <span class="ds-cnt">{{ nodeCount(d) }} 节点</span>
            </div>
            <el-button size="small" class="ds-add" :icon="Plus" @click="openCreate">新建数据集</el-button>
          </div>

          <EmptyState
            v-if="!caseDatasets.length"
            description="该用例暂无数据集（未绑定数据集的用例无法执行）。点「新建数据集」建立一套入参取值"
          />

          <template v-else-if="current">
            <div class="main-head">
              <span class="main-title">{{ current.name }}</span>
              <span class="group-count">{{ view?.nodes.length || 0 }} 节点 · {{ configuredCount }} 已配置</span>
              <div class="main-actions">
                <el-button size="small" @click="copyDataset">复制</el-button>
                <el-button size="small" @click="openEdit(current)">编辑信息</el-button>
                <el-button size="small" type="danger" link @click="remove(current)">删除</el-button>
              </div>
            </div>

            <!-- 悬空节点配置：画布节点已删但行内仍有其入参配置 -->
            <el-alert v-if="view?.orphan_node_ids.length" type="warning" :closable="false" class="orphan-alert">
              <template #title>
                {{ view.orphan_node_ids.length }} 个节点已从用例编排中删除，但本数据集仍保留其入参配置（不再被执行）
                <el-button size="small" type="warning" plain :loading="cleaningOrphans" @click="clearOrphans">清理悬空配置</el-button>
              </template>
            </el-alert>

            <div v-loading="viewLoading" class="params-area">
              <el-tabs v-if="view && view.nodes.length" v-model="activeNodeId" class="node-tabs" @tab-change="writeLast({})">
                <el-tab-pane
                  v-for="n in view.nodes"
                  :key="n.node_id"
                  :name="n.node_id"
                >
                  <template #label>
                    <span class="tab-label" :class="{ dirty: isDirty(n.node_id) }">
                      {{ n.label || n.node_id }}
                      <span v-if="isDirty(n.node_id)" class="tab-dot">●</span>
                    </span>
                  </template>

                  <!-- 只渲染当前激活节点：200+ 行参数表整棵 DOM 切走即销毁
                       （el-tabs 默认保留全部已访问面板，21 节点累积到 GB 级内存）；
                       编辑态存于 drafts（父级），切回无损重建 -->
                  <div v-if="activeNodeId === n.node_id && drafts[n.node_id]" class="node-panel">
                    <div class="node-meta">
                      <span v-if="n.api_name" class="meta-api">{{ n.api_name }}</span>
                      <span v-else class="meta-api none">未绑定接口（在用例编排中绑定，未绑定节点不执行）</span>
                    </div>

                    <div class="node-actions">
                      <el-button size="small" type="primary" :disabled="!isDirty(n.node_id)" :loading="savingNode" @click="saveNode(n.node_id)">
                        保存
                      </el-button>
                      <el-button size="small" :loading="savingNode" @click="resetNode(n.node_id)">放弃改动</el-button>
                      <el-button size="small" @click="openImport(n.node_id)">导入</el-button>
                      <span class="node-tip">保存即整体替换该节点的全部参数取值来源（含引用拓扑/悬空校验）</span>
                    </div>

                    <NodeParamsTable
                      :model-value="drafts[n.node_id].params"
                      :fields="(n.fields as any) || []"
                      :ref-groups="refGroupsFor(n.node_id)"
                      lock-body-add
                      @update:model-value="(v) => onDraftChange(n.node_id, v)"
                    />
                  </div>
                </el-tab-pane>
              </el-tabs>
              <EmptyState v-else-if="!viewLoading" description="用例编排中暂无节点，先去编排画布添加节点" :image-size="60" />

              <div class="pool-tip">
                入参支持<b>常量 / 函数 / 引用 / SQL</b> 四种来源；常量可为对象或数组，内嵌引用自动求值。
                <el-button text size="small" class="help-link" @click="store.openCoreCapability('expression')">查看参数来源说明</el-button>
              </div>
            </div>
          </template>
        </template>
      </div>
    </div>

    <!-- 新建/编辑数据集信息（名称/描述） -->
    <el-dialog v-model="dlgVisible" :title="dlgMode === 'create' ? '新建数据集' : '编辑数据集'" width="560px">
      <el-form label-width="80px">
        <el-form-item label="名称" required>
          <el-input v-model="form.name" placeholder="如：运单数据-场景A" maxlength="100" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="form.description" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dlgVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">{{ dlgMode === 'create' ? '创建' : '保存' }}</el-button>
      </template>
    </el-dialog>

    <!-- 导入请求体（JSON / 表单 / cURL 自动识别）：常量已配置字段替换，未配置字段初始化为常量入参，非常量不动，先进草稿 -->
    <ImportJsonDialog
      v-model:visible="importVisible"
      :body="drafts[importNodeId]?.params?.body || {}"
      @apply="onImportApply"
    />

    <!-- 契约同步（节点保存后）：本节点绑定接口的字段契约 ↔ 各数据集参数出入预览，许可后全量同步 -->
    <ContractSyncDialog
      v-model:visible="syncDlgVisible"
      :api-id="syncApiId"
      :api-name="syncApiName"
      @synced="onSynced"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { CaretRight, Document, Grid, Plus, WarningFilled } from '@element-plus/icons-vue'
import { datasetApi, caseApi, caseGroupApi, apiApi, type DataSet, type DatasetParamsView, type NodeParams, type ParamSpec, type TestCase, type CaseGroup } from '@/api'
import { useGroupTree, expandStorageKey, type GroupTreeNode } from '@/composables/useGroupTree'
import { buildRefGroups, type RefGraphCtx } from '@/composables/useRefGroups'
import { useAppStore } from '@/stores'
import EmptyState from '@/components/EmptyState.vue'
import ContractSyncDialog from '@/components/ContractSyncDialog.vue'
import ImportJsonDialog from '@/components/ImportJsonDialog.vue'
import NodeParamsTable from '@/components/NodeParamsTable.vue'
import type { RefVarGroup } from '@/components/VarRefSelect.vue'

const store = useAppStore()
const cases = ref<TestCase[]>([])
const groups = ref<CaseGroup[]>([])
const datasets = ref<DataSet[]>([])
const currentCase = ref<TestCase | null>(null)
const current = ref<DataSet | null>(null)
const loading = ref(false)
const loadError = ref('')
const saving = ref(false)

// ===== 参数视图（节点 tab 数据源）：行内现值 × 接口字段 × 静态产出 =====
const view = ref<DatasetParamsView | null>(null)
const viewLoading = ref(false)
const activeNodeId = ref('')
const savingNode = ref(false)
const cleaningOrphans = ref(false)

/** 每节点编辑草稿（params）；脏标记事件驱动（编辑事件置位，保存/放弃/重载复位）
 * ——避免 tab 标签对参数级对象做深比较 */
const drafts = reactive<Record<string, { params: NodeParams }>>({})
const dirtyMap = reactive<Record<string, boolean>>({})

const caseDatasets = computed(() => datasets.value.filter((d) => d.case_id === currentCase.value?.id))

/** 数据集已配置节点数（行内 nodes 键数） */
function nodeCount(d: DataSet): number {
  return Object.keys(d.rows?.[0]?.data?.nodes || {}).length
}

/** 当前视图内已配置（有 body/header 参数）的节点数 */
const configuredCount = computed(() =>
  (view.value?.nodes || []).filter((n) =>
    Object.keys(n.params?.body || {}).length || Object.keys(n.params?.headers || {}).length,
  ).length,
)

function isDirty(nid: string): boolean {
  return dirtyMap[nid] === true
}

/** 编辑事件：写入草稿并置脏（NodeParamsTable 换新对象 emit） */
function onDraftChange(nid: string, v: NodeParams) {
  if (!drafts[nid]) return
  drafts[nid].params = v
  dirtyMap[nid] = true
}

/** 由参数视图初始化全部节点草稿（并复位脏标记） */
function initDrafts() {
  for (const k of Object.keys(drafts)) delete drafts[k]
  for (const k of Object.keys(dirtyMap)) delete dirtyMap[k]
  for (const n of view.value?.nodes || []) {
    drafts[n.node_id] = {
      params: JSON.parse(JSON.stringify(n.params || {})),
    }
  }
}

/** 激活 tab 滚动进可视区：记忆的节点在长 tab 栏深处时，免每次手动点 > 翻页 */
function scrollActiveTabIntoView() {
  nextTick(() => {
    document
      .querySelector('.node-tabs .el-tabs__item.is-active')
      ?.scrollIntoView({ block: 'nearest', inline: 'center' })
  })
}

async function loadView(keepTab = false) {
  if (!current.value) { view.value = null; return }
  viewLoading.value = true
  try {
    const prev = activeNodeId.value
    view.value = await datasetApi.paramsView(current.value.id)
    initDrafts()
    if (!(keepTab && view.value.nodes.some((n) => n.node_id === prev))) {
      // 恢复上次访问的节点 tab（不在本视图内则回落首节点）
      const lastNode = readLast().nodeId
      activeNodeId.value = view.value.nodes.some((n) => n.node_id === lastNode)
        ? (lastNode || '') : (view.value.nodes[0]?.node_id || '')
      scrollActiveTabIntoView()
    }
    writeLast({})
  } catch (e: any) {
    ElMessage.error(e.message || '加载参数视图失败')
    view.value = null
  } finally {
    viewLoading.value = false
  }
}

/** 保存单节点入参（整体替换；服务端含引用拓扑/悬空/依赖环静态校验）。
 * 保存成功后检测节点绑定接口的契约出入（Q4 触发点之一）：有出入弹同步预览。 */
async function saveNode(nid: string) {
  if (!current.value || !drafts[nid]) return
  const node = view.value?.nodes.find((n) => n.node_id === nid)
  const apiId = node?.api_id || null
  const apiName = node?.api_name || ''
  savingNode.value = true
  try {
    await datasetApi.saveNodeConfig(current.value.id, {
      node_id: nid,
      params: drafts[nid].params,
    })
    ElMessage.success(`节点「${nodeLabelOf(nid)}」入参已保存`)
    await loadView(true)
    if (apiId) await checkContractImpact(apiId, apiName)
  } catch (e: any) {
    ElMessage.error({ message: e.message || '保存失败', duration: 6000 })
  } finally {
    savingNode.value = false
  }
}

// ===== 契约同步（接口字段 ↔ 数据集参数出入，2026-10-10 定案） =====
const syncDlgVisible = ref(false)
const syncApiId = ref<number | null>(null)
const syncApiName = ref('')

/** 查接口契约影响面：有出入才弹窗（无出入/查询失败都静默，不打扰保存主流程） */
async function checkContractImpact(apiId: number, apiName: string) {
  try {
    const impact = await apiApi.contractImpact(apiId)
    if (impact.length) {
      syncApiId.value = apiId
      syncApiName.value = apiName
      syncDlgVisible.value = true
    }
  } catch {
    /* 影响面查询失败不影响保存结果 */
  }
}

/** 同步完成：当前数据集可能被更新，重载参数视图 */
async function onSynced() {
  if (current.value) await loadView(true)
}

/** 放弃本节点改动：回到服务端快照 */
function resetNode(nid: string) {
  const n = view.value?.nodes.find((x) => x.node_id === nid)
  if (!n) return
  drafts[nid] = {
    params: JSON.parse(JSON.stringify(n.params || {})),
  }
  dirtyMap[nid] = false
}

// ===== 导入请求体（三格式自动识别）：解析/预览/应用收敛在 ImportJsonDialog（写回走草稿通道） =====
const importVisible = ref(false)
const importNodeId = ref('')

function openImport(nid: string) {
  importNodeId.value = nid
  importVisible.value = true
}

/** 应用导入结果：组件产出新 body，这里写入该节点草稿（onDraftChange 计脏） */
function onImportApply(body: Record<string, ParamSpec>, replaced: number, added: number) {
  const draft = drafts[importNodeId.value]
  if (!draft) return
  onDraftChange(importNodeId.value, { ...draft.params, body })
  ElMessage.success(`已替换 ${replaced} 个常量、新增 ${added} 个入参，点「保存本节点入参」生效`)
}

/** 清理悬空节点配置（画布已删节点的行内配置） */
async function clearOrphans() {
  if (!current.value || !view.value?.orphan_node_ids.length) return
  try {
    await ElMessageBox.confirm(
      `确认清理 ${view.value.orphan_node_ids.length} 个悬空节点的入参配置？此操作不可恢复。`,
      '清理悬空配置',
      { type: 'warning' },
    )
  } catch { return }
  cleaningOrphans.value = true
  try {
    for (const nid of view.value.orphan_node_ids) {
      await datasetApi.removeNodeConfig(current.value.id, nid)
    }
    ElMessage.success('已清理')
    await Promise.all([load(), loadView(true)])
  } catch (e: any) {
    ElMessage.error(e.message || '清理失败')
    await loadView(true)
  } finally {
    cleaningOrphans.value = false
  }
}

// ===== 引用选择器数据源：上游节点产出（BFS）∪ 本节点 SQL 参数 =====
function nodeLabelOf(nid: string): string {
  const n = view.value?.nodes.find((x) => x.node_id === nid)
  return n?.label || nid
}

/** 引用图数据源（构建口径收敛在 composables/useRefGroups） */
const refGraphCtx: RefGraphCtx = {
  orderedIds: () => (view.value?.nodes || []).map((n) => n.node_id),
  labelOf: nodeLabelOf,
  edges: () => view.value?.edges || [],
  productionsOf: (nid) => view.value?.nodes.find((x) => x.node_id === nid)?.productions || [],
  selfBodyOf: (nid) => drafts[nid]?.params?.body,
  selfLabel: '本节点参数值（前序参数可引用）',
}

/** 引用选择器数据源（computed 缓存）：上游节点产出（BFS）∪ 本节点 SQL 参数。
 * 函数式每渲染新数组会让全部行徽标重渲染（200 行表的卡顿源），此处只在
 * view/edges/drafts 变化时整体重算 */
const refGroupsMap = computed<Record<string, RefVarGroup[]>>(() => {
  const out: Record<string, RefVarGroup[]> = {}
  if (!view.value) return out
  for (const n of view.value.nodes) {
    out[n.node_id] = buildRefGroups(n.node_id, refGraphCtx)
  }
  return out
})

function refGroupsFor(nid: string): RefVarGroup[] {
  return refGroupsMap.value[nid] || []
}

// ===== 左侧用例分组树（沿用用例列表的分组结构） =====
const UNGROUPED_ID = -1
const {
  tree: groupTree,
  isExpanded,
  toggleExpand: toggleGroup,
  expandedIds,
} = useGroupTree(groups, computed(() => store.currentProjectId), 'datasetManage')

function casesOfGroup(gid: number | null) {
  return cases.value.filter((c) => (c.group_id ?? null) === gid)
}

/** 分组可展开：有子分组或组内直接有用例 */
function groupHasContent(id: number) {
  if (id === UNGROUPED_ID) return casesOfGroup(null).length > 0
  return groups.value.some((g) => g.parent_id === id) || casesOfGroup(id).length > 0
}

/** 分组节点计数：组内直接用例 + 全部子孙分组用例的数据集合计 */
function groupDatasetCount(id: number) {
  const sum = (gid: number | null) =>
    casesOfGroup(gid).reduce((n, c) => n + caseDatasetCount(c.id), 0)
  if (id === UNGROUPED_ID) return sum(null)
  const ids: number[] = [id]
  for (let i = 0; i < ids.length; i++) {
    for (const g of groups.value) {
      if (g.parent_id === ids[i] && !ids.includes(g.id)) ids.push(g.id)
    }
  }
  return ids.reduce((n, gid) => n + sum(gid), 0)
}

interface SideRow { kind: 'group' | 'case'; id: number; name: string; depth: number }

const sideRows = computed<SideRow[]>(() => {
  const out: SideRow[] = []
  const walk = (nodes: GroupTreeNode[], depth: number) => {
    for (const n of nodes) {
      out.push({ kind: 'group', id: n.id, name: n.label, depth })
      if (isExpanded(n.id)) {
        casesOfGroup(n.id).forEach((c) => out.push({ kind: 'case', id: c.id, name: c.name, depth: depth + 1 }))
        walk(n.children, depth + 1)
      }
    }
  }
  walk(groupTree.value, 0)
  out.push({ kind: 'group', id: UNGROUPED_ID, name: '未分组', depth: 0 })
  if (isExpanded(UNGROUPED_ID)) {
    casesOfGroup(null).forEach((c) => out.push({ kind: 'case', id: c.id, name: c.name, depth: 1 }))
  }
  return out
})

function selectCaseById(id: number) {
  const c = cases.value.find((x) => x.id === id)
  if (c) selectCase(c)
}

// ----- 上次访问记忆（按项目）：进入页面直接回到上次的数据集与节点 tab -----
const LAST_KEY = 'fin_dataset_last'
function readLast(): { caseId?: number; datasetId?: number; nodeId?: string } {
  try {
    const raw = JSON.parse(localStorage.getItem(LAST_KEY) || '{}')
    return raw?.projectId === store.currentProjectId ? raw : {}
  } catch { return {} }
}
function writeLast(patch: Record<string, unknown>) {
  try {
    localStorage.setItem(LAST_KEY, JSON.stringify({
      projectId: store.currentProjectId,
      caseId: currentCase.value?.id,
      datasetId: current.value?.id,
      nodeId: activeNodeId.value,
      ...patch,
    }))
  } catch { /* 存储失败忽略 */ }
}

function caseDatasetCount(caseId: number) {
  return datasets.value.filter((d) => d.case_id === caseId).length
}

async function load() {
  if (!store.currentProjectId) return
  loading.value = true
  loadError.value = ''
  try {
    const [cs, gs, ds] = await Promise.all([
      caseApi.list(store.currentProjectId),
      caseGroupApi.list(store.currentProjectId).catch(() => [] as CaseGroup[]),
      datasetApi.list({ project_id: store.currentProjectId, with_rows: true }),
    ])
    // 套件不参与数据集（成员各自绑定数据），左侧用例树不展示
    cases.value = cs.filter((c) => c.case_type !== 'suite')
    groups.value = gs
    datasets.value = ds
    // 展开记忆优先；首次（无记忆）默认全展开（含未分组虚拟节点）并落记忆
    if (localStorage.getItem(expandStorageKey('datasetManage', store.currentProjectId)) === null) {
      expandedIds.value = [...gs.map((g) => g.id), UNGROUPED_ID]
    }
    if (currentCase.value) {
      currentCase.value = cases.value.find((c) => c.id === currentCase.value!.id) || null
    }
    if (!currentCase.value && cases.value.length) {
      // 优先恢复上次访问的用例
      const last = readLast()
      currentCase.value = cases.value.find((c) => c.id === last.caseId) || cases.value[0]
    }
    if (current.value) {
      current.value = caseDatasets.value.find((d) => d.id === current.value!.id) || null
    }
    if (!current.value && caseDatasets.value.length) {
      // 优先恢复上次访问的数据集
      const last = readLast()
      current.value = caseDatasets.value.find((d) => d.id === last.datasetId) || caseDatasets.value[0]
    }
    await loadView()
  } catch (e: any) {
    loadError.value = e.message || '加载失败'
  } finally {
    loading.value = false
  }
}

function selectCase(c: TestCase) {
  currentCase.value = c
  const last = readLast()
  current.value = caseDatasets.value.find((d) => d.id === last.datasetId && d.case_id === c.id)
    || caseDatasets.value[0] || null
  loadView()
}

function select(d: DataSet) {
  current.value = d
  writeLast({})
  loadView()
}

// ---------- 数据集信息（名称/描述）新建/编辑 ----------
const dlgVisible = ref(false)
const dlgMode = ref<'create' | 'edit'>('edit')
const form = ref<{ name: string; description: string }>({ name: '', description: '' })

function openCreate() {
  if (!currentCase.value) return
  dlgMode.value = 'create'
  form.value = { name: '', description: '' }
  dlgVisible.value = true
}

function openEdit(d: DataSet) {
  dlgMode.value = 'edit'
  form.value = { name: d.name, description: d.description || '' }
  dlgVisible.value = true
}

async function save() {
  if (!form.value.name.trim()) return ElMessage.warning('请填写名称')
  saving.value = true
  try {
    if (dlgMode.value === 'create') {
      if (!store.currentProjectId || !currentCase.value) return
      const nd = await datasetApi.create({
        project_id: store.currentProjectId,
        case_id: currentCase.value.id,
        name: form.value.name,
        description: form.value.description,
      })
      ElMessage.success('已创建')
      dlgVisible.value = false
      await load()
      current.value = caseDatasets.value.find((d) => d.id === nd.id) || current.value
      await loadView()
    } else {
      if (!current.value) return
      await datasetApi.update(current.value.id, {
        name: form.value.name, description: form.value.description,
      })
      ElMessage.success('已保存')
      dlgVisible.value = false
      await load()
      current.value = caseDatasets.value.find((d) => d.id === current.value!.id) || current.value
    }
  } catch (e: any) {
    ElMessage.error(e.message || '保存失败')
  } finally {
    saving.value = false
  }
}

async function remove(d: DataSet) {
  try {
    await ElMessageBox.confirm(
      d.case_bound_count
        ? `数据集已被所属用例绑定，请先在用例管理解绑后再删除`
        : `确认删除数据集「${d.name}」及其全部节点入参配置？`,
      '删除数据集',
      { type: 'warning', showCancelButton: !d.case_bound_count, confirmButtonText: d.case_bound_count ? '知道了' : '删除' },
    )
  } catch {
    return
  }
  try {
    await datasetApi.remove(d.id)
    ElMessage.success('已删除')
    if (current.value?.id === d.id) current.value = null
    await load()
  } catch (e: any) {
    ElMessage.error(e.message || '删除失败')
  }
}

// ---------- 复制（多场景复用：换数据集执行 = 换全套入参） ----------
async function copyDataset() {
  if (!current.value) return
  try {
    const nd = await datasetApi.copy(current.value.id)
    ElMessage.success(`已复制为「${nd.name}」`)
    await load()
    current.value = caseDatasets.value.find((d) => d.id === nd.id) || current.value
    await loadView()
  } catch (e: any) {
    ElMessage.error(e.message || '复制失败')
  }
}

onMounted(load)
watch(() => store.currentProjectId, () => {
  currentCase.value = null
  current.value = null
  view.value = null
  load()
})
</script>

<style scoped>
.page {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--app-bg);
}
.head-tip {
  font-size: 12px;
  color: var(--app-text-muted);
}
/* 左用例列表 + 右该用例数据集（用例维度 master-detail） */
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
  color: var(--app-text-muted);
  font-size: 13px;
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
  white-space: nowrap;
}
.side-cnt {
  font-size: 11px;
  font-variant-numeric: tabular-nums;
  color: var(--app-text-faint);
}
.side-node.on .side-cnt {
  color: var(--app-primary);
}
.case-icon {
  font-size: 14px;
  color: var(--app-text-faint);
}
.side-node.on .case-icon {
  color: var(--app-primary);
}
.expand-icon {
  font-size: 14px;
  transition: transform 0.18s ease;
  color: var(--app-text-muted);
  cursor: pointer;
}
.expand-icon.expanded {
  transform: rotate(90deg);
}
.expand-spacer {
  width: 14px;
  flex-shrink: 0;
}
.group-main {
  flex: 1;
  min-width: 0;
  overflow: auto;
  padding: 16px 20px;
  display: flex;
  flex-direction: column;
}
/* 数据集切换条：吸顶（单行横向滚动，高度稳定供节点 tab sticky 对位） */
.ds-bar {
  position: sticky;
  top: 0;
  z-index: 6;
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: nowrap;
  overflow-x: auto;
  margin: 0 -20px;
  padding: 8px 20px;
  background: var(--app-bg);
}
.ds-bar .ds-chip,
.ds-bar .ds-add {
  flex-shrink: 0;
}
.ds-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 12px;
  border: 1px solid var(--app-border);
  border-radius: 14px;
  background: var(--app-card);
  cursor: pointer;
  max-width: 280px;
  font-size: 13px;
  color: var(--app-text-muted);
}
.ds-chip:hover {
  border-color: var(--app-primary);
}
.ds-chip.on {
  border-color: var(--app-primary);
  color: var(--app-primary);
  background: var(--app-active);
}
.ds-icon {
  font-size: 13px;
}
.ds-name {
  max-width: 180px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.ds-bound {
  font-size: 11px;
  padding: 0 6px;
  border-radius: 8px;
  background: var(--app-active);
  color: var(--app-primary);
}
.ds-chip.on .ds-bound {
  background: var(--app-primary);
  color: #fff;
}
.ds-cnt {
  font-size: 11px;
  color: var(--app-text-faint);
}
.ds-chip.on .ds-cnt {
  color: var(--app-primary);
}
.ds-add {
  border-style: dashed;
}
.main-head {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 12px; /* ds-bar 吸顶后由此留出间隔 */
  margin-bottom: 10px;
}
.main-title {
  font-size: 15px;
  font-weight: 600;
}
.group-count {
  font-size: 12px;
  color: var(--app-text-faint);
}
.main-actions {
  margin-left: auto;
  display: flex;
  gap: 4px;
}
.orphan-alert {
  margin-bottom: 10px;
}
.orphan-alert :deep(.el-alert__title) {
  display: flex;
  align-items: center;
  gap: 10px;
}
.params-area {
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-height: 200px;
}
/* 节点 tabs：header 吸顶在数据集条之下（ds-bar 单行 8+31+8≈47px） */
.node-tabs :deep(.el-tabs__header) {
  position: sticky;
  top: 47px;
  z-index: 5;
  margin: 0 -20px;
  padding: 0 20px;
  background: var(--app-bg);
}
.tab-label {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.tab-label.dirty {
  color: var(--el-color-warning);
}
.tab-dot {
  font-size: 10px;
}
.node-panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding-top: 12px;
}
.node-meta {
  display: flex;
  align-items: center;
  gap: 10px;
}
.meta-api {
  font-size: 12px;
  font-family: var(--app-font-mono, monospace);
  color: var(--app-text-muted);
  background: var(--app-hover);
  padding: 2px 8px;
  border-radius: 4px;
}
.meta-api.none {
  color: var(--el-color-warning);
  background: var(--el-color-warning-light-9, #fdf6ec);
}
.node-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  padding-bottom: 4px;
  border-bottom: 1px dashed var(--app-border);
}
.node-tip {
  font-size: 12px;
  color: var(--app-text-faint);
}
.pool-tip {
  font-size: 12px;
  color: var(--app-text-muted);
  line-height: 1.8;
}
.help-link {
  padding: 0 4px;
}
</style>

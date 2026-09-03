<template>
  <div class="page">
    <div class="page-head">
      <div class="head-left">
        <span class="page-title">数据集</span>
        <el-button type="primary" :disabled="!currentCase" @click="openCreate">+ 新建数据集</el-button>
        <el-upload :show-file-list="false" accept=".xlsx,.csv" :auto-upload="false" :disabled="!current" :on-change="onImportFile">
          <el-button :disabled="!current">Excel/CSV 导入</el-button>
        </el-upload>
        <el-button @click="openGenerate">从用例生成</el-button>
        <el-button :disabled="!current" @click="openMerge">从其他数据集覆盖…</el-button>
        <el-button :disabled="!current" @click="exportRows">导出 Excel</el-button>
      </div>
      <div class="head-right">
        <span class="head-tip">数据集按用例隔离 · 每行数据 = 一次执行 · 复用靠复制 · 列中文名实时引用字段字典</span>
      </div>
    </div>

    <!-- 左用例分组树 + 右该用例数据集（用例维度，数据集互相隔离） -->
    <div v-loading="loading" class="group-layout">
      <aside class="group-side">
        <template v-for="row in sideRows" :key="row.kind === 'group' ? `g${row.id}` : `c${row.id}`">
          <!-- 分组节点：折叠/展开组内用例 -->
          <div
            v-if="row.kind === 'group'"
            class="side-node group-row"
            :style="{ paddingLeft: 8 + row.depth * 14 + 'px' }"
            @click="toggleGroup(row.id)"
          >
            <el-icon v-if="groupHasContent(row.id)" class="expand-icon" :class="{ expanded: isExpanded(row.id) }"><CaretRight /></el-icon>
            <span v-else class="expand-spacer" />
            <el-icon class="group-icon"><Folder /></el-icon>
            <span class="side-name">{{ row.name }}</span>
            <span class="side-cnt">{{ groupDatasetCount(row.id) }} 集</span>
          </div>
          <!-- 用例节点：选中查看其数据集 -->
          <div
            v-else
            class="side-node"
            :class="{ on: currentCase?.id === row.id }"
            :style="{ paddingLeft: 8 + row.depth * 14 + 'px' }"
            @click="selectCaseById(row.id)"
          >
            <span class="expand-spacer" />
            <el-icon class="case-icon"><Document /></el-icon>
            <span class="side-name">{{ row.name }}</span>
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
              <span class="ds-cnt">{{ d.rows?.length ?? 0 }} 行</span>
            </div>
            <el-button size="small" @click="openCreate">+ 新建</el-button>
          </div>

          <EmptyState
            v-if="!caseDatasets.length"
            description="该用例暂无数据集（数据集为用例私有，跨用例复用请复制）"
          >
            <el-button type="primary" @click="openGenerate">从用例生成</el-button>
            <el-button @click="openCreate">+ 新建数据集</el-button>
          </EmptyState>

          <template v-else-if="current">
            <div class="main-head">
              <span class="main-title">{{ current.name }}</span>
              <span class="group-count">{{ current.rows?.length ?? 0 }}</span>
              <span class="main-sub" :title="colKeys.join('、')">列：{{ colLabels.join('、') || '（未定义）' }}</span>
              <div class="main-actions">
                <el-button size="small" @click="copyDataset">复制</el-button>
                <el-button size="small" @click="openEdit(current)">编辑列定义</el-button>
                <el-button size="small" type="danger" link @click="remove(current)">删除</el-button>
              </div>
            </div>

            <el-table :data="current.rows" stripe size="small" row-key="id" max-height="480">
              <template #empty>
                <EmptyState description="暂无数据行，下方添加或导入" :image-size="60" />
              </template>
              <el-table-column prop="row_index" label="#" width="50" />
              <el-table-column
                v-for="col in current.columns"
                :key="col.key"
                :label="colLabel(col.key)"
                min-width="140"
                show-overflow-tooltip
              >
                <template #header>
                  <span>{{ colLabel(col.key) }}</span>
                  <span v-if="!dictLabel(col.key)" class="col-key-raw">{{ col.key }}</span>
                </template>
                <template #default="{ row }">{{ fmtCell(row.data?.[col.key]) }}</template>
              </el-table-column>
              <el-table-column label="操作" width="180" fixed="right">
                <template #default="{ row }">
                  <el-button link size="small" @click="startEditRow(row)">编辑</el-button>
                  <el-button link size="small" @click="copyRow(row)">复制</el-button>
                  <el-button link size="small" type="danger" @click="removeRow(row)">删除</el-button>
                </template>
              </el-table-column>
            </el-table>

            <div class="row-ops">
              <el-button size="small" @click="addRow">+ 添加一行</el-button>
              <el-button size="small" type="danger" plain @click="clearRows">清空全部行</el-button>
              <span class="tip">列名与请求参数同名即自动覆盖；嵌套字段或跨字段引用可用 <code v-pre>${列名}</code></span>
            </div>

            <!-- 节点配置快照（只读 + 手动重新同步） -->
            <el-collapse class="snap-panel">
              <el-collapse-item>
                <template #title>
                  <span class="snap-title">节点配置快照（{{ current.node_configs?.length || 0 }} 个节点）</span>
                  <span class="snap-tip">只读 · 执行时整块覆盖该节点配置</span>
                </template>
                <div class="snap-actions">
                  <el-button size="small" :loading="resyncing" @click="resyncDataset">重新同步（取用例当前编排）</el-button>
                  <span class="tip">仅刷新快照，列 / 行数据不动；用例编排变更后需手动同步</span>
                </div>
                <EmptyState
                  v-if="!current.node_configs?.length"
                  description="暂无快照（生成时未捕获到节点配置，或已过期清空）"
                  :image-size="60"
                />
                <el-table v-else :data="current.node_configs" size="small">
                  <el-table-column prop="node_id" label="节点" width="130" />
                  <el-table-column prop="api_id" label="API" width="80">
                    <template #default="{ row }">{{ row.api_id ?? '—' }}</template>
                  </el-table-column>
                  <el-table-column label="前置处理" width="90">
                    <template #default="{ row }">{{ row.pre_process?.length || 0 }} 条</template>
                  </el-table-column>
                  <el-table-column label="后置提取" width="90">
                    <template #default="{ row }">{{ row.post_extract?.length || 0 }} 条</template>
                  </el-table-column>
                  <el-table-column label="断言规则" width="90">
                    <template #default="{ row }">{{ row.assertions?.length || 0 }} 条</template>
                  </el-table-column>
                  <el-table-column label="执行后等待" width="100">
                    <template #default="{ row }">{{ row.wait_after_ms || 0 }} ms</template>
                  </el-table-column>
                  <el-table-column label="明细" min-width="60">
                    <template #default="{ row }">
                      <el-button link size="small" type="primary" @click="viewSnapshot(row)">查看 JSON</el-button>
                    </template>
                  </el-table-column>
                </el-table>
              </el-collapse-item>
            </el-collapse>
          </template>
        </template>
      </div>
    </div>

    <!-- 新建/编辑数据集（列定义，中文名实时引用字典） -->
    <el-dialog v-model="dlgVisible" :title="editingId ? '编辑数据集' : `新建数据集（${currentCase?.name || ''}）`" width="640px">
      <el-form label-width="80px">
        <el-form-item label="名称" required>
          <el-input v-model="form.name" placeholder="如：运单数据" maxlength="100" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="form.description" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="列定义">
          <div class="cols-editor">
            <div class="col-list">
              <div v-for="(col, i) in form.columns" :key="i" class="col-row">
                <el-input v-model="col.key" placeholder="key（变量名）" style="width: 220px" />
                <span class="col-dict" :title="dictLabel(col.key) ? '来自字段字典' : '字典缺失，列头将显示 key'">
                  {{ dictLabel(col.key) || '（字典缺失 → 显 key）' }}
                </span>
                <el-select v-model="col.type" style="width: 110px">
                  <el-option v-for="t in colTypes" :key="t" :label="t" :value="t" />
                </el-select>
                <el-button link type="danger" @click="form.columns.splice(i, 1)">删除</el-button>
              </div>
            </div>
            <el-button size="small" @click="form.columns.push({ key: '', type: 'string' })">+ 添加列</el-button>
            <div class="tip">key 仅允许字母/数字/下划线且不以数字开头；列中文名在「字典管理」维护，此处实时引用</div>
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dlgVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>

    <!-- 从用例生成：写死请求参数 + 节点配置快照成数据集 -->
    <el-dialog v-model="genVisible" title="从用例生成数据集" width="560px">
      <el-alert
        type="info"
        :closable="false"
        style="margin-bottom: 12px"
        title="扫描用例全部节点的写死请求参数（非 ${} 提取注入），每个参数一列并带 1 行原值快照；同时按节点快照当前前置/后置提取/断言配置；同名参数跨节点取值不同时跳过该列"
      />
      <el-form label-width="80px">
        <el-form-item label="选择用例" required>
          <el-select v-model="genCaseId" filterable placeholder="选择用例" style="width: 100%"
                     :popper-options="{ strategy: 'fixed' }">
            <el-option v-for="c in genCases" :key="c.id" :label="c.name" :value="c.id">
              <el-tooltip :content="c.name" placement="top" :disabled="c.name.length <= 30">
                <span class="gen-case-option">{{ c.name }}</span>
              </el-tooltip>
            </el-option>
          </el-select>
        </el-form-item>
        <el-form-item label="名称">
          <el-input v-model="genName" placeholder="默认：用例名-参数集" maxlength="100" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="genVisible = false">取消</el-button>
        <el-button type="primary" :loading="genSaving" @click="confirmGenerate">生成</el-button>
      </template>
    </el-dialog>

    <!-- 快照明细（只读 JSON） -->
    <el-dialog v-model="snapVisible" :title="`节点 ${snapViewing?.node_id || ''} 配置快照（只读）`" width="640px">
      <pre class="snap-json">{{ snapJson }}</pre>
      <template #footer>
        <el-button @click="snapVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <!-- 导入预览确认 -->
    <el-dialog v-model="previewVisible" title="导入预览" width="720px">
      <el-alert
        v-for="(w, i) in previewWarnings"
        :key="i"
        :title="w"
        type="warning"
        :closable="false"
        style="margin-bottom: 8px"
      />
      <div class="preview-tip">共解析 {{ previewRows.length }} 行，确认后将<b>替换现有全部行</b></div>
      <el-table :data="previewRows" stripe size="small" max-height="360">
        <el-table-column type="index" label="#" width="50" />
        <el-table-column
          v-for="col in previewCols"
          :key="col"
          :prop="col"
          :label="colLabel(col)"
          min-width="130"
          show-overflow-tooltip
        >
          <template #default="{ row }">{{ fmtCell(row[col]) }}</template>
        </el-table-column>
      </el-table>
      <template #footer>
        <el-button @click="previewVisible = false">取消</el-button>
        <el-button type="primary" :loading="importing" @click="confirmImport">确认导入</el-button>
      </template>
    </el-dialog>

    <!-- 行编辑抽屉：字段纵向排列 + 搜索定位，替代横向滚动表格内编辑 -->
    <el-drawer v-model="drawerVisible" size="640px" :close-on-click-modal="false">
      <template #header>
        <span>编辑第 {{ editingRowIndex }} 行数据</span>
      </template>
      <div class="drawer-body">
        <el-input
          v-model="fieldSearch"
          placeholder="搜索字段（中文名 / key）"
          clearable
          class="field-search"
        />
        <div class="field-count">
          {{ filteredFields.length }} / {{ current?.columns?.length || 0 }} 个字段{{ fieldSearch ? '（已过滤）' : '' }}
        </div>
        <el-scrollbar class="field-scroll">
          <el-form label-position="top" size="small" @submit.prevent>
            <el-form-item v-for="col in filteredFields" :key="col.key">
              <template #label>
                <span>{{ colLabel(col.key) }}</span>
                <span v-if="!dictLabel(col.key)" class="col-key-raw">{{ col.key }}</span>
                <span class="col-type-tag">{{ col.type }}</span>
              </template>
              <el-input
                v-model="editingRowData[col.key]"
                :type="isJsonText(editingRowData[col.key]) ? 'textarea' : 'text'"
                :autosize="{ minRows: 1, maxRows: 20 }"
              />
              <div v-if="jsonError(col.key)" class="json-err">{{ jsonError(col.key) }}</div>
            </el-form-item>
          </el-form>
        </el-scrollbar>
      </div>
      <template #footer>
        <el-button @click="cancelEditRow">取消</el-button>
        <el-button type="primary" :loading="rowSaving" @click="saveRow">保存</el-button>
      </template>
    </el-drawer>

    <!-- 从其他数据集覆盖（节点级对比合并） -->
    <el-dialog v-model="mergeVisible" title="从其他数据集覆盖" width="720px" :close-on-click-modal="false">
      <el-form label-width="90px" size="small">
        <el-form-item label="源数据集">
          <el-select
            v-model="mergeSourceId"
            placeholder="选择同项目其他数据集"
            style="width: 100%"
            filterable
            fit-input-width
            @change="doMergePreview"
          >
            <el-option
              v-for="d in mergeCandidates"
              :key="d.id"
              :value="d.id"
              :label="`${d.name}（${caseName(d.case_id)}，${d.rows?.length ?? 0} 行）`"
            />
          </el-select>
        </el-form-item>
      </el-form>

      <div v-if="mergeLoading" v-loading="true" style="min-height: 120px" />

      <template v-else-if="mergePreviewData">
        <el-alert
          v-if="!mergePreviewData.common_nodes.length"
          type="info"
          :closable="false"
          title="两个数据集没有相同节点（相同接口），没有覆盖的必要"
        />
        <template v-else>
          <el-form label-width="90px" size="small">
            <el-form-item label="用源哪一行">
              <el-select v-model="mergeRowIdx" style="width: 200px" filterable fit-input-width>
                <el-option
                  v-for="(lbl, i) in mergePreviewData.source.row_labels"
                  :key="i"
                  :value="i + 1"
                  :label="`第 ${lbl} 行`"
                />
              </el-select>
              <span class="merge-hint">该行的值将覆盖下方勾选节点涉及的列（当前数据集全部行）</span>
            </el-form-item>
          </el-form>
          <el-table
            ref="mergeTableRef"
            :data="mergePreviewData.common_nodes"
            size="small"
            @selection-change="(rows: any[]) => (mergeSelectedApis = rows.map((r) => r.api_id))"
          >
            <el-table-column type="selection" width="40" />
            <el-table-column prop="api_name" label="相同节点（接口）" min-width="140" />
            <el-table-column label="涉及列" min-width="300">
              <template #default="{ row }">
                <span class="merge-cols" :title="row.columns.join('、')">{{ row.columns.join('、') }}</span>
              </template>
            </el-table-column>
          </el-table>
          <div class="merge-hint" style="margin-top: 8px">
            已选 {{ mergeSelectedApis.length }} 个节点 · 源「{{ mergePreviewData.source.name }}」共
            {{ mergePreviewData.source.rows }} 行 · 目标独有列保持不变 · 源行空值不覆盖
          </div>
        </template>
      </template>

      <template #footer>
        <el-button @click="mergeVisible = false">取消</el-button>
        <el-button
          type="primary"
          :disabled="!mergePreviewData || !mergePreviewData.common_nodes.length || !mergeSelectedApis.length"
          :loading="merging"
          @click="confirmMerge"
        >
          覆盖合并
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { CaretRight, Document, Folder, Grid, WarningFilled } from '@element-plus/icons-vue'
import { datasetApi, caseApi, caseGroupApi, type DataSet, type DataSetColumn, type DataSetNodeConfig, type TestCase, type CaseGroup } from '@/api'
import { buildGroupTree, type GroupTreeNode } from '@/composables/useGroupTree'
import { useAppStore } from '@/stores'
import EmptyState from '@/components/EmptyState.vue'

const store = useAppStore()
const cases = ref<TestCase[]>([])
const groups = ref<CaseGroup[]>([])
const datasets = ref<DataSet[]>([])
const currentCase = ref<TestCase | null>(null)
const current = ref<DataSet | null>(null)
const loading = ref(false)
const loadError = ref('')
const saving = ref(false)
const resyncing = ref(false)

const colTypes = ['string', 'int', 'bool', 'array', 'object']
const caseDatasets = computed(() => datasets.value.filter((d) => d.case_id === currentCase.value?.id))
const colKeys = computed(() => (current.value?.columns || []).map((c) => c.key))
const colLabels = computed(() => colKeys.value.map((k) => colLabel(k)))

// ===== 左侧用例分组树（沿用用例列表的分组结构）=====
const UNGROUPED_ID = -1
const groupTree = computed(() => buildGroupTree(groups.value))
// 展开记忆：按项目持久化（与 CaseList 的 fin_group_expand_{scope}_{projectId} 同约定，scope 独立）
const EXPAND_SCOPE = 'datasetManage'
const expandedGroupIds = ref(new Set<number>())
let hasExpandMemory = false

function expandStorageKey() {
  return `fin_group_expand_${EXPAND_SCOPE}_${store.currentProjectId ?? 0}`
}

function loadExpandMemory() {
  if (!store.currentProjectId) {
    expandedGroupIds.value = new Set()
    hasExpandMemory = false
    return
  }
  try {
    const saved = localStorage.getItem(expandStorageKey())
    if (saved !== null) {
      expandedGroupIds.value = new Set(JSON.parse(saved))
      hasExpandMemory = true
    } else {
      hasExpandMemory = false
    }
  } catch {
    hasExpandMemory = false
  }
}

function saveExpandMemory() {
  if (!store.currentProjectId) return
  try {
    localStorage.setItem(expandStorageKey(), JSON.stringify([...expandedGroupIds.value]))
  } catch {
    // 忽略写入失败
  }
}

function isExpanded(id: number) {
  return expandedGroupIds.value.has(id)
}

function toggleGroup(id: number) {
  const s = new Set(expandedGroupIds.value)
  if (s.has(id)) s.delete(id)
  else s.add(id)
  expandedGroupIds.value = s
  saveExpandMemory()
}

function casesOfGroup(gid: number | null) {
  return cases.value.filter((c) => (c.group_id ?? null) === gid)
}

/** 分组可展开：有子分组或组内直接有用例（叶子分组折叠用例列表） */
function groupHasContent(id: number) {
  if (id === UNGROUPED_ID) return casesOfGroup(null).length > 0
  return groups.value.some((g) => g.parent_id === id) || casesOfGroup(id).length > 0
}

/** 分组节点计数：组内直接用例的数据集合计（不含子组，避免与子组重复） */
function groupDatasetCount(id: number) {
  return casesOfGroup(id === UNGROUPED_ID ? null : id).reduce((n, c) => n + caseDatasetCount(c.id), 0)
}

interface SideRow { kind: 'group' | 'case'; id: number; name: string; depth: number }

const sideRows = computed<SideRow[]>(() => {
  const rows: SideRow[] = []
  const walk = (nodes: GroupTreeNode[], depth: number) => {
    for (const n of nodes) {
      rows.push({ kind: 'group', id: n.id, name: n.label, depth })
      if (isExpanded(n.id)) {
        casesOfGroup(n.id).forEach((c) => rows.push({ kind: 'case', id: c.id, name: c.name, depth: depth + 1 }))
        walk(n.children, depth + 1)
      }
    }
  }
  walk(groupTree.value, 0)
  rows.push({ kind: 'group', id: UNGROUPED_ID, name: '未分组', depth: 0 })
  if (isExpanded(UNGROUPED_ID)) {
    casesOfGroup(null).forEach((c) => rows.push({ kind: 'case', id: c.id, name: c.name, depth: 1 }))
  }
  return rows
})

function selectCaseById(id: number) {
  const c = cases.value.find((x) => x.id === id)
  if (c) selectCase(c)
}

// 列中文名实时引用项目字段字典，缺失显 key
function dictLabel(key: string) {
  return store.fieldDictMap?.[key] || ''
}
function colLabel(key: string) {
  return dictLabel(key) || key
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
    cases.value = cs
    groups.value = gs
    datasets.value = ds
    // 展开记忆优先；首次（无记忆）默认全展开并落记忆
    loadExpandMemory()
    if (!hasExpandMemory) {
      const s = new Set<number>()
      gs.forEach((g) => s.add(g.id))
      s.add(UNGROUPED_ID)
      expandedGroupIds.value = s
      saveExpandMemory()
    }
    if (currentCase.value) {
      currentCase.value = cases.value.find((c) => c.id === currentCase.value!.id) || null
    }
    if (!currentCase.value && cases.value.length) currentCase.value = cases.value[0]
    if (current.value) {
      current.value = caseDatasets.value.find((d) => d.id === current.value!.id) || null
    }
    if (!current.value && caseDatasets.value.length) current.value = caseDatasets.value[0]
  } catch (e: any) {
    loadError.value = e?.response?.data?.detail || '加载失败'
  } finally {
    loading.value = false
  }
}

function selectCase(c: TestCase) {
  cancelEditRow()
  currentCase.value = c
  current.value = caseDatasets.value[0] || null
}

function select(d: DataSet) {
  cancelEditRow()
  current.value = d
}

// ---------- 数据集（列定义）新建/编辑 ----------
const dlgVisible = ref(false)
const editingId = ref<number | null>(null)
const form = ref<{ name: string; description: string; columns: DataSetColumn[] }>({
  name: '', description: '', columns: [{ key: '', type: 'string' }],
})

function openCreate() {
  if (!currentCase.value) return ElMessage.warning('请先选择左侧用例（数据集按用例隔离）')
  editingId.value = null
  form.value = { name: '', description: '', columns: [{ key: '', type: 'string' }] }
  dlgVisible.value = true
}

function openEdit(d: DataSet) {
  editingId.value = d.id
  form.value = {
    name: d.name,
    description: d.description || '',
    columns: (d.columns || []).map((c) => ({ ...c })),
  }
  dlgVisible.value = true
}

async function save() {
  if (!form.value.name.trim()) return ElMessage.warning('请填写名称')
  const cols = form.value.columns.filter((c) => c.key.trim())
  if (!cols.length) return ElMessage.warning('至少需要一列')
  saving.value = true
  try {
    if (editingId.value) {
      await datasetApi.update(editingId.value, {
        name: form.value.name, description: form.value.description, columns: cols,
      })
    } else {
      await datasetApi.create({
        project_id: store.currentProjectId!, case_id: currentCase.value!.id, name: form.value.name,
        description: form.value.description, columns: cols,
      })
    }
    ElMessage.success('已保存')
    dlgVisible.value = false
    await load()
    if (editingId.value) current.value = caseDatasets.value.find((d) => d.id === editingId.value) || current.value
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

async function remove(d: DataSet) {
  try {
    await ElMessageBox.confirm(
      d.case_bound_count
        ? `数据集已被所属用例绑定，请先在用例管理解绑后再删除`
        : `确认删除数据集「${d.name}」及其全部数据行？`,
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
    ElMessage.error(e?.response?.data?.detail || '删除失败')
  }
}

// ---------- 复制 / 重新同步（隔离语义下的复用与快照更新） ----------
async function copyDataset() {
  if (!current.value) return
  try {
    const nd = await datasetApi.copy(current.value.id)
    ElMessage.success(`已复制为「${nd.name}」`)
    await load()
    current.value = caseDatasets.value.find((d) => d.id === nd.id) || current.value
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '复制失败')
  }
}

async function resyncDataset() {
  if (!current.value) return
  resyncing.value = true
  try {
    const r = await datasetApi.resync(current.value.id)
    ElMessage.success(r.message)
    await load()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '重新同步失败')
  } finally {
    resyncing.value = false
  }
}

// ---------- 快照明细（只读） ----------
const snapVisible = ref(false)
const snapViewing = ref<DataSetNodeConfig | null>(null)
const snapJson = computed(() => JSON.stringify(snapViewing.value, null, 2))

function viewSnapshot(c: DataSetNodeConfig) {
  snapViewing.value = c
  snapVisible.value = true
}

// ---------- 从用例生成（写死参数 + 节点配置快照） ----------
const genVisible = ref(false)
const genSaving = ref(false)
const genCases = ref<TestCase[]>([])
const genCaseId = ref<number | null>(null)
const genName = ref('')

async function openGenerate() {
  genCaseId.value = currentCase.value?.id ?? null
  genName.value = ''
  genVisible.value = true
  try {
    genCases.value = await caseApi.list(store.currentProjectId ?? undefined)
  } catch {
    genCases.value = []
  }
}

watch(genCaseId, (id) => {
  const c = genCases.value.find((c) => c.id === id)
  genName.value = c ? `${c.name}-参数集` : ''
})

async function confirmGenerate() {
  if (!genCaseId.value) return ElMessage.warning('请选择用例')
  genSaving.value = true
  try {
    const { dataset, stats } = await datasetApi.generate(genCaseId.value, genName.value.trim() || undefined)
    ElMessage.success(`已生成「${dataset.name}」：${stats.columns} 列 · 扫描 ${stats.nodes} 节点 · 含 1 行原值快照`)
    if (stats.conflicts?.length) {
      const keys = stats.conflicts.slice(0, 5).map((c) => c.key).join('、')
      ElMessage.info(`${stats.conflicts.length} 个参数跨节点取值不同，已取首节点值成列：${keys}${stats.conflicts.length > 5 ? '…' : ''}`)
    }
    genVisible.value = false
    await load()
    currentCase.value = cases.value.find((c) => c.id === genCaseId.value) || currentCase.value
    current.value = caseDatasets.value.find((d) => d.id === dataset.id) || current.value
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '生成失败')
  } finally {
    genSaving.value = false
  }
}

// ---------- 行编辑（右侧抽屉：字段纵向排列 + 搜索定位） ----------
const editingRowId = ref<number | null>(null)
const editingRowIndex = ref<number | null>(null)
const editingRowData = ref<Record<string, any>>({})
const drawerVisible = ref(false)
const rowSaving = ref(false)
const fieldSearch = ref('')

// JSON 文本字段判定（对象/数组列编辑态显示为 JSON 文本，用 textarea）
function isJsonText(v: any) {
  return typeof v === 'string' && (v.startsWith('[') || v.startsWith('{'))
}

/** 即时 JSON 校验：文本以 {/[ 开头但解析失败时给出提示（不阻塞输入） */
function jsonError(key: string) {
  const v = editingRowData.value[key]
  if (!isJsonText(v)) return ''
  try {
    JSON.parse(v)
    return ''
  } catch (e: any) {
    return `JSON 格式错误：${e.message}`
  }
}

const filteredFields = computed(() => {
  const cols = current.value?.columns || []
  const kw = fieldSearch.value.trim().toLowerCase()
  if (!kw) return cols
  return cols.filter(
    (c) => c.key.toLowerCase().includes(kw) || colLabel(c.key).toLowerCase().includes(kw),
  )
})

function startEditRow(row: any) {
  editingRowId.value = row.id
  editingRowIndex.value = row.row_index
  fieldSearch.value = ''
  // 对象/数组字段先序列化为 JSON 文本再编辑：el-input 直接绑对象会显示 [object Object]，
  // 且用户一旦触碰该输入框，原对象就被覆盖成字符串导致数据损坏
  const data: Record<string, any> = {}
  Object.entries(row.data || {}).forEach(([k, v]) => {
    data[k] = typeof v === 'object' && v !== null ? JSON.stringify(v, null, 2) : v
  })
  editingRowData.value = data
  drawerVisible.value = true
}

function cancelEditRow() {
  drawerVisible.value = false
  editingRowId.value = null
  editingRowIndex.value = null
  editingRowData.value = {}
}

async function saveRow() {
  if (!current.value || !editingRowId.value) return
  // 有 JSON 语法错误时阻止保存（提示第一个错误字段）
  for (const col of current.value.columns) {
    const err = jsonError(col.key)
    if (err) {
      fieldSearch.value = ''
      ElMessage.error(`${colLabel(col.key)}：${err}`)
      return
    }
  }
  // JSON 文本还原为对象/数组
  const data: Record<string, any> = {}
  Object.entries(editingRowData.value).forEach(([k, v]) => {
    if (isJsonText(v)) {
      try {
        data[k] = JSON.parse(v)
        return
      } catch {
        // 上方已校验，这里不会走到
      }
    }
    data[k] = v
  })
  rowSaving.value = true
  try {
    await datasetApi.updateRow(current.value.id, editingRowId.value, data)
    ElMessage.success('已保存')
    cancelEditRow()
    await load()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '保存失败')
  } finally {
    rowSaving.value = false
  }
}

async function addRow() {
  if (!current.value) return
  if (!current.value.columns.length) return ElMessage.warning('请先编辑列定义')
  const data: Record<string, any> = {}
  current.value.columns.forEach((c) => (data[c.key] = ''))
  try {
    await datasetApi.addRow(current.value.id, data)
    await load()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '添加失败')
  }
}

async function removeRow(row: any) {
  if (!current.value) return
  try {
    await datasetApi.removeRow(current.value.id, row.id)
    await load()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '删除失败')
  }
}

/** 复制行：原行数据原样追加为新行（row_index 顺延），常用于改少数字段的近似场景 */
async function copyRow(row: any) {
  if (!current.value) return
  try {
    await datasetApi.copyRow(current.value.id, row.id)
    ElMessage.success('已复制为新行')
    await load()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '复制失败')
  }
}

async function clearRows() {
  if (!current.value) return
  try {
    await ElMessageBox.confirm('确认清空全部数据行？', '清空', { type: 'warning' })
  } catch {
    return
  }
  try {
    await datasetApi.clearRows(current.value.id)
    ElMessage.success('已清空')
    await load()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '操作失败')
  }
}

// ---------- 导入（预览 → 确认） ----------
const previewVisible = ref(false)
const previewRows = ref<Record<string, any>[]>([])
const previewWarnings = ref<string[]>([])
const previewCols = ref<string[]>([])
const importing = ref(false)
let pendingFile: File | null = null

async function onImportFile(file: any) {
  if (!current.value) return
  pendingFile = file.raw as File
  try {
    const res = await datasetApi.importFile(current.value.id, pendingFile, true)
    previewRows.value = res.rows || []
    previewWarnings.value = res.warnings || []
    previewCols.value = (current.value.columns || []).map((c) => c.key)
    previewVisible.value = true
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '解析失败')
  }
}

async function confirmImport() {
  if (!current.value || !pendingFile) return
  importing.value = true
  try {
    const res = await datasetApi.importFile(current.value.id, pendingFile, false)
    ElMessage.success(`已导入 ${res.count} 行`)
    previewVisible.value = false
    await load()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '导入失败')
  } finally {
    importing.value = false
  }
}

function fmtCell(v: any) {
  if (v === null || v === undefined || v === '') return '—'
  if (typeof v === 'object') return JSON.stringify(v)
  return String(v)
}

// ---------- 行导出 Excel ----------
async function exportRows() {
  if (!current.value) return
  try {
    const blob = await datasetApi.exportRows(current.value.id)
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    const stamp = new Date().toISOString().replace(/[-:T]/g, '').slice(0, 14)
    link.href = url
    link.download = `${current.value.name}_${stamp}.xlsx`
    link.click()
    URL.revokeObjectURL(url)
    ElMessage.success('已导出 Excel')
  } catch (e: any) {
    // blob 错误响应需按文本解析（axios 对 blob 不走 JSON 拦截）
    try {
      const txt = await (e?.response?.data as Blob)?.text()
      const detail = txt ? JSON.parse(txt).detail : ''
      ElMessage.error(detail || '导出失败')
    } catch {
      ElMessage.error('导出失败')
    }
  }
}

// ---------- 从其他数据集覆盖（节点级对比合并） ----------
const mergeVisible = ref(false)
const mergeSourceId = ref<number | null>(null)
const mergeLoading = ref(false)
const merging = ref(false)
const mergePreviewData = ref<Awaited<ReturnType<typeof datasetApi.mergePreview>> | null>(null)
const mergeSelectedApis = ref<number[]>([])
const mergeRowIdx = ref(1)
const mergeTableRef = ref()

/** 源候选：同项目其他数据集（项目内已全量加载，无需再请求） */
const mergeCandidates = computed(() =>
  datasets.value.filter((d) => d.id !== current.value?.id && (d.rows?.length ?? 0) > 0),
)

function caseName(caseId: number) {
  return cases.value.find((c) => c.id === caseId)?.name || `用例#${caseId}`
}

function openMerge() {
  mergeSourceId.value = null
  mergePreviewData.value = null
  mergeSelectedApis.value = []
  mergeRowIdx.value = 1
  mergeVisible.value = true
}

async function doMergePreview() {
  if (!current.value || !mergeSourceId.value) return
  mergeLoading.value = true
  mergePreviewData.value = null
  try {
    mergePreviewData.value = await datasetApi.mergePreview(current.value.id, mergeSourceId.value)
    mergeSelectedApis.value = mergePreviewData.value.common_nodes.map((n) => n.api_id)
    // 表格默认全选（selection 列不记忆状态，需手动 toggle）
    nextTick(() => {
      mergePreviewData.value?.common_nodes.forEach((n) =>
        mergeTableRef.value?.toggleRowSelection(n as any, true),
      )
    })
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '对比失败')
  } finally {
    mergeLoading.value = false
  }
}

async function confirmMerge() {
  if (!current.value || !mergeSourceId.value || !mergeSelectedApis.value.length) return
  merging.value = true
  try {
    const res = await datasetApi.merge(current.value.id, {
      source_dataset_id: mergeSourceId.value,
      api_ids: mergeSelectedApis.value,
      source_row_index: mergeRowIdx.value,
    })
    ElMessage.success(`${res.message}：${res.keys.slice(0, 8).join('、')}${res.keys.length > 8 ? '…' : ''}`)
    mergeVisible.value = false
    await load()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '覆盖合并失败')
  } finally {
    merging.value = false
  }
}

onMounted(load)
watch(() => store.currentProjectId, () => {
  currentCase.value = null
  current.value = null
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
.group-icon {
  font-size: 16px;
  color: var(--app-primary);
}
.case-icon {
  font-size: 14px;
  color: var(--app-text-faint);
}
.side-node.on .case-icon {
  color: var(--app-primary);
}
.group-row {
  color: var(--app-text);
  font-weight: 500;
}
.expand-icon {
  font-size: 12px;
  transition: transform 0.15s;
  color: var(--app-text-faint);
}
.expand-icon.expanded {
  transform: rotate(90deg);
}
.expand-spacer {
  width: 12px;
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
/* 数据集切换条 */
.ds-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  margin-bottom: 12px;
}
.ds-chip {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 12px;
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius-sm);
  cursor: pointer;
  user-select: none;
  color: var(--app-text-muted);
  background: var(--app-card);
}
.ds-chip:hover {
  border-color: var(--app-primary);
  color: var(--app-text);
}
.ds-chip.on {
  background: var(--app-active);
  border-color: var(--app-primary);
  color: var(--app-primary);
  font-weight: 500;
}
.ds-icon {
  font-size: 14px;
}
.ds-name {
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.ds-cnt {
  font-size: 11px;
  color: var(--app-text-faint);
}
.ds-chip.on .ds-cnt {
  color: var(--app-primary);
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
.group-count {
  background: var(--app-primary);
  color: #fff;
  border-radius: var(--app-radius-sm);
  padding: 1px 10px;
  font-size: 12px;
  font-weight: 500;
  min-width: 24px;
  text-align: center;
}
.main-sub {
  flex: 1;
  min-width: 0;
  font-size: 12px;
  color: var(--app-text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.main-actions {
  margin-left: auto;
  display: flex;
  gap: 8px;
  align-items: center;
  flex-shrink: 0;
}
.row-ops {
  margin-top: 10px;
  display: flex;
  gap: 8px;
  align-items: center;
}
.tip {
  color: var(--app-text-muted);
  font-size: 12px;
}
.col-key-raw {
  margin-left: 4px;
  font-size: 11px;
  color: var(--app-text-faint);
}
.col-row {
  display: flex;
  gap: 8px;
  margin-bottom: 8px;
  align-items: center;
}
.col-dict {
  width: 170px;
  font-size: 12px;
  color: var(--app-text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.cols-editor {
  width: 100%;
  /* 列定义多时限高滚动，防弹窗无限膨胀；+ 添加列按钮与提示随滚动区之外常驻 */
  display: flex;
  flex-direction: column;
}
.cols-editor .col-list {
  max-height: 300px;
  overflow-y: auto;
  padding-right: 4px;
}
/* 节点配置快照面板 */
.snap-panel {
  margin-top: 14px;
  border-top: 1px solid var(--app-border);
}
.snap-title {
  font-size: 13px;
  font-weight: 500;
  color: var(--app-text);
}
.snap-tip {
  margin-left: 10px;
  font-size: 12px;
  color: var(--app-text-muted);
}
.snap-actions {
  display: flex;
  gap: 10px;
  align-items: center;
  margin-bottom: 10px;
}
.snap-json {
  max-height: 420px;
  overflow: auto;
  padding: 12px;
  background: var(--app-bg);
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius-sm);
  font-size: 12px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-all;
}
.preview-tip {
  margin-bottom: 10px;
  color: var(--app-text-muted);
  font-size: 13px;
}
/* 用例下拉选项：超长名截断省略，防下拉面板无限变宽 */
.gen-case-option {
  display: block;
  max-width: 420px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
/* 行编辑抽屉：搜索固定顶部，字段区独立滚动 */
.drawer-body {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 0 4px;
}
.field-search {
  margin-bottom: 8px;
}
.field-count {
  font-size: 12px;
  color: var(--app-text-muted);
  margin-bottom: 8px;
}
.field-scroll {
  flex: 1;
}
.col-type-tag {
  margin-left: 6px;
  font-size: 11px;
  color: var(--app-text-muted);
  border: 1px solid var(--el-border-color);
  border-radius: 3px;
  padding: 0 4px;
}
.json-err {
  font-size: 12px;
  color: var(--el-color-danger);
  margin-top: 2px;
}
/* 覆盖合并弹窗 */
.merge-hint {
  font-size: 12px;
  color: var(--app-text-muted);
  margin-left: 12px;
}
.merge-cols {
  font-size: 12px;
  color: var(--app-text-muted);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
</style>

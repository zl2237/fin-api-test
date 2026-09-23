<template>
  <div class="page">
    <div class="page-head">
      <div class="head-left">
        <span class="page-title">数据集</span>
      </div>
      <div class="head-right">
        <span class="head-tip">变量按参数名自动匹配各节点同名入参 · 数据集按用例隔离 · 每个数据集一套数据（测试数据唯一来源） · 多场景建多个数据集 · 复用靠复制</span>
      </div>
    </div>

    <!-- 左用例分组树 + 右该用例数据集（用例维度，数据集互相隔离） -->
    <div v-loading="loading" class="group-layout">
      <aside class="group-side">
        <template v-for="row in sideRows" :key="row.kind === 'group' ? `g${row.id}` : `c${row.id}`">
          <!-- 分组节点：折叠/展开组内用例（样式与接口/用例页左树同规格） -->
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
              <span class="ds-cnt">{{ d.columns?.length ?? 0 }} 变量</span>
            </div>
          </div>

          <EmptyState
            v-if="!caseDatasets.length"
            description="该用例暂无数据集。保存用例会自动收集静态值生成默认数据集；需要多场景时复制现有数据集再改值"
          />

          <template v-else-if="current">
            <div class="main-head">
              <span class="main-title">{{ current.name }}</span>
              <span class="group-count">{{ totalCount }}</span>
              <div class="main-actions">
                <el-button size="small" type="primary" :loading="savingValues" :disabled="!view" @click="saveValues">保存</el-button>
                <el-button size="small" @click="copyDataset">复制</el-button>
                <el-button size="small" @click="openMerge">从其他数据集覆盖…</el-button>
                <el-button size="small" @click="openEdit(current)">编辑信息</el-button>
                <el-button size="small" type="danger" link @click="remove(current)">删除</el-button>
              </div>
            </div>

            <div v-loading="viewLoading" class="params-area">
              <EmptyState
                v-if="!viewLoading && !view?.nodes.length"
                description="当前用例编排没有可配置入参的节点（先在用例设计器绑定接口）"
                :image-size="60"
              />

              <template v-else-if="view">
                <!-- 悬空变量提示：池中存在但当前编排无节点使用；显式清理（普通保存不隐式删除） -->
                <el-alert v-if="view.orphan_keys.length" type="info" :closable="false" class="orphan-tip">
                  <template #title>
                    {{ view.orphan_keys.length }} 个池变量已不被编排使用（节点已删/改参）：{{ view.orphan_keys.slice(0, 6).join('、') }}{{ view.orphan_keys.length > 6 ? '…' : '' }}
                    <el-button link type="primary" size="small" :loading="savingValues" @click="cleanOrphans">立即清理</el-button>
                  </template>
                </el-alert>

                <!-- 配置概览 + 检索工具：大池（数百变量）按名/中文名搜索，只看未配置快速补值 -->
                <div class="pool-stat">
                  <span>已配置 <b>{{ filledCount }}</b> / {{ totalCount }} 个变量</span>
                  <span class="stat-note">未配置的变量执行时发送空值（""/null）</span>
                  <el-input
                    v-model="searchKey"
                    size="small"
                    clearable
                    placeholder="搜索变量（名/中文名）"
                    class="pool-search"
                  />
                  <el-checkbox v-model="onlyUnfilled" size="small">只看未配置</el-checkbox>
                  <el-button v-if="activeNodeId === '__all__'" size="small" class="add-var-btn" @click="openAddVariable">新增变量</el-button>
                  <el-button v-if="activeNodeId !== '__all__'" size="small" class="add-var-btn" @click="openImport">导入变量…</el-button>
                </div>

                <!-- 变量池 = 用例级单池；总览页签看全部变量（去重），节点页签按节点筛选 -->
                <el-tabs v-model="activeNodeId" class="node-tabs">
                  <el-tab-pane name="__all__">
                    <template #label>
                      <span class="tab-label">变量池总览</span>
                      <span class="tab-cnt">{{ view.all_params.length }}</span>
                    </template>
                  </el-tab-pane>
                  <el-tab-pane v-for="node in view.nodes" :key="node.node_id" :name="node.node_id">
                    <template #label>
                      <span class="tab-label">{{ node.label }}</span>
                      <span class="tab-cnt">{{ node.params.length }}</span>
                    </template>
                  </el-tab-pane>
                </el-tabs>

                <!-- 就近作用域提示：双作用域编辑是本页核心心智模型 -->
                <div class="scope-tip">
                  <template v-if="activeNodeId === '__all__'">
                    此处编辑池值：一键一值，各节点共享（同名参数全部生效）
                  </template>
                  <template v-else>
                    此处编辑「{{ currentScopeNodeLabel }}」的手动覆盖值：压过池值，其他节点不受影响；清空后回落池值
                  </template>
                </div>

                <div class="node-params">
                  <EmptyState
                    v-if="!filteredParams.length"
                    :description="searchKey || onlyUnfilled ? '没有匹配的变量（调整搜索/过滤条件）' : '暂无变量'"
                    :image-size="60"
                  />
                  <div
                    v-for="p in filteredParams"
                    :key="p.key"
                    class="param-row"
                    :class="{ manual: p.manual }"
                  >
                    <div class="param-label">
                      <span>{{ colLabel(p.key) }}</span>
                      <span class="col-type-tag">{{ p.type }}</span>
                      <el-button
                        v-if="activeNodeId === '__all__'"
                        link
                        type="danger"
                        size="small"
                        class="del-var-btn"
                        :disabled="p.manual || p.dynamic"
                        @click="removeVariable(p)"
                      >
                        删除
                      </el-button>
                      <!-- 状态徽标：手动覆盖 / 已动态配置 / 已配置 / 未配置 -->
                      <el-tooltip
                        v-if="p.manual"
                        :content="`节点手动覆盖：${String(p.manual_value ?? '')}——压过池值；清空后回落池值`"
                        placement="top"
                        popper-class="app-tip"
                      >
                        <span class="badge badge-manual">手动覆盖</span>
                      </el-tooltip>
                      <el-tooltip
                        v-else-if="p.dynamic"
                        :content="`节点已动态配置：${String(p.manual_value ?? '')}——运行时表达式求值（优先生效，请在用例编排中调整）`"
                        placement="top"
                        popper-class="app-tip"
                      >
                        <span class="badge badge-dynamic">已动态配置</span>
                      </el-tooltip>
                      <el-tooltip
                        v-else-if="isFilled(p)"
                        :content="activeNodeId === '__all__'
                          ? '变量池中已有值，执行时按参数名取此值'
                          : '池值（各节点共享）；在此改值即成为该节点手动覆盖，压过池值'"
                        placement="top"
                        popper-class="app-tip"
                      >
                        <span class="badge badge-filled">已配置</span>
                      </el-tooltip>
                      <el-tooltip
                        v-else
                        :content="activeNodeId === '__all__'
                          ? '池中无值：留空时发送空值（“”/null）；需引用运行时变量请用 ${} 显式绑定'
                          : '池中无值：填值即成为该节点手动覆盖；留空同池语义'"
                        placement="top"
                        popper-class="app-tip"
                      >
                        <span class="badge badge-empty">未配置</span>
                      </el-tooltip>
                    </div>
                    <!-- file 类型：值是文件中心文件 ID，弹文件选择器；显示文件名（ID 备查） -->
                    <div v-if="p.type === 'file'" class="file-value-cell">
                      <el-input
                        :model-value="editVal(p.key) ? fileLabel(String(editVal(p.key))) : ''"
                        readonly
                        placeholder="未选择文件"
                        class="file-value-input"
                      />
                      <el-button
                        link
                        type="primary"
                        :disabled="p.dynamic && activeNodeId !== '__all__'"
                        @click="openFilePicker(p.key)"
                      >选择</el-button>
                      <el-button
                        v-if="editVal(p.key)"
                        link
                        type="danger"
                        :disabled="p.dynamic && activeNodeId !== '__all__'"
                        @click="setEditVal(p.key, '')"
                      >清除</el-button>
                    </div>
                    <el-input
                      v-else
                      :model-value="editVal(p.key)"
                      @update:model-value="(v: string) => setEditVal(p.key, v)"
                      @blur="beautifyJson(p.key)"
                      :type="isJsonText(editVal(p.key)) ? 'textarea' : 'text'"
                      :autosize="{ minRows: 1, maxRows: 20 }"
                      :placeholder="paramPlaceholder(p)"
                      :disabled="p.dynamic && activeNodeId !== '__all__'"
                    />
                    <div
                      v-if="!(p.dynamic && activeNodeId !== '__all__') && jsonError(editVal(p.key))"
                      class="json-err"
                    >{{ jsonError(editVal(p.key)) }}</div>
                  </div>
                </div>

                <div class="pool-tip">
                  徽标含义：<span class="badge badge-filled">已配置</span>=池中有值（执行取此值）；
                  <span class="badge badge-dynamic">已动态配置</span>=节点编排 ${} 运行时求值，优先生效；
                  <span class="badge badge-empty">未配置</span>=池中无值，留空时发送空值（“”/null）；
                  <span class="badge badge-manual">手动覆盖</span>=节点编排字面量优先，池值暂不生效。
                  优先级：手动覆盖 &gt; 套件注入 &gt; 数据集变量池；运行时变量不自动按名取值，仅 ${} 显式引用
                  <el-button text size="small" class="help-link" @click="store.openCoreCapability('dataset')">查看数据集用法</el-button>
                </div>
              </template>
            </div>
          </template>
        </template>
      </div>
    </div>

    <!-- 脏状态吸底保存条：长列表编辑后保存按钮不随滚动丢失 -->
    <transition name="el-fade-in">
      <div v-if="current && isDirty && !savingValues" class="save-dock">
        <span class="save-dock-text">{{ dirtyCount }} 处未保存改动（含节点手动覆盖）</span>
        <el-button size="small" @click="discardEdits">放弃</el-button>
        <el-button size="small" type="primary" @click="saveValues">保存</el-button>
      </div>
    </transition>

    <!-- 编辑数据集信息（名称/描述）：新建走「保存用例自动建池」或「复制」，无手动新建 -->
    <el-dialog v-model="dlgVisible" title="编辑数据集" width="560px">
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
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>

    <!-- 新增变量（变量池加列） -->
    <el-dialog v-model="addVarVisible" title="新增变量" width="460px" :close-on-click-modal="false">
      <el-alert
        type="info"
        :closable="false"
        style="margin-bottom: 12px"
        title="在变量池中新增一个变量（列）。同字段在不同节点取值不同的参数（如状态流转）建议不从池取值，改由各节点在用例编排中单独配置"
      />
      <el-form label-width="70px">
        <el-form-item label="变量名" required>
          <el-input v-model="addVarKey" placeholder="如：entrust_status 或 to_customer.remark（点路径）" maxlength="100" />
        </el-form-item>
        <el-form-item label="类型">
          <el-select v-model="addVarType" style="width: 100%">
            <el-option v-for="t in ['string', 'int', 'bool', 'array', 'object', 'file']" :key="t" :label="t" :value="t" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="addVarVisible = false">取消</el-button>
        <el-button type="primary" @click="confirmAddVariable">添加</el-button>
      </template>
    </el-dialog>

    <!-- 节点变量导入：粘贴 JSON → 预览（动态不覆盖/静态替换/忽略）→ 确认应用并保存 -->
    <el-dialog v-model="importVisible" title="导入节点变量" width="760px" :close-on-click-modal="false">
      <el-input
        v-model="importText"
        type="textarea"
        :rows="8"
        placeholder="粘贴 JSON 对象（{...}）；解析预览后仅「将被替换」的变量会被应用，动态绑定（${}）不会被覆盖"
      />
      <div class="import-actions">
        <el-button size="small" @click="parseImport">解析预览</el-button>
      </div>
      <el-table v-if="importRows.length" :data="importRows" size="small" border max-height="320">
        <el-table-column label="变量" prop="key" width="200" show-overflow-tooltip />
        <el-table-column label="状态" width="150">
          <template #default="{ row }">
            <span class="badge" :class="row.badge">{{ row.statusText }}</span>
          </template>
        </el-table-column>
        <el-table-column label="当前值" min-width="160" show-overflow-tooltip>
          <template #default="{ row }">{{ row.cur || '（空）' }}</template>
        </el-table-column>
        <el-table-column label="导入值" min-width="160" show-overflow-tooltip>
          <template #default="{ row }">{{ row.neu }}</template>
        </el-table-column>
      </el-table>
      <template #footer>
        <el-button @click="importVisible = false">取消</el-button>
        <el-button type="primary" :disabled="!applyCount" :loading="savingValues" @click="confirmImport">
          确认导入{{ applyCount ? `（${applyCount} 项替换）` : '' }}
        </el-button>
      </template>
    </el-dialog>

    <!-- file 参数取值：文件中心选择器 -->
    <FilePicker
      v-model="filePickerVisible"
      :model-file-id="editingValues[filePickerKey] || ''"
      @select="onFileSelect"
    />

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
              :label="`${d.name}（${caseName(d.case_id)}，${d.columns?.length ?? 0} 变量）`"
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
          <el-table
            ref="mergeTableRef"
            :data="mergePreviewData.common_nodes"
            size="small"
            @selection-change="(rows: any[]) => (mergeSelectedApis = rows.map((r) => r.api_id))"
          >
            <el-table-column type="selection" width="40" />
            <el-table-column prop="api_name" label="相同节点（接口）" min-width="140" />
            <el-table-column label="涉及变量" min-width="300">
              <template #default="{ row }">
                <el-tooltip :content="row.columns.map(colLabel).join('、')" placement="top" popper-class="app-tip">
                  <span class="merge-cols">{{ row.columns.map(colLabel).join('、') }}</span>
                </el-tooltip>
              </template>
            </el-table-column>
          </el-table>
          <div class="merge-hint" style="margin-top: 8px">
            已选 {{ mergeSelectedApis.length }} 个节点 · 源「{{ mergePreviewData.source.name }}」的单套值将覆盖勾选节点涉及变量 ·
            目标独有变量保持不变 · 源空值不覆盖
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
import { CaretRight, Document, Grid, WarningFilled } from '@element-plus/icons-vue'
import { datasetApi, caseApi, caseGroupApi, fileApi, type DataSet, type TestCase, type CaseGroup, type DatasetParamsView, type DatasetParam, type TestFile } from '@/api'
import { useGroupTree, expandStorageKey, type GroupTreeNode } from '@/composables/useGroupTree'
import { useFieldDict } from '@/composables/useFieldDict'
import { useAppStore } from '@/stores'
import EmptyState from '@/components/EmptyState.vue'
import FilePicker from '@/components/FilePicker.vue'

const store = useAppStore()
const { dictLabel } = useFieldDict()
const cases = ref<TestCase[]>([])
const groups = ref<CaseGroup[]>([])
const datasets = ref<DataSet[]>([])
const currentCase = ref<TestCase | null>(null)
const current = ref<DataSet | null>(null)
const loading = ref(false)
const loadError = ref('')
const saving = ref(false)

const caseDatasets = computed(() => datasets.value.filter((d) => d.case_id === currentCase.value?.id))

// ===== 变量池视图（用例级单池；节点为筛选视角） =====
const view = ref<DatasetParamsView | null>(null)
const viewLoading = ref(false)
const savingValues = ref(false)
const editingValues = ref<Record<string, any>>({})
const activeNodeId = ref('__all__')  // 默认总览：全部变量去重平铺
// 节点级编辑态：node_id → key → 值（节点页签编辑 = 写该节点手动覆盖，压过池值；
// 池总览页签编辑 = 池值本身，一键一值向各节点共享）
const nodeEdits = ref<Record<string, Record<string, any>>>({})
// 脏检测基线：node_id → key → 序列化初值（manual/dynamic 显示 manual_value，否则池值）
const nodeBaselines = ref<Record<string, Record<string, string>>>({})
// 池值基线（总览页签脏检测）：key → 序列化初值
const poolBaseline = ref<Record<string, string>>({})
// 动态绑定键（值含 ${}，编排配置）：节点页签只读，编辑/清除一律跳过
const dynamicKeysByNode = ref<Record<string, Set<string>>>({})
// file 类型值（文件 ID）→ 文件名映射（拉一次项目文件列表）
const fileNames = ref<Record<string, string>>({})

/** 当前页签的参数清单：总览 = all_params（用例级去重）；节点页签 = 该节点视角 */
const currentParams = computed<DatasetParam[]>(() => {
  if (!view.value) return []
  if (activeNodeId.value === '__all__') return view.value.all_params
  return view.value.nodes.find((n) => n.node_id === activeNodeId.value)?.params ?? []
})

// ===== 检索工具：搜索（名/字典中文名）+ 只看未配置（manual/dynamic 有编排值来源，视为已配置） =====
const searchKey = ref('')
const onlyUnfilled = ref(false)

const filteredParams = computed<DatasetParam[]>(() => {
  const q = searchKey.value.trim().toLowerCase()
  return currentParams.value.filter((p) => {
    if (onlyUnfilled.value && (isFilled(p) || p.manual || p.dynamic)) return false
    if (!q) return true
    return p.key.toLowerCase().includes(q) || (dictLabel(p.key) || '').toLowerCase().includes(q)
  })
})

/** 当前节点页签的显示名（作用域提示用） */
const currentScopeNodeLabel = computed(
  () => view.value?.nodes.find((n) => n.node_id === activeNodeId.value)?.label ?? activeNodeId.value,
)

const filledCount = computed(
  () => view.value?.all_params.filter(isFilled).length ?? 0,
)
const totalCount = computed(() => view.value?.all_params.length ?? 0)

/** 池中已有值（编辑态实时：输入框非空即已配置） */
function isFilled(p: DatasetParam) {
  const v = editingValues.value[p.key]
  return v !== '' && v !== null && v !== undefined
}

/** 当前作用域的编辑值：总览 = 池值；节点页签 = 该节点手动覆盖值 */
function editVal(key: string): any {
  if (activeNodeId.value === '__all__') return editingValues.value[key]
  return nodeEdits.value[activeNodeId.value]?.[key]
}

/** 当前作用域写值（v-model 无法绑三元表达式，经此分发） */
function setEditVal(key: string, v: any) {
  if (activeNodeId.value === '__all__') {
    editingValues.value[key] = v
    return
  }
  const m = nodeEdits.value[activeNodeId.value]
  if (m) m[key] = v
}

/** 失焦自动美化：输入/粘贴的合法 JSON 文本统一缩进换行；非法（${} 动态绑定/尾逗号等）原样保留，错误由 jsonError 实时提示 */
function beautifyJson(key: string) {
  const v = editVal(key)
  if (!isJsonText(v)) return
  try {
    setEditVal(key, JSON.stringify(JSON.parse(v.trim()), null, 2))
  } catch {
    // 非法 JSON（尾逗号/动态绑定占位等）：不动
  }
}

/** 序列化（对象/数组转 JSON 文本，与池编辑同一格式；紧凑 JSON 文本字符串自动美化缩进换行） */
function _ser(v: any): string {
  if (typeof v === 'object' && v !== null) return JSON.stringify(v, null, 2)
  if (isJsonText(v)) {
    try {
      return JSON.stringify(JSON.parse(v), null, 2)  // 合法 JSON 文本：统一美化
    } catch {
      return v  // 非法（${} 动态绑定/尾逗号等）：原样保留
    }
  }
  return v ?? ''
}

/** 值文本还原：JSON 文本解析回对象/数组，其余原样 */
function _parse(v: any): any {
  if (isJsonText(v)) {
    try {
      return JSON.parse(v)
    } catch {
      return v
    }
  }
  return v
}

// 上次加载视图的数据集：id 变化（切换/复制）才重置视角；
// 保存/覆盖合并后的原位刷新保留当前 tab、搜索词与过滤——用户视角不被动荡
let lastViewDatasetId: number | null = null

async function loadParamsView(id: number) {
  const viewChanged = id !== lastViewDatasetId
  lastViewDatasetId = id
  viewLoading.value = true
  try {
    view.value = await datasetApi.paramsView(id)
    // 编辑副本：对象/数组序列化为 JSON 文本（el-input 直接绑对象会显示 [object Object]，
    // 且用户一旦触碰输入框，原对象就被覆盖成字符串导致数据损坏）
    const data: Record<string, any> = {}
    for (const node of view.value.nodes) {
      for (const p of node.params) {
        if (p.key in data) continue
        const v = p.value
        data[p.key] = _ser(v)
      }
    }
    // 悬空变量保留在编辑副本（保存时可随清单清理，也可继续给值）
    for (const k of view.value.orphan_keys) {
      if (!(k in data)) data[k] = ''
    }
    editingValues.value = data
    poolBaseline.value = { ...data }
    // 节点级编辑态：manual/dynamic 显示绑定值（manual 可改，dynamic 只读），
    // 其余显示池值——改了即成该节点手动覆盖；基线用于保存时脏检测
    const edits: Record<string, Record<string, any>> = {}
    const bases: Record<string, Record<string, string>> = {}
    const dyn: Record<string, Set<string>> = {}
    for (const node of view.value.nodes) {
      const m: Record<string, any> = {}
      const b: Record<string, string> = {}
      const dk = new Set<string>()
      for (const p of node.params) {
        const base = (p.manual || p.dynamic) ? p.manual_value : p.value
        m[p.key] = _ser(base)
        b[p.key] = _ser(base)
        if (p.dynamic) dk.add(p.key)
      }
      edits[node.node_id] = m
      bases[node.node_id] = b
      dyn[node.node_id] = dk
    }
    nodeEdits.value = edits
    nodeBaselines.value = bases
    dynamicKeysByNode.value = dyn
    if (viewChanged) {
      activeNodeId.value = '__all__'  // 切换数据集回到总览
      searchKey.value = ''
      onlyUnfilled.value = false
    }
    await loadFileNames()
  } catch (e: any) {
    ElMessage.error(e.message || '加载变量池视图失败')
    view.value = null
  } finally {
    viewLoading.value = false
  }
}

/** file 值显示名：项目文件列表建 ID→文件名映射（查无时回退 #ID） */
async function loadFileNames() {
  const ids = new Set<string>()
  for (const node of view.value?.nodes || []) {
    for (const p of node.params) {
      if (p.type !== 'file') continue
      // 池值 + 手动覆盖值都收集：file 参数的值可能是节点字面量（manual_value），
      // 只收池值会漏建映射，节点页签的文件显示回退成 #ID
      if (p.value) ids.add(String(p.value))
      const mv = p.manual_value
      if (mv !== undefined && mv !== null && mv !== '' && !String(mv).includes('${')) {
        ids.add(String(mv))
      }
    }
  }
  for (const d of caseDatasets.value) {
    for (const c of d.columns || []) {
      if (c.type === 'file') {
        const v = editingValues.value[c.key]
        if (v) ids.add(String(v))
      }
    }
  }
  if (!ids.size) {
    fileNames.value = {}
    return
  }
  try {
    const files = await fileApi.list(store.currentProjectId!)
    const m: Record<string, string> = {}
    for (const f of files) m[String(f.id)] = f.name || f.original_name || `#${f.id}`
    fileNames.value = m
  } catch {
    fileNames.value = {}
  }
}

function fileLabel(id: string) {
  return fileNames.value[id] || `#${id}`
}

/** 悬空变量显式清理：从编辑清单移除并保存（键不进 values 即删列） */
async function cleanOrphans() {
  if (!view.value?.orphan_keys.length) return
  try {
    await ElMessageBox.confirm(
      `确认清理 ${view.value.orphan_keys.length} 个已不被编排使用的池变量？清理后不可恢复。`,
      '清理悬空变量',
      { type: 'warning' },
    )
  } catch {
    return
  }
  for (const k of view.value.orphan_keys) {
    delete editingValues.value[k]
    delete addedVarTypes.value[k]
  }
  await saveValues()
}

// ===== 脏状态（吸底保存条）：池值增删改 + 节点手动覆盖改动 =====
const isDirty = computed(() => dirtyCount.value > 0)

const dirtyCount = computed(() => {
  let n = 0
  const base = poolBaseline.value
  const cur = editingValues.value
  const keys = new Set([...Object.keys(base), ...Object.keys(cur)])
  for (const k of keys) {
    if (String(cur[k] ?? '') !== String(base[k] ?? '')) n++
  }
  for (const [nid, m] of Object.entries(nodeEdits.value)) {
    const b = nodeBaselines.value[nid] || {}
    const dyn = dynamicKeysByNode.value[nid] || new Set<string>()
    for (const [k, v] of Object.entries(m)) {
      if (k in b && String(v) !== String(b[k]) && !dyn.has(k)) n++
    }
  }
  return n
})

/** 放弃改动：重载变量池视图（回到服务端状态） */
async function discardEdits() {
  if (!current.value) return
  await loadParamsView(current.value.id)
  ElMessage.info('已放弃未保存改动')
}

/** JSON 文本判定：trim 后以 [ 或 { 开头（前导空格不逃逸美化/校验/保存拦截三道防线） */
function isJsonText(v: any) {
  const s = typeof v === 'string' ? v.trim() : ''
  return s.startsWith('[') || s.startsWith('{')
}

// ===== 变量池新增/删除变量（保存时经 column_types 指定新列类型） =====
const addVarVisible = ref(false)
const addVarKey = ref('')
const addVarType = ref('string')
const addedVarTypes = ref<Record<string, string>>({})

// ===== 节点参数导入（粘贴 JSON → 预览 → 应用编辑态并保存） =====
interface ImportRow {
  key: string
  status: 'replace' | 'dynamic' | 'ignore' | 'same'
  statusText: string
  badge: string
  cur: string
  neu: string
}
const importVisible = ref(false)
const importText = ref('')
const importRows = ref<ImportRow[]>([])
const applyCount = computed(() => importRows.value.filter((r) => r.status === 'replace').length)

function openImport() {
  importText.value = ''
  importRows.value = []
  importVisible.value = true
}

/** 解析预览：当前节点参数与导入 JSON 逐键比对——动态绑定（${}）不覆盖，
 *  非该节点参数忽略，其余标记替换（同值标记不变） */
function parseImport() {
  let obj: any
  try {
    obj = JSON.parse(importText.value)
  } catch (e: any) {
    ElMessage.error(`JSON 解析失败：${e.message}`)
    return
  }
  if (typeof obj !== 'object' || obj === null || Array.isArray(obj)) {
    ElMessage.error('请粘贴 JSON 对象（{...}）')
    return
  }
  const node = view.value?.nodes.find((n) => n.node_id === activeNodeId.value)
  const byKey = new Map((node?.params || []).map((p) => [p.key, p]))
  const rows: ImportRow[] = []
  for (const [k, v] of Object.entries(obj)) {
    const neu = _ser(v)
    const p = byKey.get(k)
    if (!p) {
      rows.push({ key: k, status: 'ignore', statusText: '非该节点变量，忽略', badge: 'badge-empty', cur: '', neu })
    } else if (p.dynamic) {
      rows.push({ key: k, status: 'dynamic', statusText: '动态绑定，不覆盖', badge: 'badge-dynamic', cur: _ser(p.manual_value), neu })
    } else if (String(editVal(k)) === neu) {
      rows.push({ key: k, status: 'same', statusText: '值相同', badge: 'badge-filled', cur: neu, neu })
    } else {
      rows.push({ key: k, status: 'replace', statusText: '将被替换', badge: 'badge-manual', cur: String(editVal(k) ?? ''), neu })
    }
  }
  importRows.value = rows
  if (!rows.length) ElMessage.info('导入内容为空')
}

async function confirmImport() {
  // 仅替换项写入节点编辑态（与手输同一格式），复用保存链路（JSON 校验/脏检测）
  for (const r of importRows.value) {
    if (r.status === 'replace') setEditVal(r.key, r.neu)
  }
  importVisible.value = false
  await saveValues()
}
// 与后端 _COL_KEY_RE 一致：字母/数字/下划线/点路径段
const VAR_KEY_RE = /^(?:[A-Za-z_][A-Za-z0-9_]*|\d+)(?:\[(?:[A-Za-z_][A-Za-z0-9_]*)?\])*(?:\.(?:[A-Za-z_][A-Za-z0-9_]*|\d+)(?:\[(?:[A-Za-z_][A-Za-z0-9_]*)?\])*)*$/

function openAddVariable() {
  addVarKey.value = ''
  addVarType.value = 'string'
  addVarVisible.value = true
}

function confirmAddVariable() {
  const k = addVarKey.value.trim()
  if (!k) return ElMessage.warning('请填写变量名')
  if (!VAR_KEY_RE.test(k)) {
    return ElMessage.error('变量名不合法：仅允许字母/数字/下划线/点号（点路径段，段内不以数字开头、不含空格/${}）')
  }
  if (k in editingValues.value) return ElMessage.warning(`变量「${k}」已存在`)
  editingValues.value[k] = ''
  addedVarTypes.value[k] = addVarType.value
  addVarVisible.value = false
  ElMessage.info(`已添加变量「${k}」，填写值后点「保存」生效`)
}

async function removeVariable(p: DatasetParam) {
  if (!(p.key in editingValues.value)) return
  try {
    await ElMessageBox.confirm(
      `确认从变量池删除「${colLabel(p.key)}」？删除后该参数不再从池取值：若节点未配置手动/动态值，执行时发送空值（""/null）。同字段节点取不同值时，请改由各节点在用例编排中单独配置。`,
      '删除变量',
      { type: 'warning' },
    )
  } catch {
    return
  }
  delete editingValues.value[p.key]
  delete addedVarTypes.value[p.key]
  ElMessage.info('已从编辑清单移除，点「保存」后正式删除')
}

/** 即时 JSON 校验：文本以 {/[ 开头但解析失败时给出提示（不阻塞输入，保存时拦截） */
function jsonError(v: any) {
  if (!isJsonText(v)) return ''
  try {
    JSON.parse(v)
    return ''
  } catch (e: any) {
    return `JSON 格式错误：${e.message}`
  }
}

function paramPlaceholder(p: DatasetParam) {
  if (p.type === 'array' || p.type === 'object')
    return '池中无值；JSON 数组/对象文本'
  return '池中无值；留空时发送空值（运行时变量需 ${} 显式引用）'
}

async function saveValues() {
  if (!current.value) return
  // 有 JSON 语法错误时阻止保存（提示第一个错误字段；池值 + 节点覆盖值都查）
  for (const [k, v] of Object.entries(editingValues.value)) {
    const err = jsonError(v)
    if (err) {
      ElMessage.error(`池值 ${colLabel(k)}：${err}`)
      return
    }
  }
  for (const [nid, m] of Object.entries(nodeEdits.value)) {
    const dyn = dynamicKeysByNode.value[nid] || new Set<string>()
    for (const [k, v] of Object.entries(m)) {
      if (dyn.has(k)) continue  // 动态绑定（${}）只读展示，非 JSON 文本不校验
      const err = jsonError(v)
      if (err) {
        const label = view.value?.nodes.find((n) => n.node_id === nid)?.label || nid
        ElMessage.error(`${label} / ${colLabel(k)}：${err}`)
        return
      }
    }
  }
  // 节点级脏检测：改动即该节点手动覆盖（写 pre_process 字面量，压过池值）；
  // 清空 = 移除覆盖回落池值；动态绑定键只读不参与
  const nodeSaves: { node_id: string; sets: Record<string, any>; clears: string[] }[] = []
  for (const [nid, m] of Object.entries(nodeEdits.value)) {
    const base = nodeBaselines.value[nid] || {}
    const dyn = dynamicKeysByNode.value[nid] || new Set<string>()
    const sets: Record<string, any> = {}
    const clears: string[] = []
    for (const [k, v] of Object.entries(m)) {
      // 两侧统一 String 再比：池值 number/bool 经 _ser 原样保留非字符串，
      // 若只 String 一侧，String(123) !== 123 恒真 → 未改动的参数被误判脏，
      // 保存时整批写成节点 set_field 字面量（污染用例前置处理）
      if (k in base && String(v) !== String(base[k]) && !dyn.has(k)) {
        if (v === '' || v === null || v === undefined) clears.push(k)
        else sets[k] = _parse(v)
      }
    }
    if (Object.keys(sets).length || clears.length) nodeSaves.push({ node_id: nid, sets, clears })
  }
  // JSON 文本还原为对象/数组；空串保持空串（未配置语义）
  const values: Record<string, any> = {}
  Object.entries(editingValues.value).forEach(([k, v]) => {
    if (isJsonText(v)) {
      try {
        values[k] = JSON.parse(v)
        return
      } catch {
        // 上方已校验，这里不会走到
      }
    }
    values[k] = v
  })
  savingValues.value = true
  try {
    const columnTypes = Object.keys(addedVarTypes.value).length ? { ...addedVarTypes.value } : undefined
    await datasetApi.saveValues(current.value.id, values, columnTypes)
    for (const ns of nodeSaves) {
      await datasetApi.saveNodeValues(current.value.id, ns.node_id, ns.sets, ns.clears)
    }
    ElMessage.success('已保存')
    await load()
    if (current.value) await loadParamsView(current.value.id)
  } catch (e: any) {
    ElMessage.error(e.message || '保存失败')
  } finally {
    savingValues.value = false
  }
}

// ===== file 参数取值：文件中心选择器（值存文件 ID） =====
const filePickerVisible = ref(false)
const filePickerKey = ref('')
const filePickerNode = ref<string | null>(null)  // null = 池总览；节点页签 = 该节点覆盖

function openFilePicker(key: string) {
  filePickerKey.value = key
  filePickerNode.value = activeNodeId.value === '__all__' ? null : activeNodeId.value
  filePickerVisible.value = true
}

function onFileSelect(file: TestFile) {
  if (filePickerKey.value) {
    const id = String(file.id)
    fileNames.value[id] = file.name || file.original_name || `#${file.id}`
    if (filePickerNode.value) {
      const m = nodeEdits.value[filePickerNode.value]
      if (m) m[filePickerKey.value] = id
    } else {
      editingValues.value[filePickerKey.value] = id
    }
  }
  filePickerKey.value = ''
  filePickerNode.value = null
}

// ===== 左侧用例分组树（沿用用例列表的分组结构；树构建与展开记忆收敛进 useGroupTree）=====
const UNGROUPED_ID = -1
const {
  tree: groupTree,
  isExpanded,
  toggleExpand: toggleGroup,
  expandedIds,
} = useGroupTree(groups, computed(() => store.currentProjectId), 'datasetManage')
// 未分组（-1 虚拟节点）不在 useGroupTree 的树里：与真实分组共用 expandedIds，
// 同一持久化 key（fin_group_expand_datasetManage_{projectId}），展开/折叠语义一致

function casesOfGroup(gid: number | null) {
  return cases.value.filter((c) => (c.group_id ?? null) === gid)
}

/** 分组可展开：有子分组或组内直接有用例（叶子分组折叠用例列表） */
function groupHasContent(id: number) {
  if (id === UNGROUPED_ID) return casesOfGroup(null).length > 0
  return groups.value.some((g) => g.parent_id === id) || casesOfGroup(id).length > 0
}

/** 分组节点计数：组内直接用例 + 全部子孙分组用例的数据集合计
 *  （父分组自身无直接用例时不再显示 0——用例都在子分组里是常态） */
function groupDatasetCount(id: number) {
  const sum = (gid: number | null) =>
    casesOfGroup(gid).reduce((n, c) => n + caseDatasetCount(c.id), 0)
  if (id === UNGROUPED_ID) return sum(null)
  // BFS 收集该分组及全部后代分组（分组规模小，数组去重足够）
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

// 字段名统一展示约定（全站一致）：原始 key + 字典中文名（如有）。
// dictLabel 来自 useFieldDict（含嵌套路径完整/末段/父级段匹配），不再本地弱化重写。
function colLabel(key: string) {
  const cn = dictLabel(key)
  return cn ? `${key}（${cn}）` : key
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
    // 套件不参与数据集（成员各自绑定变量池），左侧用例树不展示
    cases.value = cs.filter((c) => c.case_type !== 'suite')
    groups.value = gs
    datasets.value = ds
    // 展开记忆优先（useGroupTree 随 projectId 变化自动读写）；首次（无记忆）
    // 默认全展开（含未分组虚拟节点）并落记忆
    if (localStorage.getItem(expandStorageKey('datasetManage', store.currentProjectId)) === null) {
      expandedIds.value = [...gs.map((g) => g.id), UNGROUPED_ID]
    }
    if (currentCase.value) {
      currentCase.value = cases.value.find((c) => c.id === currentCase.value!.id) || null
    }
    if (!currentCase.value && cases.value.length) currentCase.value = cases.value[0]
    if (current.value) {
      current.value = caseDatasets.value.find((d) => d.id === current.value!.id) || null
    }
    if (!current.value && caseDatasets.value.length) current.value = caseDatasets.value[0]
    if (current.value) await loadParamsView(current.value.id)
  } catch (e: any) {
    loadError.value = e.message || '加载失败'
  } finally {
    loading.value = false
  }
}

function selectCase(c: TestCase) {
  currentCase.value = c
  current.value = caseDatasets.value[0] || null
  if (current.value) loadParamsView(current.value.id)
  else view.value = null
}

function select(d: DataSet) {
  current.value = d
  loadParamsView(d.id)
}

// ---------- 数据集信息（名称/描述）编辑 ----------
const dlgVisible = ref(false)
const form = ref<{ name: string; description: string }>({ name: '', description: '' })

function openEdit(d: DataSet) {
  form.value = { name: d.name, description: d.description || '' }
  dlgVisible.value = true
}

async function save() {
  if (!form.value.name.trim()) return ElMessage.warning('请填写名称')
  if (!current.value) return
  saving.value = true
  try {
    await datasetApi.update(current.value.id, {
      name: form.value.name, description: form.value.description,
    })
    ElMessage.success('已保存')
    dlgVisible.value = false
    await load()
    current.value = caseDatasets.value.find((d) => d.id === current.value!.id) || current.value
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
        : `确认删除数据集「${d.name}」及其单套数据？`,
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

// ---------- 复制（隔离语义下的复用） ----------
async function copyDataset() {
  if (!current.value) return
  try {
    const nd = await datasetApi.copy(current.value.id)
    ElMessage.success(`已复制为「${nd.name}」`)
    await load()
    current.value = caseDatasets.value.find((d) => d.id === nd.id) || current.value
    if (current.value) loadParamsView(current.value.id)
  } catch (e: any) {
    ElMessage.error(e.message || '复制失败')
  }
}

// ---------- 从其他数据集覆盖（节点级对比合并） ----------
const mergeVisible = ref(false)
const mergeSourceId = ref<number | null>(null)
const mergeLoading = ref(false)
const merging = ref(false)
const mergePreviewData = ref<Awaited<ReturnType<typeof datasetApi.mergePreview>> | null>(null)
const mergeSelectedApis = ref<number[]>([])
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
    ElMessage.error(e.message || '对比失败')
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
    })
    ElMessage.success(`${res.message}：${res.keys.slice(0, 8).join('、')}${res.keys.length > 8 ? '…' : ''}`)
    mergeVisible.value = false
    await load()
    if (current.value) await loadParamsView(current.value.id)
  } catch (e: any) {
    ElMessage.error(e.message || '覆盖合并失败')
  } finally {
    merging.value = false
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
.main-actions {
  margin-left: auto;
  display: flex;
  gap: 8px;
  align-items: center;
  flex-shrink: 0;
}
.tip {
  color: var(--app-text-muted);
  font-size: 12px;
}
/* 变量池视图：节点页签 + 参数状态徽标 */
.params-area {
  min-height: 120px;
}
.orphan-tip {
  margin-bottom: 10px;
}
.pool-stat {
  display: flex;
  align-items: center;
  gap: 16px;
  font-size: 12px;
  color: var(--app-text-muted);
  margin-bottom: 8px;
}
.pool-stat b {
  color: var(--app-primary);
}
.stat-note {
  color: var(--app-text-faint);
}
.pool-search {
  width: 220px;
  margin-left: auto;
}
.add-var-btn {
  flex-shrink: 0;
}
/* 作用域就近提示：双作用域编辑是本页核心心智模型 */
.scope-tip {
  font-size: 12px;
  color: var(--app-text-muted);
  background: var(--app-hover);
  border-radius: var(--app-radius-sm);
  padding: 4px 10px;
  margin: 8px 0 2px;
}
.save-dock {
  position: fixed;
  left: 50%;
  transform: translateX(-50%);
  bottom: 18px;
  z-index: 100;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 18px;
  background: var(--app-card);
  border: 1px solid var(--app-border);
  border-radius: 8px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.14);
}
.save-dock-text {
  font-size: 13px;
  color: var(--app-text);
}
.del-var-btn {
  margin-left: auto;
  margin-right: -6px;
}
.node-tabs {
  border-top: 1px solid var(--app-border);
}
.tab-label {
  max-width: 160px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  vertical-align: middle;
}
.tab-cnt {
  margin-left: 6px;
  font-size: 11px;
  color: var(--app-text-faint);
  vertical-align: middle;
}
.node-params {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
  gap: 12px 20px;
  padding: 8px 2px 4px;
}
.param-row {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.param-row.manual .param-label {
  color: var(--app-text-muted);
}
.param-label {
  font-size: 12px;
  color: var(--app-text);
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}
.col-type-tag {
  font-size: 11px;
  color: var(--app-text-muted);
  border: 1px solid var(--el-border-color);
  border-radius: 3px;
  padding: 0 4px;
}
/* 参数状态徽标（四态） */
.badge {
  font-size: 11px;
  border-radius: 3px;
  padding: 0 5px;
  border: 1px solid;
  cursor: help;
  line-height: 18px;
  white-space: nowrap;
}
.badge-filled {
  color: var(--el-color-success);
  border-color: var(--el-color-success);
}
.badge-dynamic {
  color: var(--el-color-primary);
  border-color: var(--el-color-primary);
}
.badge-empty {
  color: var(--app-text-muted);
  border-color: var(--app-border);
  background: var(--app-hover);
}
.badge-manual {
  color: var(--el-color-warning);
  border-color: var(--el-color-warning);
}
.json-err {
  font-size: 12px;
  color: var(--el-color-danger);
}
.pool-tip {
  margin-top: 10px;
  color: var(--app-text-muted);
  font-size: 12px;
  line-height: 2;
}
.pool-tip .badge {
  cursor: default;
}
.pool-tip .help-link {
  padding: 2px 6px;
  font-size: 12px;
  margin-left: 4px;
}
.file-value-cell {
  display: flex;
  align-items: center;
  gap: 4px;
  width: 100%;
}
.file-value-input {
  flex: 1;
}
/* 覆盖合并弹窗 */
.import-actions {
  margin: 8px 0 4px;
  display: flex;
  justify-content: flex-end;
}
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

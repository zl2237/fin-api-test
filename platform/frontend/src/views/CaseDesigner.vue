<template>
  <div class="designer" v-loading="loading" element-loading-text="加载用例编排数据中...">
    <!-- 左侧接口列表（按分组树折叠，继承接口管理的分组与排序） -->
    <div class="api-panel">
      <div class="panel-title">
        <el-button link @click="onBack">
          <el-icon><ArrowLeft /></el-icon>返回
        </el-button>
        <span class="title-text">接口列表</span>
      </div>
      <div class="api-list">
        <div
          v-for="row in visibleGroupRows"
          :key="row.key"
          class="group-block"
        >
          <!-- 分组头（可折叠/展开） -->
          <div
            class="group-header"
            :style="{ paddingLeft: 12 + row.depth * 16 + 'px' }"
            @click="onToggleGroup(row)"
          >
            <el-icon
              v-if="row.expandable"
              class="expand-icon"
              :class="{ expanded: isGroupExpanded(row.groupId!) }"
            ><CaretRight /></el-icon>
            <span v-else class="expand-spacer" />
            <el-icon class="group-icon"><Files /></el-icon>
            <span class="group-name">{{ row.name }}</span>
            <span class="group-count">{{ row.isUngrouped ? apisOf(null).length : countApisWithDescendants(row.groupId!) }}</span>
          </div>
          <!-- 分组下的直接接口（仅展开时显示；无直接接口时不渲染，避免显示 No Data） -->
          <div
            v-if="row.isUngrouped || isGroupExpanded(row.groupId!)"
            :style="{ paddingLeft: 12 + row.depth * 16 + 'px' }"
          >
            <div
              v-for="a in apisOf(row.groupId)"
              :key="a.id"
              class="api-item"
              @click="onAddNode(a)"
            >
              <div class="api-item-name">{{ a.name }}</div>
              <div class="api-item-path">{{ a.method }} {{ a.path }}</div>
            </div>
          </div>
        </div>
        <EmptyState v-if="!apiList.length" description="暂无接口，请先到接口管理新增" :image-size="60" />
      </div>
    </div>

    <!-- 中央画布 -->
    <div class="canvas-wrap">
      <div class="canvas-toolbar">
        <div class="toolbar-left">
          <el-button link @click="onBack">
            <el-icon><ArrowLeft /></el-icon>返回列表
          </el-button>
          <el-input v-model="caseData.name" style="width: 260px" placeholder="用例名称" />
        </div>
        <div class="toolbar-right">
          <span class="dirty-tip">{{ dirty ? '有未保存改动' : '已保存' }}</span>
          <el-select
            v-model="store.currentEnvId"
            placeholder="选择环境"
            size="default"
            style="width: 160px"
            :disabled="!store.environments.length"
          >
            <template #prefix>
              <el-icon><Connection /></el-icon>
            </template>
            <el-option
              v-for="e in store.environments"
              :key="e.id"
              :label="e.name"
              :value="e.id"
            />
          </el-select>
          <el-button @click="onAutoLayout">自动布局</el-button>
          <el-button
            :type="linkMode ? 'warning' : 'default'"
            @click="onToggleLinkMode"
          >
            {{ linkMode ? linkHint : '连线模式' }}
          </el-button>
          <el-button type="primary" :loading="saving" @click="onSave">保存用例</el-button>
          <el-button type="success" :loading="running" @click="onRun">执行</el-button>
        </div>
      </div>
      <DagCanvas
        ref="canvasRef"
        v-model:nodes="nodes"
        v-model:edges="edges"
        @node-open="onNodeOpen"
        @nodes-pasted="onNodesPasted"
        @link-mode-change="onLinkModeChange"
      />
      <div class="canvas-hint">
        提示：点击接口添加节点；单击选中、双击或按 Enter 打开节点配置；Ctrl+C/V 复制粘贴节点；可拖拽节点右侧端点连线到目标左侧端点；或点「连线模式」后依次点击两个节点；点击连线删除。
      </div>
    </div>

    <!-- 节点配置抽屉 -->
    <NodeConfigDrawer
      v-model:visible="drawerVisible"
      :config="currentConfig"
      :apis="apiList"
      @save="onConfigSave"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch, toRef } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowLeft, Connection, Files, CaretRight } from '@element-plus/icons-vue'
import DagCanvas from '@/components/DagCanvas.vue'
import NodeConfigDrawer from '@/components/NodeConfigDrawer.vue'
import { caseApi, apiApi, apiGroupApi, execApi, type ApiDef, type ApiGroup, type TestCase, type NodeConfig } from '@/api'
import { useAppStore } from '@/stores'
import { useGroupTree, collectDescendantIds, type FlatGroup } from '@/composables/useGroupTree'
import { useFaviconStatus } from '@/composables/useFaviconStatus'
import EmptyState from '@/components/EmptyState.vue'

const favicon = useFaviconStatus()

const route = useRoute()
const router = useRouter()
const store = useAppStore()

// 追踪执行轮询定时器，组件卸载时统一清理，避免切页后继续请求已失效的执行记录
const pollTimers: ReturnType<typeof setTimeout>[] = []

const apiList = ref<ApiDef[]>([])
const apiGroups = ref<ApiGroup[]>([])

// ===== 多级分组树（继承接口管理的分组层级与排序） =====
const flatGroups = computed<FlatGroup[]>(() =>
  apiGroups.value.map((g) => ({ id: g.id, parent_id: g.parent_id, name: g.name, sort_order: g.sort_order })),
)
const {
  tree,
  isExpanded: isGroupExpanded,
  toggleExpand: toggleGroupExpand,
  applyDefaultExpand,
  computeVisibleRows,
} = useGroupTree(flatGroups, toRef(store, 'currentProjectId'), 'caseDesigner')

/** 主列表可见行：树扁平化 + 祖先展开可见性 + 未分组行（叶子分组有数据也可展开） */
const visibleGroupRows = computed(() => computeVisibleRows(apiList.value.some((a) => !a.group_id), (id) => apisOf(id).length))

/** 统计分组的接口数量（含所有子孙分组） */
function countApisWithDescendants(groupId: number): number {
  const ids = [groupId, ...collectDescendantIds(tree.value, groupId)]
  return apiList.value.filter((a) => a.group_id != null && ids.includes(a.group_id)).length
}

/** 获取分组的直接接口 */
function apisOf(groupId: number | null): ApiDef[] {
  if (groupId === null) return apiList.value.filter((a) => !a.group_id)
  return apiList.value.filter((a) => a.group_id === groupId)
}

/** 切换分组展开/折叠（未分组行与不可展开的空分组不响应） */
function onToggleGroup(row: { groupId: number | null; isUngrouped: boolean; expandable?: boolean }) {
  if (row.isUngrouped || row.groupId == null || row.expandable === false) return
  toggleGroupExpand(row.groupId)
}
const caseData = ref<TestCase>(emptyCase())
const nodes = ref<any[]>([])
const edges = ref<any[]>([])
const configs = ref<NodeConfig[]>([])
const canvasRef = ref<any>(null)
const drawerVisible = ref(false)
const selectedNodeId = ref<string | null>(null)
const saving = ref(false)
const running = ref(false)
const dirty = ref(false)
const loading = ref(false)
const linkMode = ref(false)
const linkSourceSelected = ref(false)

function emptyCase(): TestCase {
  return {
    id: 0,
    project_id: store.currentProjectId || 0,
    name: '',
    description: '',
    dag_config: { nodes: [], edges: [] },
    node_configs: [],
  }
}

const linkHint = computed(() => {
  if (!linkSourceSelected.value) return '连线模式：点击源节点'
  return '连线模式：点击目标节点'
})

const currentConfig = computed<NodeConfig>(() => {
  if (!selectedNodeId.value) {
    return { node_id: '', api_id: null, pre_process: [], post_extract: [], assertions: [], wait_after_ms: 0 }
  }
  const found = configs.value.find((c) => c.node_id === selectedNodeId.value)
  if (found) return found
  const fresh: NodeConfig = {
    node_id: selectedNodeId.value,
    api_id: null,
    pre_process: [],
    post_extract: [],
    assertions: [],
    wait_after_ms: 0,
  }
  configs.value.push(fresh)
  return fresh
})

async function loadApis() {
  if (!store.currentProjectId) return
  apiList.value = await apiApi.list(store.currentProjectId)
}

async function loadApiGroups() {
  if (!store.currentProjectId) return
  apiGroups.value = await apiGroupApi.list(store.currentProjectId)
  // 无记忆时默认全部展开
  applyDefaultExpand()
}

async function loadCase(id: number) {
  const c = await caseApi.get(id)
  caseData.value = c
  // 加载节点时，用最新接口信息同步节点的 label/method/path
  // 避免接口名称修改后，用例内节点的旧名称仍残留
  nodes.value = (c.dag_config?.nodes || []).map((n: any) => {
    const apiId = n.data?.api_id
    const api = apiId ? apiList.value.find(a => a.id === apiId) : null
    if (!api) return { ...n }
    return {
      ...n,
      data: { ...n.data, label: api.name, api_method: api.method, api_path: api.path },
      label: api.name,
    }
  })
  edges.value = (c.dag_config?.edges || []).map((e: any) => ({ ...e }))
  configs.value = (c.node_configs || []).map((nc: NodeConfig) => ({ ...nc }))
  dirty.value = false
}

function onBack() {
  router.push('/cases')
}

function onAddNode(api: ApiDef) {
  const id = `node_${Date.now()}`
  // 从画布获取一个空闲位置（视口中心附近，避免覆盖已有节点）
  const position = canvasRef.value?.findFreePosition?.() ?? { x: 80, y: 60 }
  const node = {
    id,
    position,
    data: { label: api.name, api_id: api.id, api_method: api.method, api_path: api.path },
    label: api.name,
  }
  nodes.value.push(node)
  canvasRef.value?.addNode(node)
  configs.value.push({
    node_id: id,
    api_id: api.id,
    pre_process: [],
    post_extract: [],
    assertions: [],
    wait_after_ms: 0,
  })
  dirty.value = true
}

/** 双击/回车打开节点配置抽屉 */
function onNodeOpen(id: string) {
  if (linkMode.value) return
  selectedNodeId.value = id
  drawerVisible.value = true
}

/** 粘贴节点：克隆对应 config（深拷贝 pre_process/post_extract/assertions 避免共享引用） */
function onNodesPasted(mapping: { oldId: string; newId: string }[]) {
  for (const { oldId, newId } of mapping) {
    const src = configs.value.find((c) => c.node_id === oldId)
    if (src) {
      configs.value.push(JSON.parse(JSON.stringify({
        ...src,
        node_id: newId,
      })))
    }
  }
  dirty.value = true
}

function onConfigSave(_config: NodeConfig) {
  const idx = configs.value.findIndex((c) => c.node_id === _config.node_id)
  if (idx >= 0) configs.value[idx] = { ..._config }
  dirty.value = true
}

function onAutoLayout() {
  canvasRef.value?.autoLayout()
  dirty.value = true
}

function onToggleLinkMode() {
  const newMode = canvasRef.value?.toggleLinkMode()
  linkMode.value = newMode
  linkSourceSelected.value = false
  if (newMode) {
    ElMessage.info('连线模式已开启：依次点击源节点和目标节点')
    // 监听源节点选择状态
    watch(
      () => canvasRef.value?.linkSourceId,
      (v) => { linkSourceSelected.value = !!v },
      { immediate: true }
    )
  } else {
    ElMessage.info('连线模式已关闭')
  }
}

// DagCanvas 内部 Esc 退出 linkMode 时同步本组件状态
function onLinkModeChange(active: boolean) {
  linkMode.value = active
  if (!active) {
    linkSourceSelected.value = false
  }
}

// 画布变更同步
watch(nodes, () => { dirty.value = true }, { deep: true })
watch(edges, () => { dirty.value = true }, { deep: true })

async function onSave() {
  if (!caseData.value.id) {
    ElMessage.warning('请从用例列表进入编排')
    return
  }
  saving.value = true
  try {
    // 保存前 trim 后置提取的字符串字段，防止前后空格导致后续注入失败
    const cleanedConfigs = configs.value.map((c: NodeConfig) => ({
      ...c,
      post_extract: (c.post_extract || []).map((r: any) => ({
        ...r,
        name: typeof r.name === 'string' ? r.name.trim() : r.name,
        json_path: typeof r.json_path === 'string' ? r.json_path.trim() : r.json_path,
        sql: typeof r.sql === 'string' ? r.sql.trim() : r.sql,
        field: typeof r.field === 'string' ? r.field.trim() : r.field,
      })),
    }))
    const payloadNodes = nodes.value.map((n: any) => ({
      id: n.id,
      position: n.position,
      data: n.data,
      label: n.label,
    }))
    await caseApi.update(caseData.value.id, {
      name: caseData.value.name,
      dag_config: { nodes: payloadNodes, edges: edges.value },
      node_configs: cleanedConfigs,
    })
    // 同步回本地，保持 UI 与已保存数据一致
    configs.value = cleanedConfigs
    dirty.value = false
    ElMessage.success('已保存')
  } catch (e: any) {
    ElMessage.error(e.message)
  } finally {
    saving.value = false
  }
}

async function onRun() {
  if (!caseData.value.id) return ElMessage.warning('请先保存用例')
  if (!store.currentEnvId) return ElMessage.warning('请先在工具栏选择环境')
  await onSave()
  running.value = true
  try {
    // 异步执行：立即返回 running，后台线程池执行，前端轮询状态
    const rec = await caseApi.execute(caseData.value.id, store.currentEnvId)
    const execId = rec.id
    favicon.running()
    const msg = ElMessage({
      message: '执行中...',
      type: 'info',
      duration: 0,
    })
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
      } finally {
        if (pollCount >= maxPolls) running.value = false
      }
    }
    const t = setTimeout(poll, 2000)
    pollTimers.push(t)
  } catch (e: any) {
    favicon.reset()
    ElMessage.error(e.message)
    running.value = false
  }
}

onMounted(async () => {
  // 编辑模式加载数据期间显示遮罩，避免空白无反馈
  const id = Number(route.params.id)
  loading.value = !!id
  try {
    await loadApis()
    await loadApiGroups()
    if (id) await loadCase(id)
  } finally {
    loading.value = false
  }
  window.addEventListener('keydown', onKeydown)
})
onUnmounted(() => {
  window.removeEventListener('keydown', onKeydown)
  // 清理所有执行轮询定时器，防止切页后继续请求
  pollTimers.forEach(t => clearTimeout(t))
  pollTimers.length = 0
})

function onKeydown(e: KeyboardEvent) {
  if ((e.ctrlKey || e.metaKey) && e.key === 's') {
    e.preventDefault()
    onSave()
  }
}

watch(() => store.currentProjectId, async () => {
  await loadApis()
  await loadApiGroups()
})
</script>

<style scoped>
.designer {
  display: flex;
  gap: 12px;
  height: calc(100vh - 100px);
}
.api-panel {
  width: 280px;
  background: var(--app-card);
  backdrop-filter: saturate(180%) blur(20px);
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.panel-title {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 14px;
  font-weight: 600;
  font-size: 13px;
  border-bottom: 1px solid var(--app-border);
}
.title-text {
  flex: 1;
}
.api-list {
  flex: 1;
  overflow: auto;
  padding: 8px;
}
.group-block {
  margin-bottom: 4px;
}
.group-header {
  display: flex;
  align-items: center;
  gap: 6px;
  height: 34px;
  padding-right: 12px;
  cursor: pointer;
  border-radius: var(--app-radius-md);
  transition: background 0.15s;
}
.group-header:hover {
  background: var(--app-chip-bg);
}
.expand-icon {
  font-size: 12px;
  color: var(--app-text-muted);
  flex-shrink: 0;
  transition: transform 0.18s ease;
}
.expand-icon.expanded {
  transform: rotate(90deg);
}
.expand-spacer {
  width: 12px;
  flex-shrink: 0;
}
.group-icon {
  font-size: 14px;
  color: var(--app-primary);
  flex-shrink: 0;
}
.group-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--app-text);
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.group-count {
  background: var(--app-primary);
  color: #fff;
  border-radius: 10px;
  padding: 1px 8px;
  font-size: 11px;
  font-weight: 500;
  min-width: 20px;
  text-align: center;
  flex-shrink: 0;
}
.api-item {
  padding: 8px 14px;
  cursor: pointer;
  transition: background 0.15s;
  border-left: 2px solid transparent;
}
.api-item:hover {
  background: var(--app-chip-bg);
  border-left-color: var(--el-color-primary);
}
.api-item-name {
  font-size: 13px;
  font-weight: 500;
}
.api-item-path {
  font-size: 11px;
  color: var(--app-text-muted);
  margin-top: 2px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.canvas-wrap {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-width: 0;
}
.canvas-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: var(--app-card);
  backdrop-filter: saturate(180%) blur(20px);
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius);
  padding: 10px 14px;
}
.toolbar-left {
  display: flex;
  align-items: center;
  gap: 12px;
}
.toolbar-right {
  display: flex;
  align-items: center;
  gap: 10px;
}
.dirty-tip {
  font-size: 12px;
  color: var(--app-text-muted);
}
.canvas-hint {
  font-size: 12px;
  color: var(--app-text-muted);
  padding: 0 4px;
}
:deep(.canvas-wrap .dag-canvas) {
  flex: 1;
  border: 1px solid var(--app-border);
}
</style>

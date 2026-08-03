<template>
  <div class="designer">
    <!-- 左侧接口列表（按分组折叠） -->
    <div class="api-panel">
      <div class="panel-title">
        <el-button link @click="onBack">
          <el-icon><ArrowLeft /></el-icon>返回
        </el-button>
        <span class="title-text">接口列表</span>
      </div>
      <div class="api-list">
        <el-collapse v-model="activeApiGroups" class="api-collapse">
          <el-collapse-item
            v-for="g in groupedApis"
            :key="g.group?.id ?? 'ungrouped'"
            :name="g.group?.id ?? 'ungrouped'"
          >
            <template #title>
              <div class="api-group-title">
                <span>{{ g.group?.name || '未分组' }}</span>
                <span class="api-group-count">{{ g.apis.length }}</span>
              </div>
            </template>
            <div
              v-for="a in g.apis"
              :key="a.id"
              class="api-item"
              @click="onAddNode(a)"
            >
              <div class="api-item-name">{{ a.name }}</div>
              <div class="api-item-path">{{ a.method }} {{ a.path }}</div>
            </div>
            <el-empty v-if="!g.apis.length" description="无接口" :image-size="40" />
          </el-collapse-item>
        </el-collapse>
        <el-empty v-if="!apiList.length" description="暂无接口，请先到接口管理新增" :image-size="60" />
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
        @node-click="onNodeClick"
        @link-mode-change="onLinkModeChange"
      />
      <div class="canvas-hint">
        提示：点击接口添加节点；可拖拽节点右侧端点连线到目标左侧端点；或点「连线模式」后依次点击两个节点；点击连线删除。
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
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowLeft, Connection } from '@element-plus/icons-vue'
import DagCanvas from '@/components/DagCanvas.vue'
import NodeConfigDrawer from '@/components/NodeConfigDrawer.vue'
import { caseApi, apiApi, apiGroupApi, execApi, type ApiDef, type ApiGroup, type TestCase, type NodeConfig } from '@/api'
import { useAppStore } from '@/stores'

const route = useRoute()
const router = useRouter()
const store = useAppStore()

const apiList = ref<ApiDef[]>([])
const apiGroups = ref<ApiGroup[]>([])
const activeApiGroups = ref<(number | string)[]>([])
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

const groupedApis = computed(() => {
  const result: { group: ApiGroup | null; apis: ApiDef[] }[] = []
  for (const g of apiGroups.value) {
    const list = apiList.value.filter(a => a.group_id === g.id)
    result.push({ group: g, apis: list })
  }
  const ungrouped = apiList.value.filter(a => !a.group_id)
  if (ungrouped.length) {
    result.push({ group: null, apis: ungrouped })
  }
  return result
})

const currentConfig = computed<NodeConfig>(() => {
  if (!selectedNodeId.value) {
    return { node_id: '', api_id: null, pre_process: [], post_extract: [], assertions: [] }
  }
  const found = configs.value.find((c) => c.node_id === selectedNodeId.value)
  if (found) return found
  const fresh: NodeConfig = {
    node_id: selectedNodeId.value,
    api_id: null,
    pre_process: [],
    post_extract: [],
    assertions: [],
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
  activeApiGroups.value = apiGroups.value.map(g => g.id)
  if (apiList.value.some(a => !a.group_id)) {
    activeApiGroups.value.push('ungrouped')
  }
}

async function loadCase(id: number) {
  const c = await caseApi.get(id)
  caseData.value = c
  nodes.value = (c.dag_config?.nodes || []).map((n: any) => ({ ...n }))
  edges.value = (c.dag_config?.edges || []).map((e: any) => ({ ...e }))
  configs.value = (c.node_configs || []).map((nc: NodeConfig) => ({ ...nc }))
  dirty.value = false
}

function onBack() {
  router.push('/cases')
}

function onAddNode(api: ApiDef) {
  const id = `node_${Date.now()}`
  const count = nodes.value.length
  const node = {
    id,
    position: { x: 80 + (count % 5) * 200, y: 60 + Math.floor(count / 5) * 120 },
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
  })
  dirty.value = true
}

function onNodeClick(id: string) {
  if (linkMode.value) {
    // 连线模式下，通过 watch canvasRef.linkSourceId 判断
    // 这里简单处理：不打开抽屉
    return
  }
  selectedNodeId.value = id
  drawerVisible.value = true
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
    const payloadNodes = nodes.value.map((n: any) => ({
      id: n.id,
      position: n.position,
      data: n.data,
      label: n.label,
    }))
    await caseApi.update(caseData.value.id, {
      name: caseData.value.name,
      dag_config: { nodes: payloadNodes, edges: edges.value },
      node_configs: configs.value,
    })
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
        const cur = await execApi.get(execId)
        if (cur.status === 'running' && pollCount < maxPolls) {
          setTimeout(poll, 2000)
        } else {
          msg.close()
          if (cur.status === 'success') {
            ElMessage.success(`执行通过：${cur.summary.passed}/${cur.summary.total}`)
          } else if (pollCount >= maxPolls) {
            ElMessage.warning('执行超时，请到执行记录查看结果')
          } else {
            ElMessage.warning(`执行失败：${cur.summary.failed} 项未通过`)
          }
          router.push(`/reports/${execId}`)
        }
      } catch (e: any) {
        msg.close()
        ElMessage.error(e.message || '轮询执行状态失败')
      } finally {
        if (pollCount >= maxPolls) running.value = false
      }
    }
    setTimeout(poll, 2000)
  } catch (e: any) {
    ElMessage.error(e.message)
    running.value = false
  }
}

onMounted(async () => {
  await loadApis()
  await loadApiGroups()
  const id = Number(route.params.id)
  if (id) await loadCase(id)
  window.addEventListener('keydown', onKeydown)
})
onUnmounted(() => {
  window.removeEventListener('keydown', onKeydown)
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
  padding: 4px 0;
}
.api-collapse {
  border: none;
}
.api-group-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-right: 8px;
  font-size: 13px;
  font-weight: 600;
  color: var(--app-text);
}
.api-group-count {
  background: var(--app-tag-bg);
  color: var(--app-text-muted);
  border-radius: 10px;
  padding: 1px 8px;
  font-size: 11px;
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
:deep(.api-collapse .el-collapse-item__header) {
  padding: 0 12px;
  height: 36px;
  line-height: 36px;
}
:deep(.api-collapse .el-collapse-item__content) {
  padding-bottom: 0;
}
</style>

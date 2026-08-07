<template>
  <div class="dag-canvas">
    <VueFlow
      :nodes="nodes"
      :edges="edges"
      :fit-view-on-init="true"
      @connect="onConnect"
      @node-click="onNodeClick"
      @node-drag-stop="emitChange"
      @edge-click="onEdgeClick"
    >
      <Background pattern-color="#aaa" :gap="16" />
      <Controls />
      <MiniMap />
      <template #node-default="props">
        <div class="dag-node" :class="{
          selected: props.selected,
          'link-source': linkSourceId === props.id,
          'link-target': linkMode && linkSourceId && linkSourceId !== props.id
        }">
          <!-- 源连接点（右侧） -->
          <Handle id="source" type="source" :position="Position.Right" class="dag-handle source-handle" />
          <!-- 目标连接点（左侧） -->
          <Handle id="target" type="target" :position="Position.Left" class="dag-handle target-handle" />
          <div class="dag-node-title">{{ props.data.label || props.id }}</div>
          <div class="dag-node-sub">{{ props.data.api_method }} {{ props.data.api_path }}</div>
        </div>
      </template>
    </VueFlow>
    <!-- 连线模式状态栏 -->
    <div v-if="linkMode" class="link-status-bar">
      <span v-if="!linkSourceId">连线模式：点击源节点（source）</span>
      <span v-else>已选源节点，点击目标节点（target）完成连线 · 按 Esc 取消</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted } from 'vue'
import { VueFlow, useVueFlow, Position, Handle } from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'
import { MiniMap } from '@vue-flow/minimap'
import { ElMessage } from 'element-plus'

const props = defineProps<{ nodes: any[]; edges: any[] }>()
const emit = defineEmits<{
  (e: 'update:nodes', v: any[]): void
  (e: 'update:edges', v: any[]): void
  (e: 'node-click', id: string): void
  (e: 'link-mode-change', active: boolean): void
}>()

const { setNodes, setEdges, addEdges, removeEdges, removeNodes, getNodes, getEdges, fitView } = useVueFlow()

// 防止内部变化触发 emit 后又同步回内部造成循环
const syncing = ref(false)

// 连线模式：选中源节点后再点目标节点连线
const linkMode = ref(false)
const linkSourceId = ref<string | null>(null)

// 键盘事件：
// - Esc：linkMode 下重置已选 source 或退出模式
// - Delete/Backspace：删除当前选中的节点（连线模式下不触发，避免误删）
function onKeydown(e: KeyboardEvent) {
  // Esc 键撤销：linkMode 下重置已选 source 或退出模式
  if (e.key === 'Escape' && linkMode.value) {
    if (linkSourceId.value) {
      // 已选 source → 重置 source，保留 linkMode
      linkSourceId.value = null
    } else {
      // 未选 source → 退出 linkMode，并通知父组件同步状态
      linkMode.value = false
      emit('link-mode-change', false)
    }
    return
  }
  // Delete/Backspace 删除选中节点
  if ((e.key === 'Delete' || e.key === 'Backspace') && !linkMode.value) {
    // 焦点在输入框/文本域中时不拦截，避免影响文本编辑
    const target = e.target as HTMLElement | null
    if (target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable)) {
      return
    }
    const selected = getNodes.value.filter((n: any) => n.selected)
    if (!selected.length) return
    const ids = selected.map((n: any) => n.id)
    // removeNodes 会自动清理与这些节点相连的边
    removeNodes(ids)
    // 同步变更给父组件
    emit('update:nodes', serializeNodes())
    emit('update:edges', serializeEdges())
    ElMessage.success(`已删除 ${ids.length} 个节点`)
    e.preventDefault()
  }
}
onMounted(() => window.addEventListener('keydown', onKeydown))
onUnmounted(() => window.removeEventListener('keydown', onKeydown))

function serializeNodes() {
  return getNodes.value.map((n: any) => ({
    id: n.id,
    position: { x: n.position.x, y: n.position.y },
    data: { ...n.data },
    label: n.data?.label,
  }))
}
function serializeEdges() {
  return getEdges.value.map((e: any) => ({
    id: e.id,
    source: e.source,
    target: e.target,
  }))
}

function emitChange() {
  if (syncing.value) return
  emit('update:nodes', serializeNodes())
  emit('update:edges', serializeEdges())
}

function onConnect(params: any) {
  addEdges([params])
  emit('update:edges', serializeEdges())
}

function onNodeClick({ node }: any) {
  // 连线模式逻辑
  if (linkMode.value) {
    if (!linkSourceId.value) {
      // 第一次点击：选为源节点
      linkSourceId.value = node.id
      return
    }
    if (linkSourceId.value === node.id) {
      // 再次点击同一个：取消
      linkSourceId.value = null
      return
    }
    // 查重：同方向已存在连线则提示，不重复添加
    const src = linkSourceId.value
    const tgt = node.id
    const exists = getEdges.value.some(
      (e: any) => e.source === src && e.target === tgt,
    )
    if (exists) {
      ElMessage.warning('两节点间已存在该方向连线')
      linkSourceId.value = null
      return
    }
    // 第二次点击：连接源→目标
    const newEdge = {
      id: `e-${src}-${tgt}-${Date.now()}`,
      source: src,
      target: tgt,
    }
    addEdges([newEdge])
    emit('update:edges', serializeEdges())
    // 重置已选 source，保留 linkMode 便于连续连线
    linkSourceId.value = null
    return
  }
  // 普通模式：触发节点点击事件（打开配置抽屉）
  emit('node-click', node.id)
  emitChange()
}

function onEdgeClick({ edge }: any) {
  removeEdges([edge.id])
  emit('update:edges', serializeEdges())
}

function addNode(node: any) {
  setNodes([...getNodes.value, node])
  emit('update:nodes', serializeNodes())
}

// 切换连线模式（供父组件调用）
function toggleLinkMode() {
  linkMode.value = !linkMode.value
  linkSourceId.value = null
  return linkMode.value
}

// 自动布局：按 DAG 拓扑顺序（BFS）将节点填入网格，
// 根据节点总数计算目标行列数，使布局宽高比接近 4:3，避免扁平或瘦长。
function autoLayout() {
  const allNodes = getNodes.value
  const allEdges = getEdges.value
  if (!allNodes.length) return

  // 构建后继邻接表和入度
  const succ = new Map<string, string[]>()
  const indeg = new Map<string, number>()
  for (const n of allNodes) {
    succ.set(n.id, [])
    indeg.set(n.id, 0)
  }
  for (const e of allEdges) {
    if (!succ.has(e.source)) continue
    succ.get(e.source)!.push(e.target)
    indeg.set(e.target, (indeg.get(e.target) || 0) + 1)
  }

  // BFS 拓扑排序：同层节点相邻，保证依赖节点在下方
  const order: string[] = []
  const indegCopy = new Map(indeg)
  let frontier = allNodes.filter(n => (indegCopy.get(n.id) || 0) === 0).map(n => n.id)
  while (frontier.length) {
    order.push(...frontier)
    const next: string[] = []
    for (const id of frontier) {
      for (const s of succ.get(id) || []) {
        indegCopy.set(s, indegCopy.get(s)! - 1)
        if (indegCopy.get(s) === 0) next.push(s)
      }
    }
    frontier = next
  }
  // 未处理的（成环）追加到末尾
  for (const n of allNodes) {
    if (!order.includes(n.id)) order.push(n.id)
  }

  // 网格布局：根据节点数计算目标行列数，使宽高比接近 4:3
  // 节点间距 X=260 > Y=120，所以需要更多行才能让宽高均衡
  // 目标：cols × 260 / (rows × 120) ≈ 4/3 → cols/rows ≈ 0.62 → rows ≈ sqrt(N/0.62) ≈ sqrt(N) × 1.27
  const N = order.length
  const targetRows = Math.max(2, Math.min(10, Math.round(Math.sqrt(N) * 1.27)))
  const cols = Math.max(1, Math.ceil(N / targetRows))

  const NODE_GAP_X = 260
  const NODE_GAP_Y = 120
  const START_X = 80
  const START_Y = 60
  const POS_MAP = new Map<string, { x: number; y: number }>()

  order.forEach((id, idx) => {
    const row = Math.floor(idx / cols)
    const col = idx % cols
    const x = START_X + col * NODE_GAP_X
    const y = START_Y + row * NODE_GAP_Y
    POS_MAP.set(id, { x, y })
  })

  const newNodes = allNodes.map(n => {
    const pos = POS_MAP.get(n.id) || { x: START_X, y: START_Y }
    return { ...n, position: { x: pos.x, y: pos.y } }
  })

  syncing.value = true
  setNodes(newNodes)
  syncing.value = false
  emit('update:nodes', serializeNodes())
  setTimeout(() => fitView(), 50)
}

defineExpose({ addNode, emitChange, toggleLinkMode, autoLayout, linkMode })

// props 变化（如加载用例）→ 同步到 VueFlow 内部状态
// 仅在节点数量变化（加载用例、增删节点）时同步并 fitView，
// 节点位置变化（拖拽、点击触发 update:nodes 回写）不重置画面比例。
watch(
  () => props.nodes?.length,
  (newLen, oldLen) => {
    if (!props.nodes || newLen === oldLen) return
    syncing.value = true
    setNodes(props.nodes.map((n: any) => ({ ...n })))
    syncing.value = false
    setTimeout(() => fitView(), 50)
  },
  { immediate: true },
)

watch(
  () => props.edges,
  (newEdges) => {
    if (!newEdges) return
    syncing.value = true
    setEdges(newEdges.map((e: any) => ({ ...e })))
    syncing.value = false
  },
  { immediate: true, deep: true },
)
</script>

<style scoped>
.dag-canvas {
  height: 100%;
  width: 100%;
  background: #fafafa;
  position: relative;
}
.link-status-bar {
  position: absolute;
  bottom: 12px;
  left: 50%;
  transform: translateX(-50%);
  padding: 6px 16px;
  background: rgba(0, 0, 0, 0.75);
  color: #fff;
  font-size: 12px;
  border-radius: var(--app-radius-sm);
  backdrop-filter: blur(8px);
  z-index: 10;
  pointer-events: none;
  white-space: nowrap;
}
.dag-node {
  position: relative;
  padding: 10px 18px;
  border-radius: var(--app-radius-sm);
  background: var(--app-card-solid);
  border: 1px solid var(--app-border);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06);
  min-width: 150px;
  transition: border-color 0.15s, box-shadow 0.15s;
}
.dag-node.selected {
  border-color: var(--el-color-primary);
  box-shadow: 0 0 0 2px rgba(0, 113, 227, 0.2);
}
.dag-node.link-source {
  border-color: #34c759;
  box-shadow: 0 0 0 3px rgba(52, 199, 89, 0.3);
}
.dag-node.link-target {
  border-color: var(--el-color-primary);
  box-shadow: 0 0 0 2px rgba(0, 113, 227, 0.15);
}
.dag-node-title {
  font-weight: 600;
  font-size: 13px;
  color: var(--app-text);
}
.dag-node-sub {
  font-size: 11px;
  color: var(--app-text-muted);
  margin-top: 2px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 180px;
}
:deep(.dag-handle) {
  width: 12px;
  height: 12px;
  background: var(--el-color-primary);
  border: 2px solid #fff;
  box-shadow: 0 0 0 1px rgba(0, 0, 0, 0.1);
  opacity: 0.8;
  transition: opacity 0.15s, transform 0.15s;
}
:deep(.dag-handle:hover) {
  opacity: 1;
  transform: scale(1.2);
}
:deep(.source-handle) {
  right: -6px;
}
:deep(.target-handle) {
  left: -6px;
}
:deep(.vue-flow__edge-path) {
  stroke: var(--app-text-muted);
  stroke-width: 2;
}
:deep(.vue-flow__edge:hover .vue-flow__edge-path) {
  stroke: var(--el-color-danger);
  stroke-width: 3;
}
</style>

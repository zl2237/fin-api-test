<template>
  <div class="dag-canvas">
    <VueFlow
      :nodes="nodes"
      :edges="edges"
      :fit-view-on-init="true"
      @connect="onConnect"
      @node-click="onNodeClick"
      @node-double-click="onNodeDblClick"
      @node-drag-stop="emitChange"
      @edge-double-click="onEdgeClick"
    >
      <Background :pattern-color="isDark ? '#3f4148' : '#c9ccd4'" :gap="16" />
      <Controls />
      <MiniMap />
      <template #node-default="props">
        <div class="dag-node" :class="[methodClass(props.data.api_method), {
          selected: props.selected,
          'is-new': newNodeIds.includes(props.id),
          'link-source': linkSourceId === props.id,
          'link-target': linkMode && linkSourceId && linkSourceId !== props.id
        }]">
          <!-- 源连接点（右侧） -->
          <Handle id="source" type="source" :position="Position.Right" class="dag-handle source-handle" />
          <!-- 目标连接点（左侧） -->
          <Handle id="target" type="target" :position="Position.Left" class="dag-handle target-handle" />
          <!-- 接线卡头：method 色签（复用全站四色映射）+ 节点名 -->
          <div class="dag-node-head">
            <span class="dag-node-method">{{ (props.data.api_method || '?').toUpperCase() }}</span>
            <span class="dag-node-title" :title="props.data.label || props.id">{{ props.data.label || props.id }}</span>
          </div>
          <div v-if="props.data.api_path" class="dag-node-sub">{{ props.data.api_path }}</div>
          <!-- 配置徽标行：断言/提取/等待（真实配置计数；未配置任何项则整行不渲染，未配置节点更矮更素） -->
          <div v-if="hasBadges(props.id)" class="dag-node-badges">
            <span v-if="badgeOf(props.id).assertions" class="node-badge badge-assert" title="断言数">✓{{ badgeOf(props.id).assertions }}</span>
            <span v-if="badgeOf(props.id).extracts" class="node-badge badge-extract" title="提取数">→{{ badgeOf(props.id).extracts }}</span>
            <span v-if="badgeOf(props.id).waitMs" class="node-badge" title="执行后等待">{{ badgeOf(props.id).waitMs }}ms</span>
          </div>
        </div>
      </template>
    </VueFlow>
    <!-- 空画布引导：首个节点添加后消失 -->
    <div v-if="!nodes.length" class="canvas-empty">
      <div class="canvas-empty-title">从空白画布开始编排</div>
      <div class="canvas-empty-line">在左侧接口列表中点击接口，即可添加为 DAG 节点</div>
      <div class="canvas-empty-line">拖拽节点右侧端点到目标左侧端点建立依赖，双击节点配置断言与提取</div>
    </div>
    <!-- 连线模式状态栏 -->
    <div v-if="linkMode" class="link-status-bar">
      <span v-if="!linkSourceId">连线模式：点击源节点（source）</span>
      <span v-else>已选源节点，点击目标节点（target）完成连线 · 按 Esc 取消</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted } from 'vue'
import { VueFlow, useVueFlow, Position, Handle, MarkerType } from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'
import { MiniMap } from '@vue-flow/minimap'
import { ElMessage } from 'element-plus'

const props = defineProps<{
  nodes: any[]
  edges: any[]
  /** 节点配置摘要（CaseDesigner 渲染层只读派生，不进入持久化 payload）：
   *  断言/提取计数与执行后等待，用于节点徽标行展示编排覆盖情况 */
  configSummary?: Record<string, { assertions: number; extracts: number; waitMs: number }>
}>()
const emit = defineEmits<{
  (e: 'update:nodes', v: any[]): void
  (e: 'update:edges', v: any[]): void
  (e: 'node-open', id: string): void
  (e: 'nodes-pasted', mapping: { oldId: string; newId: string }[]): void
  (e: 'link-mode-change', active: boolean): void
}>()

const { setNodes, setEdges, addEdges, removeEdges, removeNodes, getNodes, getEdges, fitView, viewport, vueFlowRef } = useVueFlow()

// 暗色主题感知：监听 html.dark class 变化（含 auto 跟随系统），画布点阵随之切换
const isDark = ref(document.documentElement.classList.contains('dark'))
let themeObserver: MutationObserver | null = null
onMounted(() => {
  themeObserver = new MutationObserver(() => {
    isDark.value = document.documentElement.classList.contains('dark')
  })
  themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] })
})
onUnmounted(() => {
  themeObserver?.disconnect()
  themeObserver = null
})

// 防止内部变化触发 emit 后又同步回内部造成循环
const syncing = ref(false)

// 连线模式：选中源节点后再点目标节点连线
const linkMode = ref(false)
const linkSourceId = ref<string | null>(null)

// 新加入节点的 ID 集合（用于高亮区分，约 3.6s 后自动移除）
const newNodeIds = ref<string[]>([])

// ===== 接线卡：method 语义色类（复用接口管理四色映射 GET绿/POST青/PUT琥珀/DELETE红） =====
function methodClass(m?: string): string {
  const u = (m || '').toUpperCase()
  if (u === 'GET') return 'm-get'
  if (u === 'POST') return 'm-post'
  if (u === 'PUT') return 'm-put'
  if (u === 'DELETE') return 'm-delete'
  return 'm-other'
}
/** 节点配置摘要（缺省零值） */
function badgeOf(id: string) {
  return props.configSummary?.[id] ?? { assertions: 0, extracts: 0, waitMs: 0 }
}
/** 任一配置存在才渲染徽标行 */
function hasBadges(id: string) {
  const b = badgeOf(id)
  return !!(b.assertions || b.extracts || b.waitMs)
}

// 剪贴板：存放 Ctrl+C 复制的节点信息（含原始 ID，用于粘贴时克隆 config）
const clipboard = ref<{ id: string; data: any; label: string; position: { x: number; y: number } }[]>([])

// 键盘事件：
// - Esc：linkMode 下重置已选 source 或退出模式
// - Delete/Backspace：删除当前选中的节点（连线模式下不触发，避免误删）
// - Enter：打开选中节点的配置抽屉
// - Ctrl+C / Ctrl+V：复制 / 粘贴选中节点
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
  // 焦点在输入框/文本域中时不拦截快捷键，避免影响文本编辑
  const target = e.target as HTMLElement | null
  const inEditable = !!target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable)

  // Delete 删除选中节点（Backspace 不再绑定删除：退格是高频编辑键，误触代价高）
  if (e.key === 'Delete' && !linkMode.value && !inEditable) {
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
    return
  }

  // Enter 打开选中节点的配置抽屉（仅单个选中时触发）
  if (e.key === 'Enter' && !linkMode.value && !inEditable) {
    const selected = getNodes.value.filter((n: any) => n.selected)
    if (selected.length === 1) {
      emit('node-open', selected[0].id)
      e.preventDefault()
    }
    return
  }

  // Ctrl+C 复制选中节点到剪贴板
  if ((e.ctrlKey || e.metaKey) && e.key === 'c' && !linkMode.value && !inEditable) {
    const selected = getNodes.value.filter((n: any) => n.selected)
    if (!selected.length) return
    clipboard.value = selected.map((n: any) => ({
      id: n.id,
      data: { ...n.data },
      label: n.label,
      position: { x: n.position.x, y: n.position.y },
    }))
    e.preventDefault()
    return
  }

  // Ctrl+V 粘贴节点（新 ID + 偏移位置，并通知父组件克隆 config）
  if ((e.ctrlKey || e.metaKey) && e.key === 'v' && !linkMode.value && !inEditable) {
    if (!clipboard.value.length) return
    const mapping: { oldId: string; newId: string }[] = []
    const newNodes: any[] = []
    let counter = 0
    for (const item of clipboard.value) {
      const newId = `paste-${Date.now()}-${counter++}`
      mapping.push({ oldId: item.id, newId })
      newNodes.push({
        id: newId,
        position: { x: item.position.x + 40, y: item.position.y + 40 },
        data: { ...item.data },
        label: item.label,
      })
    }
    setNodes([...getNodes.value, ...newNodes])
    emit('update:nodes', serializeNodes())
    // 标记新节点高亮
    newNodeIds.value = [...newNodeIds.value, ...newNodes.map((n) => n.id)]
    const pasteIds = newNodes.map((n) => n.id)
    setTimeout(() => {
      newNodeIds.value = newNodeIds.value.filter((id) => !pasteIds.includes(id))
    }, 3600)
    // 通知父组件克隆对应 config
    emit('nodes-pasted', mapping)
    ElMessage.success(`已粘贴 ${mapping.length} 个节点`)
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
  addEdges([{ ...params, markerEnd: MarkerType.ArrowClosed }])
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
      markerEnd: MarkerType.ArrowClosed,
    }
    addEdges([newEdge])
    emit('update:edges', serializeEdges())
    // 重置已选 source，保留 linkMode 便于连续连线
    linkSourceId.value = null
    return
  }
  // 普通模式：单击仅选中（VueFlow 内部已处理选中状态），不打开配置
}

/** 双击节点：触发打开配置抽屉 */
function onNodeDblClick({ node }: any) {
  if (linkMode.value) return
  emit('node-open', node.id)
}

/** 双击连线删除（原「单击即删」误触率高：hover 变红是唯一预告，想选中看看就已删除） */
function onEdgeClick({ edge }: any) {
  removeEdges([edge.id])
  emit('update:edges', serializeEdges())
  ElMessage.success(`已删除连线 ${edge.source} → ${edge.target}`)
}

function addNode(node: any) {
  setNodes([...getNodes.value, node])
  emit('update:nodes', serializeNodes())
  // 标记为新节点，3.6s 后自动清除高亮
  newNodeIds.value = [...newNodeIds.value, node.id]
  const nid = node.id
  setTimeout(() => {
    newNodeIds.value = newNodeIds.value.filter(id => id !== nid)
  }, 3600)
}

// 计算一个空闲位置：优先当前视口中心，若被占用则螺旋搜索周围空闲点
function findFreePosition(): { x: number; y: number } {
  const vp = viewport.value
  const canvasEl = vueFlowRef.value as HTMLElement | null
  const allNodes = getNodes.value

  // 默认起点（视口信息不可用时）
  let cx = 80
  let cy = 60

  // 计算当前视口中心在画布坐标系中的位置
  if (canvasEl && vp) {
    const rect = canvasEl.getBoundingClientRect()
    cx = (rect.width / 2 - vp.x) / vp.zoom
    cy = (rect.height / 2 - vp.y) / vp.zoom
  }

  // 节点尺寸估计 + 间距（用于碰撞检测）
  const NODE_W = 200
  const NODE_H = 70
  const GAP_X = 40
  const GAP_Y = 40

  const isOverlap = (x: number, y: number) =>
    allNodes.some((n: any) =>
      Math.abs(n.position.x - x) < NODE_W + GAP_X &&
      Math.abs(n.position.y - y) < NODE_H + GAP_Y,
    )

  // 视口中心不重叠则直接用
  if (!isOverlap(cx, cy)) {
    return { x: Math.round(cx), y: Math.round(cy) }
  }

  // 螺旋搜索空闲位置
  const STEP = 80
  for (let r = 1; r <= 15; r++) {
    const points = r * 8
    for (let i = 0; i < points; i++) {
      const angle = (i / points) * Math.PI * 2
      const x = cx + Math.cos(angle) * r * STEP
      const y = cy + Math.sin(angle) * r * STEP
      if (!isOverlap(x, y)) {
        return { x: Math.round(x), y: Math.round(y) }
      }
    }
  }

  // 兜底：右下偏移
  return { x: Math.round(cx + 260), y: Math.round(cy + 130) }
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

/** 当前画布选中节点（供设计器「拆分选中」等父组件操作读取） */
function getSelectedNodes(): any[] {
  return getNodes.value.filter((n: any) => n.selected)
}

defineExpose({ addNode, findFreePosition, emitChange, toggleLinkMode, autoLayout, linkMode, getSelectedNodes })

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
    // 所有边带闭合箭头：DAG 的方向语义必须可辨（无向线段在交叉时无法区分 A→B / B→A）
    setEdges(newEdges.map((e: any) => ({ ...e, markerEnd: e.markerEnd ?? MarkerType.ArrowClosed })))
    syncing.value = false
  },
  { immediate: true, deep: true },
)
</script>

<style scoped>
.dag-canvas {
  height: 100%;
  width: 100%;
  background: var(--app-canvas-bg);
  position: relative;
}
.link-status-bar {
  position: absolute;
  bottom: 12px;
  left: 50%;
  transform: translateX(-50%);
  padding: 6px 16px;
  background: var(--app-tooltip-bg);
  color: var(--app-text-inverse);
  font-size: 12px;
  border-radius: var(--app-radius-sm);
  z-index: 10;
  pointer-events: none;
  white-space: nowrap;
}
/* 空画布引导卡片 */
.canvas-empty {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  padding: 22px 30px;
  text-align: center;
  background: var(--app-card-solid);
  border: 1px dashed var(--app-border);
  border-radius: var(--app-radius);
  box-shadow: var(--app-shadow-sm);
  pointer-events: none;
}
.canvas-empty-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--app-text);
  margin-bottom: 8px;
}
.canvas-empty-line {
  font-size: 12px;
  color: var(--app-text-muted);
  line-height: 1.8;
}
.dag-node {
  position: relative;
  padding: 9px 12px;
  border-radius: var(--app-radius-sm);
  background: var(--app-card-solid);
  border: 1px solid var(--app-border);
  /* 接线卡：左 method 语义色轨（--node-accent 由 m-get/m-post/... 类驱动） */
  border-left: 3px solid var(--node-accent, var(--app-border));
  box-shadow: var(--app-shadow-sm);
  min-width: 168px;
  transition: border-color 0.15s, box-shadow 0.15s;
}
/* 色轨/淡底用 accent；文字必须用加深文字变体（小号粗体需 4.5:1，accent 原色仅 2.2-3.5:1） */
.dag-node.m-get { --node-accent: var(--app-success); --node-accent-text: color-mix(in srgb, var(--app-success-text) 78%, black); }
.dag-node.m-post { --node-accent: var(--app-primary); --node-accent-text: var(--app-primary); }
.dag-node.m-put { --node-accent: var(--app-warn-accent); --node-accent-text: color-mix(in srgb, var(--app-warn-text) 70%, black); }
.dag-node.m-delete { --node-accent: var(--app-danger); --node-accent-text: var(--app-danger-text); }
.dag-node.m-other { --node-accent: var(--app-text-faint); --node-accent-text: var(--app-text-muted); }
/* hover 反馈：预判可点击（双击开配置），cursor 提示交互 */
.dag-node:hover {
  border-color: color-mix(in srgb, var(--app-primary) 55%, var(--app-border));
  box-shadow: var(--app-shadow);
  cursor: pointer;
}
.dag-node.selected {
  border-color: var(--app-primary);
  box-shadow: var(--app-glow-primary);
}
.dag-node.is-new {
  border-color: var(--app-success);
  animation: dag-node-highlight 1.2s ease-in-out 3;
}
@keyframes dag-node-highlight {
  0%, 100% {
    box-shadow: 0 0 0 0 color-mix(in srgb, var(--app-success) 45%, transparent), var(--app-shadow-sm);
  }
  50% {
    box-shadow: 0 0 0 10px color-mix(in srgb, var(--app-success) 10%, transparent), var(--app-shadow-sm);
  }
}
@media (prefers-reduced-motion: reduce) {
  .dag-node.is-new {
    animation: none;
  }
}
.dag-node.link-source {
  border-color: var(--app-success);
  box-shadow: var(--app-glow-success);
}
.dag-node.link-target {
  border-color: var(--app-primary);
  box-shadow: var(--app-glow-primary);
}
.dag-node-head {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}
/* method 色签：mono 大写 + 语义色淡底（与左侧色轨同源） */
.dag-node-method {
  flex-shrink: 0;
  font-family: var(--app-font-mono);
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.05em;
  /* 文字用加深变体保证 4.5:1；淡底仍用 accent 原色 */
  color: var(--node-accent-text, var(--app-text-muted));
  background: color-mix(in srgb, var(--node-accent, var(--app-text-muted)) 12%, transparent);
  padding: 1px 5px;
  border-radius: var(--app-radius-xs);
}
.dag-node-title {
  font-weight: 600;
  font-size: 13px;
  color: var(--app-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.dag-node-sub {
  font-family: var(--app-font-mono);
  font-size: 11px;
  color: var(--app-text-muted);
  margin-top: 3px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 190px;
}
/* 配置徽标行：真实配置计数（断言绿/提取青/等待灰），未配置不渲染 */
.dag-node-badges {
  display: flex;
  gap: 8px;
  margin-top: 7px;
  padding-top: 6px;
  border-top: 1px solid var(--app-border);
}
.node-badge {
  font-family: var(--app-font-mono);
  font-size: 10.5px;
  color: var(--app-text-muted);
}
.node-badge.badge-assert { color: color-mix(in srgb, var(--app-success-text) 80%, black); }
.node-badge.badge-extract { color: var(--app-primary); }
:deep(.dag-handle) {
  width: 12px;
  height: 12px;
  background: var(--app-primary);
  border: 2px solid var(--app-card-solid);
  box-shadow: 0 0 0 1px var(--app-border);
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

/* ===== 暗色主题下 Vue Flow 官方控件的适配（默认亮色，暗画布上刺眼） ===== */
html.dark :deep(.vue-flow__controls) {
  background: var(--app-card);
  border: 1px solid var(--app-border);
  box-shadow: none;
}
html.dark :deep(.vue-flow__controls-button) {
  background: transparent;
  border-bottom: 1px solid var(--app-border);
  fill: var(--app-text-muted);
}
html.dark :deep(.vue-flow__controls-button:hover) {
  background: var(--app-hover, rgba(255, 255, 255, 0.06));
}
html.dark :deep(.vue-flow__minimap) {
  background: var(--app-card);
  border: 1px solid var(--app-border);
}
html.dark :deep(.vue-flow__minimap-svg) {
  fill: var(--app-hover, rgba(255, 255, 255, 0.06));
}
</style>

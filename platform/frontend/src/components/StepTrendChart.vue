<template>
  <!-- 各步骤响应耗时趋势图（纯 SVG，零依赖）；从 ReportDetail 提取的展示组件：
       输入仅 steps，输出仅 select(stepId)，悬浮/抽稀等全部内聚 -->
  <el-card shadow="never" :class="['trend-card', { compact }]" @mouseleave="hideTrendTip">
    <div class="trend-head" :class="{ 'is-compact': compact }">
      <span class="trend-title">{{ compact ? '耗时趋势' : '步骤响应耗时趋势' }}</span>
      <span class="trend-sub">{{ compact ? `最大 ${trendMax} · 平均 ${trendAvg} ms` : `单位 ms，最大 ${trendMax} ms，平均 ${trendAvg} ms；悬浮或点击节点查看步骤` }}</span>
    </div>
    <!-- vector-effect 等比保护：none 拉伸会把数据点拉成椭圆、轴文字变形 -->
    <svg class="trend-svg" :viewBox="`0 0 ${geo.w} ${geo.h}`" preserveAspectRatio="none">
      <!-- 网格线 -->
      <line v-for="g in trendGrids" :key="g.y" :x1="g.x1" :y1="g.y" :x2="g.x2" :y2="g.y" stroke="currentColor" class="grid-line" stroke-width="1" vector-effect="non-scaling-stroke" />
      <!-- Y 轴刻度（compact 模式空间不足，隐藏；精确值由悬浮提示承载） -->
      <text v-if="!compact" v-for="g in trendGrids" :key="'t'+g.y" :x="4" :y="g.y - 2" font-size="10" class="axis-text">{{ g.label }}</text>
      <!-- 面积填充（静态呈现：排障工具页不做入场演出） -->
      <polygon v-if="trendDots.length >= 2" :points="areaPoints" class="trend-area" :fill="'url(#trend-grad)'" />
      <defs>
        <linearGradient id="trend-grad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="var(--app-primary)" stop-opacity="0.22" />
          <stop offset="100%" stop-color="var(--app-primary)" stop-opacity="0.02" />
        </linearGradient>
      </defs>
      <!-- 折线（静态呈现） -->
      <polyline
        :points="trendPoints"
        fill="none"
        class="trend-line"
        stroke-width="2"
        stroke-linejoin="round"
        stroke-linecap="round"
        vector-effect="non-scaling-stroke"
      />
      <!-- 数据点（点击选中对应步骤） -->
      <g v-for="(p, i) in trendDots" :key="i">
        <circle
          :cx="p.x"
          :cy="p.y"
          :r="hoveredTrend === i ? 5.5 : (compact ? 2.8 : 3.5)"
          :class="steps[i].status === 'success' ? 'dot-ok' : 'dot-err'"
          class="trend-dot"
          @mouseenter="showTrendTip($event, i)"
          @mousemove="moveTrendTip($event)"
          @mouseleave="hideTrendTip"
          @click="emit('select', steps[i].id)"
        />
      </g>
      <!-- X 轴标签（超过 12 个抽稀防挤压；compact 模式隐藏） -->
      <template v-if="!compact">
        <text
          v-for="(p, i) in trendDots"
          v-show="trendLabelVisible(i)"
          :key="'x'+i"
          :x="p.x"
          :y="geo.h - 4"
          font-size="10"
          class="axis-text"
          text-anchor="middle"
        >{{ i + 1 }}</text>
      </template>
    </svg>
    <!-- 悬浮提示框 -->
    <div v-show="hoveredTrend !== null" class="trend-tip" :style="{ left: tipPos.x + 'px', top: tipPos.y + 'px' }">
      <div class="trend-tip-name">{{ tipContent.name }}</div>
      <div class="trend-tip-row">
        <span class="trend-tip-label">耗时</span>
        <span class="trend-tip-value">{{ tipContent.value }} ms</span>
      </div>
      <div class="trend-tip-row">
        <span class="trend-tip-label">状态</span>
        <span :class="tipContent.status === 'success' ? 'trend-tip-ok' : 'trend-tip-err'">{{ tipContent.status === 'success' ? '通过' : '失败' }}</span>
      </div>
    </div>
  </el-card>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import type { StepRecord } from '@/api'

const props = defineProps<{
  /** 报告步骤列表（按执行顺序），图表只读消费 */
  steps: StepRecord[]
  /** 紧凑模式：嵌入摘要横带的小尺寸 sparkline（隐藏轴标签，悬浮提示保留） */
  compact?: boolean
}>()

const emit = defineEmits<{
  /** 点击数据点：选中对应步骤（由父级写入 currentStepId） */
  select: [stepId: number]
}>()

// ===== 画布几何（compact 模式用小 viewBox + 窄边距，随尺寸一起换算坐标） =====
const geo = computed(() =>
  props.compact
    ? { w: 720, h: 64, pad: { top: 8, right: 8, bottom: 8, left: 8 } }
    : { w: 720, h: 160, pad: { top: 16, right: 20, bottom: 20, left: 40 } }
)

const trendValues = computed(() =>
  props.steps.map(s => s.response_time_ms ?? 0)
)

const trendMax = computed(() => {
  const m = Math.max(...trendValues.value, 1)
  // 向上取整到 10 的倍数，便于刻度
  return Math.ceil(m / 10) * 10
})

const trendAvg = computed(() => {
  if (!trendValues.value.length) return 0
  return Math.round(trendValues.value.reduce((a, b) => a + b, 0) / trendValues.value.length)
})

const trendGrids = computed(() => {
  const grids: { y: number; x1: number; x2: number; label: string }[] = []
  const gridSteps = props.compact ? 2 : 4
  const usableH = geo.value.h - geo.value.pad.top - geo.value.pad.bottom
  for (let i = 0; i <= gridSteps; i++) {
    const y = geo.value.pad.top + (usableH * i) / gridSteps
    const val = Math.round(trendMax.value * (1 - i / gridSteps))
    grids.push({ y, x1: geo.value.pad.left, x2: geo.value.w - geo.value.pad.right, label: String(val) })
  }
  return grids
})

const trendDots = computed(() => {
  const vals = trendValues.value
  if (!vals.length) return []
  const usableW = geo.value.w - geo.value.pad.left - geo.value.pad.right
  const usableH = geo.value.h - geo.value.pad.top - geo.value.pad.bottom
  const max = trendMax.value || 1
  return vals.map((v, i) => {
    const x = geo.value.pad.left + (vals.length === 1 ? usableW / 2 : (usableW * i) / (vals.length - 1))
    const y = geo.value.pad.top + usableH * (1 - v / max)
    return { x, y, value: v }
  })
})

const trendPoints = computed(() =>
  trendDots.value.map(p => `${p.x},${p.y}`).join(' ')
)

// 面积多边形：折线点 + 底边闭合（左右落到基线）
const areaPoints = computed(() => {
  const dots = trendDots.value
  if (dots.length < 2) return ''
  const base = geo.value.h - geo.value.pad.bottom
  const first = dots[0]
  const last = dots[dots.length - 1]
  return `${first.x},${base} ${dots.map(p => `${p.x},${p.y}`).join(' ')} ${last.x},${base}`
})

// ===== 悬浮提示（组件内聚局部状态） =====
const hoveredTrend = ref<number | null>(null)
const tipPos = ref({ x: 0, y: 0 })
const tipContent = ref({ name: '', value: 0, status: '' })

function showTrendTip(e: MouseEvent, i: number) {
  hoveredTrend.value = i
  const s = props.steps[i]
  tipContent.value = {
    name: s.api_name || s.node_id || '未命名步骤',
    value: trendValues.value[i] ?? 0,
    status: s.status || '',
  }
  moveTrendTip(e)
}
function moveTrendTip(e: MouseEvent) {
  const card = (e.currentTarget as SVGElement).closest('.trend-card') as HTMLElement | null
  if (!card) return
  const rect = card.getBoundingClientRect()
  let x = e.clientX - rect.left + 14
  let y = e.clientY - rect.top + 14
  // 防止提示框溢出容器右侧/底部
  if (x + 180 > rect.width) x = e.clientX - rect.left - 190
  if (y + 90 > rect.height) y = e.clientY - rect.top - 100
  tipPos.value = { x, y }
}
function hideTrendTip() {
  hoveredTrend.value = null
}

/** X 轴标签抽稀：步骤多时按步长隔行显示，避免标签挤成一排 */
function trendLabelVisible(i: number) {
  const total = trendDots.value.length
  if (total <= 12) return true
  const step = Math.ceil(total / 12)
  return i % step === 0
}
</script>

<style scoped>
.trend-card {
  position: relative;
  background: var(--app-card);
  border-radius: var(--app-radius-lg);
  display: flex;
  flex-direction: column;
  overflow: visible;
}

.trend-head {
  display: flex;
  align-items: baseline;
  gap: 12px;
  margin-bottom: 8px;
}

/* compact 模式：嵌入摘要横带的迷你尺寸 */
.trend-card.compact {
  background: transparent;
  border: none;
  box-shadow: none;
  min-width: 0;
}
.trend-card.compact :deep(.el-card__body) {
  padding: 0;
}
.trend-head.is-compact {
  gap: 8px;
  margin-bottom: 4px;
  white-space: nowrap;
}
.trend-head.is-compact .trend-title {
  font-size: 12px;
}
.trend-head.is-compact .trend-sub {
  font-size: 11px;
}
.trend-card.compact .trend-svg {
  height: 46px;
}

.trend-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--app-text);
}

.trend-sub {
  font-size: 12px;
  color: var(--app-text-muted);
}

.trend-svg {
  width: 100%;
  height: 130px;
  display: block;
}

/* SVG 趋势图主题色（覆盖 presentation attribute） */
.trend-svg .grid-line {
  stroke: var(--app-border);
}
.trend-svg .axis-text {
  fill: var(--app-text-muted);
}
.trend-svg .trend-line {
  stroke: var(--app-primary);
}
.trend-svg .trend-area {
  opacity: 1;
}
.trend-svg .dot-ok {
  fill: var(--app-success);
}
.trend-svg .dot-err {
  fill: var(--app-danger);
}
.trend-svg .trend-dot {
  cursor: pointer;
  transition: r 0.15s ease;
}
/* hover：实心描边环替代发光（工程面板语言） */
.trend-svg .trend-dot:hover {
  stroke: var(--app-card-solid);
  stroke-width: 2px;
}

/* 悬浮提示框 */
.trend-tip {
  position: absolute;
  z-index: 20;
  min-width: 160px;
  max-width: 260px;
  padding: 10px 12px;
  background: var(--app-card-solid);
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius-md);
  box-shadow: var(--app-shadow-lg);
  pointer-events: none;
  animation: trend-tip-in 0.12s ease;
}
@keyframes trend-tip-in {
  from { opacity: 0; transform: translateY(2px); }
  to { opacity: 1; transform: translateY(0); }
}
@media (prefers-reduced-motion: reduce) {
  .trend-tip {
    animation: none;
  }
}
.trend-tip-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--app-text);
  margin-bottom: 6px;
  word-break: break-all;
}
.trend-tip-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  font-size: 12px;
  line-height: 1.6;
}
.trend-tip-label {
  color: var(--app-text-muted);
}
.trend-tip-value {
  font-family: var(--app-font-mono);
  color: var(--app-primary);
  font-weight: 500;
}
.trend-tip-ok {
  color: var(--app-success);
}
.trend-tip-err {
  color: var(--app-danger);
}
</style>

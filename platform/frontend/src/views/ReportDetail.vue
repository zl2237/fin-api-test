<template>
  <div class="report" v-loading="loading">
    <!-- 执行中提示条：running 态自动轮询，与列表页行为一致 -->
    <el-alert
      v-if="record?.status === 'running'"
      class="running-banner"
      type="info"
      :closable="false"
      show-icon
    >
      <template #title>
        用例执行中，每 {{ POLL_MS / 1000 }} 秒自动刷新…
        <el-icon class="is-loading"><Loading /></el-icon>
      </template>
    </el-alert>
    <!-- 顶部：摘要 + 趋势图 横向并排，节省垂直空间 -->
    <div class="top-row">
      <el-card shadow="never" class="summary-card">
        <div class="summary-head">
          <div class="summary-title">
            <span class="title-text">执行报告 #{{ record?.id ?? '-' }}</span>
            <el-tag :type="statusType(record?.status)" effect="light" round>
              {{ statusText(record?.status) }}
            </el-tag>
          </div>
          <div class="summary-actions">
            <el-button
              size="small"
              type="success"
              :loading="rerunning"
              :disabled="!record?.case_id || !record?.env_id"
              @click="onRerun"
            >
              重新执行
            </el-button>
            <el-button size="small" @click="exportCsv" :disabled="!steps.length">导出 CSV</el-button>
            <el-button size="small" @click="exportHtml" :disabled="!steps.length">导出 HTML</el-button>
            <el-button text @click="router.back()">返回</el-button>
          </div>
        </div>
        <div class="summary-grid">
          <div class="metric">
            <div class="metric-label">用例</div>
            <div class="metric-value" :title="record?.case_name || `#${record?.case_id}` || '-'">{{ record?.case_name || `#${record?.case_id}` || '-' }}</div>
          </div>
          <div class="metric">
            <div class="metric-label">环境</div>
            <div class="metric-value" :title="record?.env_name || `#${record?.env_id}` || '-'">{{ record?.env_name || `#${record?.env_id}` || '-' }}</div>
          </div>
          <div class="metric">
            <div class="metric-label">步骤通过 / 总数</div>
            <div class="metric-value">
              <span class="pass">{{ passedCountUp }}</span>
              <span class="sep">/</span>
              <span>{{ totalCountUp }}</span>
            </div>
          </div>
          <div class="metric">
            <div class="metric-label">断言通过 / 总数</div>
            <div class="metric-value">
              <span class="pass">{{ assertionPassedUp }}</span>
              <span class="sep">/</span>
              <span>{{ assertionTotalUp }}</span>
            </div>
          </div>
          <div class="metric">
            <div class="metric-label">开始时间</div>
            <div class="metric-value small" :title="record?.started_at ?? '-'">{{ record?.started_at ?? '-' }}</div>
          </div>
          <div class="metric">
            <div class="metric-label">耗时</div>
            <div class="metric-value">{{ durationUp }}</div>
          </div>
        </div>
      </el-card>

      <!-- 各步骤响应耗时趋势图（纯 SVG，零依赖） -->
      <el-card v-if="steps.length" shadow="never" class="trend-card" @mouseleave="hideTrendTip">
        <div class="trend-head">
          <span class="trend-title">步骤响应耗时趋势</span>
          <span class="trend-sub">单位 ms · 最大值 {{ trendMax }} ms · 平均 {{ trendAvg }} ms · 悬浮/点击节点查看步骤</span>
        </div>
        <!-- vector-effect 等比保护：none 拉伸会把数据点拉成椭圆、轴文字变形 -->
        <svg class="trend-svg" :viewBox="`0 0 ${trendWidth} ${trendHeight}`" preserveAspectRatio="none">
          <!-- 网格线 -->
          <line v-for="g in trendGrids" :key="g.y" :x1="g.x1" :y1="g.y" :x2="g.x2" :y2="g.y" stroke="currentColor" class="grid-line" stroke-width="1" vector-effect="non-scaling-stroke" />
          <!-- Y 轴刻度 -->
          <text v-for="g in trendGrids" :key="'t'+g.y" :x="4" :y="g.y - 2" font-size="10" class="axis-text">{{ g.label }}</text>
          <!-- 面积填充（渐变，描线入场时同步淡入） -->
          <polygon v-if="trendDots.length >= 2" :points="areaPoints" class="trend-area" :class="{ drawn: trendDrawn }" :fill="'url(#trend-grad)'" />
          <defs>
            <linearGradient id="trend-grad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stop-color="var(--app-primary)" stop-opacity="0.22" />
              <stop offset="100%" stop-color="var(--app-primary)" stop-opacity="0.02" />
            </linearGradient>
          </defs>
          <!-- 折线（描线入场：stroke-dashoffset 从总长滚到 0） -->
          <polyline
            ref="trendLineRef"
            :points="trendPoints"
            fill="none"
            class="trend-line"
            :class="{ drawn: trendDrawn }"
            stroke-width="2"
            stroke-linejoin="round"
            stroke-linecap="round"
            vector-effect="non-scaling-stroke"
          />
          <!-- 数据点（点击跳转对应步骤；X 轴标签超过 12 个抽稀防挤压） -->
          <g v-for="(p, i) in trendDots" :key="i">
            <circle
              :cx="p.x"
              :cy="p.y"
              :r="hoveredTrend === i ? 5.5 : 3.5"
              :class="steps[i].status === 'success' ? 'dot-ok' : 'dot-err'"
              class="trend-dot"
              @mouseenter="showTrendTip($event, i)"
              @mousemove="moveTrendTip($event)"
              @mouseleave="hideTrendTip"
              @click="currentStepId = steps[i].id"
            />
          </g>
          <text
            v-for="(p, i) in trendDots"
            v-show="trendLabelVisible(i)"
            :key="'x'+i"
            :x="p.x"
            :y="trendHeight - 4"
            font-size="10"
            class="axis-text"
            text-anchor="middle"
          >{{ i + 1 }}</text>
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
    </div>

    <!-- 失败摘要卡：与导出 HTML 报告同构（仅失败时渲染，点击跳转对应步骤） -->
    <el-card v-if="failedSteps.length" shadow="never" class="fail-summary">
      <div class="fail-summary-head">
        <el-icon class="fail-icon"><CircleCloseFilled /></el-icon>
        失败摘要 · {{ failedSteps.length }} 个步骤未通过（点击跳转）
      </div>
      <div
        v-for="fs in failedSteps"
        :key="fs.id"
        class="fail-summary-item"
        @click="jumpToStep(fs)"
      >
        <span class="fs-idx">#{{ fs.index + 1 }}</span>
        <span class="fs-name" :title="fs.api_name || fs.node_id || '未命名步骤'">{{ fs.api_name || fs.node_id || '未命名步骤' }}</span>
        <span class="fs-why">{{ fs.why }}</span>
        <span class="fs-count">{{ fs.failCount }} 条断言失败</span>
      </div>
    </el-card>

    <!-- 主体：时间轴 + 详情 -->
    <div class="body">
      <!-- 左侧时间轴 -->
      <el-card shadow="never" class="steps-card">
        <div class="steps-head">
          步骤时间轴（{{ displaySteps.length }}<template v-if="onlyFailed">/{{ steps.length }}</template>）
          <el-checkbox
            v-if="failedStepCount > 0"
            v-model="onlyFailed"
            size="small"
            class="only-failed"
          >只看失败</el-checkbox>
        </div>
        <!-- 导航搜索：与导出报告同构（按名称/方法/路径过滤） -->
        <div class="steps-search">
          <el-input
            v-model="stepKeyword"
            size="small"
            clearable
            placeholder="搜索步骤 / 路径…"
            :prefix-icon="Search"
          />
        </div>
        <el-scrollbar class="steps-scroll">
          <el-timeline>
            <el-timeline-item
              v-for="s in displaySteps"
              :key="s.id"
              :type="stepType(s.status)"
              :timestamp="stepTimeText(s)"
              :hollow="currentStepId !== s.id"
              placement="top"
              @click="currentStepId = s.id"
            >
              <div
                class="step-item"
                :class="{ active: currentStepId === s.id }"
                @click="currentStepId = s.id"
              >
                <div class="step-idx">#{{ stepNo(s) }}</div>
                <div class="step-main">
                  <div class="step-title">{{ s.api_name || s.node_id || '未命名步骤' }}</div>
                  <div class="step-sub">{{ s.api_method }} {{ s.api_path }}</div>
                  <div class="step-tags">
                    <el-tag :type="stepType(s.status)" size="small" effect="plain" round>
                      {{ stepStatusText(s.status) }}
                    </el-tag>
                    <el-tag v-if="s.response_status" size="small" type="info" effect="plain" round>
                      HTTP {{ s.response_status }}
                    </el-tag>
                    <el-tag v-if="s.response_time_ms != null" size="small" type="info" effect="plain" round>
                      {{ s.response_time_ms }} ms
                    </el-tag>
                  </div>
                </div>
              </div>
            </el-timeline-item>
            <EmptyState v-if="!steps.length" description="暂无步骤" :image-size="60" />
          </el-timeline>
        </el-scrollbar>
      </el-card>

      <!-- 右侧详情 -->
      <el-card shadow="never" class="detail-card">
        <template v-if="currentStep">
          <div class="detail-head">
            <div class="detail-title">
              {{ currentStep.api_name || currentStep.node_id || '未命名步骤' }}
            </div>
            <div class="detail-sub">
              <span class="muted">{{ currentStep.api_method }} {{ currentStep.api_path }}</span>
            </div>
          </div>
          <el-tabs v-model="activeTab" class="detail-tabs">
            <el-tab-pane label="请求" name="request">
              <div class="section">
                <div class="section-title">请求头</div>
                <VueJsonPretty v-if="currentStep.request_headers" :data="currentStep.request_headers" />
                <EmptyState v-else description="无请求头" :image-size="40" />
              </div>
              <div class="section">
                <div class="section-title">请求体</div>
                <VueJsonPretty v-if="currentStep.request_body" :data="currentStep.request_body" />
                <EmptyState v-else description="无请求体" :image-size="40" />
              </div>
            </el-tab-pane>

            <el-tab-pane label="响应" name="response">
              <div class="section">
                <div class="section-title">状态码</div>
                <el-tag :type="httpStatusType(currentStep.response_status)" effect="light" round>
                  {{ currentStep.response_status ?? '-' }}
                </el-tag>
              </div>
              <div class="section">
                <div class="section-title">响应耗时</div>
                <span>{{ currentStep.response_time_ms ?? '-' }} ms</span>
              </div>
              <div class="section">
                <div class="section-title">响应体</div>
                <VueJsonPretty v-if="currentStep.response_body != null" :data="currentStep.response_body" />
                <EmptyState v-else description="无响应体" :image-size="40" />
              </div>
            </el-tab-pane>

            <el-tab-pane :label="`断言 (${currentStep.assertions.length})`" name="assertions">
              <el-table :data="currentStep.assertions" size="small" border :row-class-name="assertionRowClass">
                <el-table-column label="结果" width="80">
                  <template #default="{ row }">
                    <el-tag :type="row.result ? 'success' : 'danger'" effect="light" round size="small">
                      {{ row.result ? '通过' : '失败' }}
                    </el-tag>
                  </template>
                </el-table-column>
                <el-table-column prop="rule_type" label="断言类型" width="180" />
                <el-table-column label="规则配置">
                  <template #default="{ row }">
                    <div class="config-cell">
                      <VueJsonPretty v-if="row.rule_config" :data="row.rule_config" :deep="2" />
                      <span v-else class="muted">—</span>
                    </div>
                  </template>
                </el-table-column>
                <el-table-column label="实际值" min-width="140" show-overflow-tooltip>
                  <template #default="{ row }">
                    <span class="mono">{{ row.actual_value ?? '—' }}</span>
                  </template>
                </el-table-column>
                <el-table-column label="期望值" min-width="140" show-overflow-tooltip>
                  <template #default="{ row }">
                    <span class="mono">{{ row.expected_value ?? '—' }}</span>
                  </template>
                </el-table-column>
                <el-table-column label="消息" min-width="180" show-overflow-tooltip>
                  <template #default="{ row }">
                    <!-- 失败原因是一页报告里最重要的信息，不再弱化为灰色小字 -->
                    <span :class="row.result ? 'muted' : 'fail-msg'">{{ row.message ?? '—' }}</span>
                  </template>
                </el-table-column>
              </el-table>
              <EmptyState v-if="!currentStep.assertions.length" description="该步骤无断言" :image-size="60" />
            </el-tab-pane>
          </el-tabs>
        </template>
        <EmptyState v-else description="请选择左侧步骤查看详情" :image-size="80" />
      </el-card>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Loading, Search, CircleCloseFilled } from '@element-plus/icons-vue'
import VueJsonPretty from 'vue-json-pretty'
import 'vue-json-pretty/lib/styles.css'
import EmptyState from '@/components/EmptyState.vue'
import { execApi, caseApi, type ExecutionRecord, type StepRecord } from '@/api'
import { generateReportFilename } from '@/utils/reportFilename'
import { useCountUp } from '@/composables/useCountUp'

const route = useRoute()
const router = useRouter()
const record = ref<ExecutionRecord | null>(null)
const loading = ref(false)
const currentStepId = ref<number | null>(null)
const activeTab = ref('request')
const rerunning = ref(false)

async function onRerun() {
  if (!record.value?.case_id || !record.value?.env_id) {
    ElMessage.warning('缺少用例或环境信息，无法重跑')
    return
  }
  rerunning.value = true
  try {
    const rec = await caseApi.execute(record.value.case_id, record.value.env_id)
    ElMessage.success('已触发重跑，正在跳转到新报告')
    router.replace(`/reports/${rec.id}`)
  } catch (e: any) {
    ElMessage.error(e.message || '重跑失败')
  } finally {
    rerunning.value = false
  }
}

const steps = computed<StepRecord[]>(() => record.value?.steps ?? [])
const currentStep = computed<StepRecord | null>(() =>
  steps.value.find((s) => s.id === currentStepId.value) ?? null
)

// 失败可见性：失败步骤计数 + 「只看失败」过滤 + 导航搜索（与导出报告同构）
const failedStepCount = computed(() => steps.value.filter((s) => s.status !== 'success').length)
const onlyFailed = ref(false)
const stepKeyword = ref('')
const displaySteps = computed(() => {
  let list = onlyFailed.value ? steps.value.filter((s) => s.status !== 'success') : steps.value
  const kw = stepKeyword.value.trim().toLowerCase()
  if (kw) {
    list = list.filter((s) =>
      (s.api_name || s.node_id || '').toLowerCase().includes(kw)
      || (s.api_method || '').toLowerCase().includes(kw)
      || (s.api_path || '').toLowerCase().includes(kw),
    )
  }
  return list
})

// 失败摘要卡数据：失败步骤 + 原始序号 + 首条失败断言原因（与导出报告 fail-card 同构）
const failedSteps = computed(() =>
  steps.value
    .map((s, index) => {
      if (s.status === 'success') return null
      const failedAsserts = (s.assertions ?? []).filter((a) => !a.result)
      const why = failedAsserts.length
        ? (failedAsserts[0].message || failedAsserts[0].rule_type)
        : (s.status || '失败')
      return { ...s, index, why, failCount: failedAsserts.length }
    })
    .filter((x): x is NonNullable<typeof x> => x !== null),
)

/** 失败摘要卡跳转：清筛选保可见 + 选中 + 联动详情 Tab 定位到断言 */
function jumpToStep(fs: (typeof failedSteps.value)[number]) {
  onlyFailed.value = false
  stepKeyword.value = ''
  currentStepId.value = fs.id
  activeTab.value = 'assertions'
}

/** 时间轴序号：过滤/搜索后仍显示原始步骤序号（与失败摘要卡、导出报告一致） */
function stepNo(s: StepRecord) {
  return steps.value.indexOf(s) + 1
}

/** 断言表行样式：失败行浅红底，扫一眼就能定位 */
function assertionRowClass({ row }: { row: any }) {
  return row.result ? '' : 'assert-fail-row'
}

const passedCount = computed(() => steps.value.filter((s) => s.status === 'success').length)
const totalCount = computed(() => steps.value.length)

const assertionTotal = computed(() =>
  steps.value.reduce((acc, s) => acc + (s.assertions?.length ?? 0), 0)
)
const assertionPassed = computed(() =>
  steps.value.reduce(
    (acc, s) => acc + (s.assertions?.filter((a) => a.result).length ?? 0),
    0
  )
)

// ===== 摘要数字 count-up 滚动（数据加载完成后从 0 滚到目标值） =====
const passedCountUp = useCountUp(computed(() => passedCount.value))
const totalCountUp = useCountUp(computed(() => totalCount.value))
const assertionPassedUp = useCountUp(computed(() => assertionPassed.value))
const assertionTotalUp = useCountUp(computed(() => assertionTotal.value))
// 耗时滚动：毫秒数值滚动 + 同款格式化（<1s 显示整数 ms，否则秒两位小数）
const durationMs = computed(() => {
  if (!record.value?.started_at || !record.value?.ended_at) return 0
  return new Date(record.value.ended_at).getTime() - new Date(record.value.started_at).getTime()
})
function formatDuration(ms: number): string {
  if (ms < 1000) return `${Math.round(ms)} ms`
  return `${(ms / 1000).toFixed(2)} s`
}
const durationUp = useCountUp(durationMs, 800, formatDuration)

// ===== 步骤耗时趋势图（纯 SVG） =====
const trendWidth = 720
const trendHeight = 160
const trendPadding = { top: 16, right: 20, bottom: 20, left: 40 }

const trendValues = computed(() =>
  steps.value.map(s => s.response_time_ms ?? 0)
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
  const gridSteps = 4
  const usableH = trendHeight - trendPadding.top - trendPadding.bottom
  for (let i = 0; i <= gridSteps; i++) {
    const y = trendPadding.top + (usableH * i) / gridSteps
    const val = Math.round(trendMax.value * (1 - i / gridSteps))
    grids.push({ y, x1: trendPadding.left, x2: trendWidth - trendPadding.right, label: String(val) })
  }
  return grids
})

const trendDots = computed(() => {
  const vals = trendValues.value
  if (!vals.length) return []
  const usableW = trendWidth - trendPadding.left - trendPadding.right
  const usableH = trendHeight - trendPadding.top - trendPadding.bottom
  const max = trendMax.value || 1
  return vals.map((v, i) => {
    const x = trendPadding.left + (vals.length === 1 ? usableW / 2 : (usableW * i) / (vals.length - 1))
    const y = trendPadding.top + usableH * (1 - v / max)
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
  const base = trendHeight - trendPadding.bottom
  const first = dots[0]
  const last = dots[dots.length - 1]
  return `${first.x},${base} ${dots.map(p => `${p.x},${p.y}`).join(' ')} ${last.x},${base}`
})

// ===== 描线入场：steps 数据就位后，dashoffset 从总长动画到 0（从左向右画出折线） =====
const trendLineRef = ref<SVGPolylineElement | null>(null)
const trendDrawn = ref(false)
watch(trendPoints, async (pts) => {
  if (!pts) return
  await nextTick()
  const el = trendLineRef.value
  if (!el) return
  const total = el.getTotalLength ? el.getTotalLength() : 0
  if (!total) {
    trendDrawn.value = true
    return
  }
  // 重置后触发 CSS transition 完成描线；减少动画偏好时 CSS 侧直接置 0 跳过
  trendDrawn.value = false
  el.style.strokeDasharray = String(total)
  el.style.strokeDashoffset = String(total)
  // 强制回流使起始状态生效
  void el.getBoundingClientRect()
  requestAnimationFrame(() => {
    trendDrawn.value = true
  })
}, { immediate: true })

// ===== 趋势图悬浮提示 =====
const hoveredTrend = ref<number | null>(null)
const tipPos = ref({ x: 0, y: 0 })
const tipContent = ref({ name: '', value: 0, status: '' })

function showTrendTip(e: MouseEvent, i: number) {
  hoveredTrend.value = i
  const s = steps.value[i]
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

function statusType(s?: string) {
  if (s === 'success') return 'success'
  if (s === 'running') return 'warning'
  if (s == null) return 'info' // 加载中/加载失败不再是红色标签 + '-'
  return 'danger'
}
function statusText(s?: string) {
  if (s === 'success') return '通过'
  if (s === 'running') return '执行中'
  if (s === 'failed') return '失败'
  return s ?? '-'
}

function stepType(s?: string) {
  if (s === 'success') return 'success'
  if (s === 'running') return 'warning'
  if (s === 'failed') return 'danger'
  return 'info'
}
function stepStatusText(s?: string) {
  if (s === 'success') return '通过'
  if (s === 'failed') return '失败'
  if (s === 'skipped') return '跳过'
  if (s === 'running') return '执行中'
  return s ?? '-'
}

function httpStatusType(code?: number) {
  if (code == null) return 'info'
  if (code >= 200 && code < 300) return 'success'
  // 接口测试语义：非 2xx 即请求层面失败（原 4xx 归 warning 与失败层级冲突）
  if (code >= 400) return 'danger'
  return 'info'
}

function stepTimeText(s: StepRecord) {
  const start = s.started_at ?? '-'
  const dur = s.started_at && s.ended_at
    ? `${new Date(s.ended_at).getTime() - new Date(s.started_at).getTime()} ms`
    : ''
  return dur ? `${start} · ${dur}` : start
}

// ===== 导出 CSV / HTML（后端组装：/reports/executions/{id}/export，视图只负责下载） =====
async function exportCsv() {
  await downloadExport('csv', '已导出 CSV')
}

async function exportHtml() {
  await downloadExport('html', '已导出 HTML 报告')
}

async function downloadExport(format: 'csv' | 'html', okMsg: string) {
  if (!steps.value.length || !record.value?.id) return
  try {
    const blob = await execApi.exportReport(record.value.id, format)
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = generateReportFilename({
      caseName: record.value?.case_name,
      envName: record.value?.env_name,
      status: record.value?.status,
      ext: format,
    })
    link.click()
    URL.revokeObjectURL(url)
    ElMessage.success(okMsg)
  } catch (e: any) {
    ElMessage.error(e.message || '导出失败')
  }
}

// running 态轮询间隔（与执行列表页一致的节奏）
const POLL_MS = 3000
let pollTimer: ReturnType<typeof setTimeout> | null = null

function stopPolling() {
  if (pollTimer) {
    clearTimeout(pollTimer)
    pollTimer = null
  }
}

/** running 态自动轮询直到出结果；终态即停（含页面失活兜底） */
function schedulePollIfRunning() {
  stopPolling()
  if (record.value?.status !== 'running') return
  pollTimer = setTimeout(async () => {
    await load(true)
    schedulePollIfRunning()
  }, POLL_MS)
}

async function load(silent = false) {
  const id = Number(route.params.id)
  if (!id) return
  if (!silent) loading.value = true
  try {
    record.value = await execApi.report(id)
    if (steps.value.length && currentStepId.value == null) {
      // 默认定位首个失败步骤（排障第一诉求）；无失败则回第 1 步
      const firstFailed = steps.value.find((s) => s.status !== 'success')
      currentStepId.value = (firstFailed ?? steps.value[0]).id
    }
    schedulePollIfRunning()
  } catch (e: any) {
    ElMessage.error(e.message)
  } finally {
    if (!silent) loading.value = false
  }
}

watch(
  () => route.params.id,
  () => {
    // keep-alive 缓存下，其他带 :id 参数的路由变化也会触发本 watch；
    // 仅当前路由确实是报告详情页时才加载，避免把用例 ID 当执行记录 ID 请求 404
    if (route.name !== 'ReportDetail') return
    load()
  }
)

onMounted(load)
onUnmounted(stopPolling)
</script>

<style scoped>
.report {
  display: flex;
  flex-direction: column;
  gap: 12px;
  height: 100%;
  min-height: 0;
}

/* 顶部摘要 + 趋势图 横向并排，高度固定不随内容变化 */
.top-row {
  display: grid;
  grid-template-columns: minmax(420px, 1.4fr) minmax(360px, 1fr);
  gap: 12px;
  flex-shrink: 0;
  height: 180px;
}

.summary-card {
  background: var(--app-card);
  backdrop-filter: saturate(180%) blur(20px);
  border-radius: var(--app-radius-lg);
  overflow: hidden;
}

.trend-card {
  position: relative;
  background: var(--app-card);
  backdrop-filter: saturate(180%) blur(20px);
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
  /* 描线入场：dasharray/offset 由脚本按总长设置，drawn 后过渡到 0 */
  transition: stroke-dashoffset 1.1s cubic-bezier(0.4, 0, 0.2, 1);
}
.trend-svg .trend-line.drawn {
  stroke-dashoffset: 0 !important;
}
/* 减少动画偏好：跳过描线直接显示 */
@media (prefers-reduced-motion: reduce) {
  .trend-svg .trend-line {
    transition: none;
  }
  .trend-svg .trend-line.drawn {
    stroke-dashoffset: 0 !important;
  }
}
/* 面积填充：随描线完成淡入 */
.trend-svg .trend-area {
  opacity: 0;
  transition: opacity 0.6s ease 0.5s;
}
.trend-svg .trend-area.drawn {
  opacity: 1;
}
@media (prefers-reduced-motion: reduce) {
  .trend-svg .trend-area {
    opacity: 1;
    transition: none;
  }
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
  filter: drop-shadow(0 0 0 transparent);
}
.trend-svg .trend-dot:hover {
  filter: drop-shadow(0 0 4px currentColor);
}

/* 悬浮提示框 */
.trend-tip {
  position: absolute;
  z-index: 20;
  min-width: 160px;
  max-width: 260px;
  padding: 10px 12px;
  background: var(--app-card);
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius-md);
  box-shadow: 0 6px 20px rgba(0, 0, 0, 0.15);
  pointer-events: none;
  animation: trend-tip-in 0.12s ease;
}
@keyframes trend-tip-in {
  from { opacity: 0; transform: translateY(2px); }
  to { opacity: 1; transform: translateY(0); }
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

.summary-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.summary-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.summary-title {
  display: flex;
  align-items: center;
  gap: 12px;
}

.title-text {
  font-size: 18px;
  font-weight: 600;
  color: var(--app-text);
}

.summary-grid {
  margin-top: 12px;
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 12px;
  flex: 1;
  min-height: 0;
  align-content: start;
}

.metric {
  background: var(--app-hover);
  border-radius: var(--app-radius);
  padding: 12px 14px;
  min-width: 0;
}

.metric-label {
  font-size: 12px;
  color: var(--app-text-muted);
}

.metric-value {
  font-size: 18px;
  font-weight: 600;
  color: var(--app-text);
  margin-top: 4px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.metric-value.small {
  font-size: 13px;
  font-weight: 500;
}

.metric-value .pass {
  color: var(--app-success);
}

.metric-value .sep {
  color: var(--app-text-faint);
  margin: 0 4px;
}

.body {
  flex: 1;
  display: grid;
  grid-template-columns: 360px 1fr;
  gap: 12px;
  min-height: 0;
  overflow: hidden;
}

.steps-card,
.detail-card {
  background: var(--app-card);
  backdrop-filter: saturate(180%) blur(20px);
  border-radius: var(--app-radius-lg);
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}

.steps-head {
  font-size: 14px;
  font-weight: 600;
  color: var(--app-text);
  margin-bottom: 8px;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

/* 导航搜索框（与导出报告同构） */
.steps-search {
  margin-bottom: 8px;
}

/* ===== 失败摘要卡（与导出报告 fail-card 同构） ===== */
.fail-summary {
  flex-shrink: 0;
  border-left: 4px solid var(--app-danger);
}
.fail-summary :deep(.el-card__body) {
  padding: 0;
}
.fail-summary-head {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 18px;
  font-size: 13px;
  font-weight: 600;
  color: var(--app-danger);
  background: color-mix(in srgb, var(--app-danger) 8%, transparent);
}
.fail-icon {
  font-size: 15px;
}
.fail-summary-item {
  display: flex;
  align-items: baseline;
  gap: 10px;
  flex-wrap: wrap;
  padding: 9px 18px;
  border-top: 1px solid var(--app-border);
  cursor: pointer;
  transition: background 0.12s ease;
}
.fail-summary-item:hover {
  background: color-mix(in srgb, var(--app-primary) 6%, transparent);
}
.fs-idx {
  font-size: 12px;
  font-weight: 700;
  color: var(--app-danger);
  flex-shrink: 0;
}
.fs-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--app-text);
  /* 超长步骤名单行截断（title 悬浮全文），防摘要卡被撑高 */
  max-width: 40%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.fs-why {
  flex: 1;
  min-width: 200px;
  font-size: 12px;
  color: var(--app-danger);
}
.fs-count {
  font-size: 11px;
  color: var(--app-text-muted);
  flex-shrink: 0;
}

.only-failed {
  font-weight: 400;
}

/* 失败断言行：浅红底 + 红色消息文字（失败原因是排障第一信息，不再弱化） */
:deep(.assert-fail-row) {
  background: color-mix(in srgb, var(--el-color-danger) 7%, transparent);
}
.fail-msg {
  color: var(--el-color-danger);
  font-size: 12px;
}

.steps-scroll {
  flex: 1;
}

.step-item {
  display: flex;
  gap: 8px;
  cursor: pointer;
  padding: 6px 8px;
  border-radius: var(--app-radius-md);
  transition: background 0.15s;
}

.step-item:hover {
  background: var(--app-hover);
}

.step-item.active {
  background: var(--app-active);
}

.step-idx {
  font-size: 12px;
  font-weight: 600;
  color: var(--app-text-muted);
  min-width: 28px;
}

.step-main {
  flex: 1;
  min-width: 0;
}

.step-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--app-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.step-sub {
  font-size: 11px;
  color: var(--app-text-muted);
  margin-top: 2px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.step-tags {
  margin-top: 6px;
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.detail-head {
  margin-bottom: 12px;
  flex-shrink: 0;
}

.detail-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--app-text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.detail-sub {
  margin-top: 4px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.detail-tabs {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

/* 右侧详情 Tab 内容区独立滚动，不再随整页滚 */
:deep(.detail-tabs .el-tabs__content) {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding-right: 4px;
}

.section {
  margin-bottom: 16px;
}

.section-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--app-text);
  margin-bottom: 6px;
}

.muted {
  color: var(--app-text-muted);
  font-size: 12px;
}

.mono {
  font-family: var(--app-font-mono);
  font-size: 12px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  display: inline-block;
  max-width: 100%;
}

.config-cell {
  max-height: 120px;
  overflow: auto;
}

:deep(.el-card__body) {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

/* 顶部摘要卡内容不撑满（避免趋势图卡被拉高） */
:deep(.summary-card .el-card__body) {
  flex: 0 0 auto;
}

:deep(.el-timeline-item__tail) {
  left: 6px;
}

:deep(.el-timeline-item__node) {
  cursor: pointer;
}
</style>

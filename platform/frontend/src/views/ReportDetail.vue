<template>
  <div class="report" v-loading="loading">
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
              <span class="pass">{{ passedCount }}</span>
              <span class="sep">/</span>
              <span>{{ totalCount }}</span>
            </div>
          </div>
          <div class="metric">
            <div class="metric-label">断言通过 / 总数</div>
            <div class="metric-value">
              <span class="pass">{{ assertionPassed }}</span>
              <span class="sep">/</span>
              <span>{{ assertionTotal }}</span>
            </div>
          </div>
          <div class="metric">
            <div class="metric-label">开始时间</div>
            <div class="metric-value small" :title="record?.started_at ?? '-'">{{ record?.started_at ?? '-' }}</div>
          </div>
          <div class="metric">
            <div class="metric-label">耗时</div>
            <div class="metric-value">{{ durationText }}</div>
          </div>
        </div>
      </el-card>

      <!-- 各步骤响应耗时趋势图（纯 SVG，零依赖） -->
      <el-card v-if="steps.length" shadow="never" class="trend-card" @mouseleave="hideTrendTip">
        <div class="trend-head">
          <span class="trend-title">步骤响应耗时趋势</span>
          <span class="trend-sub">单位 ms · 最大值 {{ trendMax }} ms · 平均 {{ trendAvg }} ms · 悬浮节点查看详情</span>
        </div>
        <svg class="trend-svg" :viewBox="`0 0 ${trendWidth} ${trendHeight}`" preserveAspectRatio="none">
          <!-- 网格线 -->
          <line v-for="g in trendGrids" :key="g.y" :x1="g.x1" :y1="g.y" :x2="g.x2" :y2="g.y" stroke="currentColor" class="grid-line" stroke-width="1" />
          <!-- Y 轴刻度 -->
          <text v-for="g in trendGrids" :key="'t'+g.y" :x="4" :y="g.y - 2" font-size="10" class="axis-text">{{ g.label }}</text>
          <!-- 折线 -->
          <polyline :points="trendPoints" fill="none" class="trend-line" stroke-width="2" stroke-linejoin="round" stroke-linecap="round" />
          <!-- 数据点 -->
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
            />
          </g>
          <!-- X 轴标签 -->
          <text v-for="(p, i) in trendDots" :key="'x'+i" :x="p.x" :y="trendHeight - 4" font-size="10" class="axis-text" text-anchor="middle">{{ i + 1 }}</text>
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

    <!-- 主体：时间轴 + 详情 -->
    <div class="body">
      <!-- 左侧时间轴 -->
      <el-card shadow="never" class="steps-card">
        <div class="steps-head">步骤时间轴（{{ steps.length }}）</div>
        <el-scrollbar class="steps-scroll">
          <el-timeline>
            <el-timeline-item
              v-for="(s, idx) in steps"
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
                <div class="step-idx">#{{ idx + 1 }}</div>
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
              <el-table :data="currentStep.assertions" size="small" border>
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
                    <span class="muted">{{ row.message ?? '—' }}</span>
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
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import VueJsonPretty from 'vue-json-pretty'
import 'vue-json-pretty/lib/styles.css'
import EmptyState from '@/components/EmptyState.vue'
import { execApi, caseApi, type ExecutionRecord, type StepRecord } from '@/api'
import { generateReportFilename } from '@/utils/reportFilename'

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

const durationText = computed(() => {
  if (!record.value?.started_at || !record.value?.ended_at) return '-'
  const start = new Date(record.value.started_at).getTime()
  const end = new Date(record.value.ended_at).getTime()
  const ms = end - start
  if (ms < 1000) return `${ms} ms`
  return `${(ms / 1000).toFixed(2)} s`
})

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

function statusType(s?: string) {
  if (s === 'success') return 'success'
  if (s === 'running') return 'warning'
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
  if (code >= 400 && code < 500) return 'warning'
  if (code >= 500) return 'danger'
  return 'info'
}

function stepTimeText(s: StepRecord) {
  const start = s.started_at ?? '-'
  const dur = s.started_at && s.ended_at
    ? `${new Date(s.ended_at).getTime() - new Date(s.started_at).getTime()} ms`
    : ''
  return dur ? `${start} · ${dur}` : start
}

// 打印视图专用：JSON 格式化（pre 标签展示，避免 VueJsonPretty 在打印时渲染异常）
function formatJson(val: any): string {
  if (val == null) return '-'
  if (typeof val === 'string') return val
  try {
    return JSON.stringify(val, null, 2)
  } catch {
    return String(val)
  }
}

function csvEscape(val: any): string {
  if (val == null) return ''
  const s = typeof val === 'object' ? JSON.stringify(val) : String(val)
  // 含逗号/引号/换行时用双引号包裹，内部引号转义
  if (/[",\n\r]/.test(s)) return '"' + s.replace(/"/g, '""') + '"'
  return s
}

function exportCsv() {
  if (!steps.value.length) return
  const header = ['序号', '步骤名称', '方法', '路径', 'HTTP状态码', '耗时(ms)', '步骤状态', '断言通过', '断言总数', '断言详情', '请求体', '响应体']
  const rows: string[] = [header.join(',')]
  steps.value.forEach((s, idx) => {
    const assertDetails = (s.assertions || [])
      .map(a => `${a.rule_type}:${a.result ? '通过' : '失败'}(${a.actual_value ?? ''} vs ${a.expected_value ?? ''})`)
      .join(' | ')
    rows.push([
      idx + 1,
      csvEscape(s.api_name || s.node_id || ''),
      s.api_method || '',
      csvEscape(s.api_path || ''),
      s.response_status ?? '',
      s.response_time_ms ?? '',
      s.status || '',
      (s.assertions || []).filter(a => a.result).length,
      (s.assertions || []).length,
      csvEscape(assertDetails),
      csvEscape(s.request_body),
      csvEscape(s.response_body),
    ].join(','))
  })
  // 加 BOM 头确保 Excel 正确识别 UTF-8
  const csv = '\ufeff' + rows.join('\r\n')
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = generateReportFilename({
    caseName: record.value?.case_name,
    envName: record.value?.env_name,
    status: record.value?.status,
    ext: 'csv',
  })
  link.click()
  URL.revokeObjectURL(url)
  ElMessage.success('已导出 CSV')
}

// ===== 导出 HTML 报告（自包含，双击即可在浏览器打开） =====
function esc(s: any): string {
  if (s == null) return ''
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

function exportHtml() {
  const r = record.value
  if (!r) return
  const parts: string[] = []
  parts.push('<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">')
  parts.push('<meta name="viewport" content="width=device-width, initial-scale=1.0">')
  parts.push(`<title>执行报告 #${esc(r.id)}</title>`)
  parts.push('<style>', REPORT_HTML_CSS, '</style>')
  parts.push('</head><body>')
  parts.push('<div class="report">')

  // 报告头
  parts.push('<header class="report-head">')
  parts.push(`<div class="head-title">执行报告 <span class="head-id">#${esc(r.id)}</span></div>`)
  parts.push(`<span class="status-badge status-${esc(r.status)}">${esc(statusText(r.status))}</span>`)
  parts.push('</header>')

  // 摘要
  parts.push('<section class="summary-grid">')
  parts.push(summaryItem('用例', r.case_name || `#${r.case_id}`))
  parts.push(summaryItem('环境', r.env_name || `#${r.env_id}`))
  parts.push(summaryItem('项目', r.project_name || '—'))
  parts.push(summaryItem('执行人', r.created_by_name || '—'))
  parts.push(summaryItem('步骤通过 / 总数', `${passedCount.value} / ${totalCount.value}`, true))
  parts.push(summaryItem('断言通过 / 总数', `${assertionPassed.value} / ${assertionTotal.value}`, true))
  parts.push(summaryItem('开始时间', r.started_at ?? '—'))
  parts.push(summaryItem('结束时间', r.ended_at ?? '—'))
  parts.push(summaryItem('耗时', durationText.value, true))
  parts.push('</section>')

  // 各步骤
  steps.value.forEach((s, idx) => {
    parts.push('<article class="step">')
    parts.push('<header class="step-head">')
    parts.push(`<div class="step-title"><span class="step-idx">#${idx + 1}</span> ${esc(s.api_name || s.node_id || '未命名步骤')}</div>`)
    parts.push(`<span class="step-status status-${esc(s.status)}">${esc(stepStatusText(s.status))}</span>`)
    parts.push('</header>')
    parts.push('<div class="step-meta">')
    parts.push(`<span><em>请求</em> ${esc(s.api_method || '')} ${esc(s.api_path || '')}</span>`)
    parts.push(`<span><em>HTTP</em> ${esc(s.response_status ?? '-')}</span>`)
    parts.push(`<span><em>耗时</em> ${esc(s.response_time_ms ?? '-')} ms</span>`)
    parts.push(`<span><em>开始</em> ${esc(s.started_at ?? '')}</span>`)
    parts.push(`<span><em>结束</em> ${esc(s.ended_at ?? '')}</span>`)
    parts.push('</div>')

    parts.push(jsonSection('请求头', s.request_headers))
    parts.push(jsonSection('请求体', s.request_body))
    parts.push(jsonSection('响应体', s.response_body))

    if (s.assertions && s.assertions.length) {
      parts.push('<section class="subsection">')
      parts.push(`<h3>断言（${s.assertions.length}）</h3>`)
      parts.push('<table class="assert-table"><thead><tr>')
      parts.push('<th class="col-result">结果</th><th class="col-type">类型</th>')
      parts.push('<th class="col-actual">实际值</th><th class="col-expected">期望值</th><th>消息</th>')
      parts.push('</tr></thead><tbody>')
      for (const a of s.assertions) {
        const cls = a.result ? 'pass' : 'fail'
        parts.push('<tr>')
        parts.push(`<td class="${cls}">${a.result ? '✓ 通过' : '✗ 失败'}</td>`)
        parts.push(`<td>${esc(a.rule_type)}</td>`)
        parts.push(`<td class="mono">${esc(a.actual_value ?? '—')}</td>`)
        parts.push(`<td class="mono">${esc(a.expected_value ?? '—')}</td>`)
        parts.push(`<td class="muted">${esc(a.message ?? '—')}</td>`)
        parts.push('</tr>')
      }
      parts.push('</tbody></table>')
      parts.push('</section>')
    }
    parts.push('</article>')
  })

  parts.push('<footer class="report-foot">')
  parts.push(`由 fin-api-test 平台生成 · ${new Date().toLocaleString('zh-CN')}`)
  parts.push('</footer>')

  parts.push('</div></body></html>')

  const html = parts.join('')
  const blob = new Blob([html], { type: 'text/html;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = generateReportFilename({
    caseName: r.case_name,
    envName: r.env_name,
    status: r.status,
    ext: 'html',
  })
  link.click()
  URL.revokeObjectURL(url)
  ElMessage.success('已导出 HTML 报告')
}

function summaryItem(label: string, value: any, highlight = false): string {
  const cls = highlight ? 'metric metric-hl' : 'metric'
  return `<div class="${cls}"><div class="metric-label">${esc(label)}</div><div class="metric-value">${esc(value)}</div></div>`
}

function jsonSection(title: string, val: any): string {
  const text = formatJson(val)
  return `<section class="subsection"><h3>${esc(title)}</h3><pre class="json-block">${esc(text)}</pre></section>`
}

const REPORT_HTML_CSS = `
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif;
  background: #f5f7fa; color: #1f2937; padding: 32px 16px; line-height: 1.6;
}
.report { max-width: 960px; margin: 0 auto; background: #fff; border-radius: 12px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }
.report-head { display: flex; align-items: center; justify-content: space-between; padding: 24px 32px; background: linear-gradient(135deg, #409eff 0%, #2b7fd6 100%); color: #fff; }
.head-title { font-size: 22px; font-weight: 600; }
.head-id { font-weight: 400; opacity: 0.9; margin-left: 4px; }
.status-badge { padding: 4px 14px; border-radius: 999px; font-size: 13px; font-weight: 600; background: rgba(255,255,255,0.25); border: 1px solid rgba(255,255,255,0.4); }
.status-success { background: rgba(255,255,255,0.25); }
.status-failed { background: rgba(255,80,80,0.45); }
.status-running { background: rgba(255,200,80,0.45); }
.summary-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; padding: 20px 32px; background: #fafbfc; border-bottom: 1px solid #ebeef5; }
.metric { padding: 8px 0; }
.metric-label { font-size: 12px; color: #909399; margin-bottom: 4px; }
.metric-value { font-size: 14px; font-weight: 500; color: #303133; word-break: break-all; }
.metric-hl .metric-value { color: #409eff; font-size: 16px; font-weight: 600; }
.step { padding: 24px 32px; border-bottom: 1px solid #ebeef5; }
.step:last-of-type { border-bottom: none; }
.step-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.step-title { font-size: 16px; font-weight: 600; color: #303133; }
.step-idx { display: inline-block; min-width: 28px; height: 24px; line-height: 24px; text-align: center; background: #ecf5ff; color: #409eff; border-radius: 6px; font-size: 13px; margin-right: 8px; }
.step-status { padding: 2px 12px; border-radius: 999px; font-size: 12px; font-weight: 600; }
.step-status.status-success { background: #f0f9eb; color: #67c23a; }
.step-status.status-failed { background: #fef0f0; color: #f56c6c; }
.step-status.status-running { background: #fdf6ec; color: #e6a23c; }
.step-status.status-skipped { background: #f4f4f5; color: #909399; }
.step-meta { display: flex; flex-wrap: wrap; gap: 8px 24px; font-size: 12px; color: #606266; margin-bottom: 16px; padding: 10px 14px; background: #fafbfc; border-radius: 6px; }
.step-meta em { font-style: normal; color: #909399; margin-right: 4px; }
.subsection { margin-bottom: 14px; }
.subsection h3 { font-size: 13px; font-weight: 600; color: #303133; margin-bottom: 6px; padding-left: 8px; border-left: 3px solid #409eff; }
.json-block { background: #1e2a3a; color: #c8d3e0; padding: 12px 14px; border-radius: 6px; font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace; font-size: 12px; line-height: 1.6; white-space: pre-wrap; word-break: break-all; overflow-x: auto; }
.assert-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.assert-table th, .assert-table td { border: 1px solid #ebeef5; padding: 8px 10px; text-align: left; vertical-align: top; }
.assert-table th { background: #fafbfc; font-weight: 600; color: #606266; }
.assert-table .pass { color: #67c23a; font-weight: 600; }
.assert-table .fail { color: #f56c6c; font-weight: 600; }
.assert-table .mono { font-family: 'SFMono-Regular', Consolas, monospace; font-size: 11px; }
.assert-table .muted { color: #909399; }
.col-result { width: 90px; } .col-type { width: 180px; } .col-actual, .col-expected { width: 22%; }
.report-foot { padding: 16px 32px; text-align: center; font-size: 12px; color: #909399; background: #fafbfc; }
@media print { body { padding: 0; background: #fff; } .report { box-shadow: none; border-radius: 0; max-width: none; } .step { break-inside: avoid; } }
`

async function load() {
  const id = Number(route.params.id)
  if (!id) return
  loading.value = true
  try {
    record.value = await execApi.report(id)
    if (steps.value.length && currentStepId.value == null) {
      currentStepId.value = steps.value[0].id
    }
  } catch (e: any) {
    ElMessage.error(e.message)
  } finally {
    loading.value = false
  }
}

watch(
  () => route.params.id,
  () => load()
)

onMounted(load)
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



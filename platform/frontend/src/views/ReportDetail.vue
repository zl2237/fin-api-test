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
            <el-button size="small" @click="exportPdf" :disabled="!steps.length">导出 PDF</el-button>
            <el-button text @click="router.back()">返回</el-button>
          </div>
        </div>
        <div class="summary-grid">
          <div class="metric">
            <div class="metric-label">用例</div>
            <div class="metric-value">{{ record?.case_name || `#${record?.case_id}` || '-' }}</div>
          </div>
          <div class="metric">
            <div class="metric-label">环境</div>
            <div class="metric-value">{{ record?.env_name || `#${record?.env_id}` || '-' }}</div>
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
            <div class="metric-value small">{{ record?.started_at ?? '-' }}</div>
          </div>
          <div class="metric">
            <div class="metric-label">耗时</div>
            <div class="metric-value">{{ durationText }}</div>
          </div>
        </div>
      </el-card>

      <!-- 各步骤响应耗时趋势图（纯 SVG，零依赖） -->
      <el-card v-if="steps.length" shadow="never" class="trend-card">
        <div class="trend-head">
          <span class="trend-title">步骤响应耗时趋势</span>
          <span class="trend-sub">单位 ms · 最大值 {{ trendMax }} ms · 平均 {{ trendAvg }} ms</span>
        </div>
        <svg class="trend-svg" :viewBox="`0 0 ${trendWidth} ${trendHeight}`" preserveAspectRatio="none">
          <!-- 网格线 -->
          <line v-for="g in trendGrids" :key="g.y" :x1="g.x1" :y1="g.y" :x2="g.x2" :y2="g.y" stroke="#eee" stroke-width="1" />
          <!-- Y 轴刻度 -->
          <text v-for="g in trendGrids" :key="'t'+g.y" :x="4" :y="g.y - 2" font-size="10" fill="#999">{{ g.label }}</text>
          <!-- 折线 -->
          <polyline :points="trendPoints" fill="none" stroke="#007aff" stroke-width="2" stroke-linejoin="round" stroke-linecap="round" />
          <!-- 数据点 -->
          <g v-for="(p, i) in trendDots" :key="i">
            <circle :cx="p.x" :cy="p.y" r="3.5" :fill="steps[i].status === 'success' ? '#34c759' : '#ff3b30'" />
            <title>{{ steps[i].api_name || steps[i].node_id }}: {{ p.value }} ms</title>
          </g>
          <!-- X 轴标签 -->
          <text v-for="(p, i) in trendDots" :key="'x'+i" :x="p.x" :y="trendHeight - 4" font-size="10" fill="#999" text-anchor="middle">{{ i + 1 }}</text>
        </svg>
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
            <el-empty v-if="!steps.length" description="暂无步骤" :image-size="60" />
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
                <el-empty v-else description="无请求头" :image-size="40" />
              </div>
              <div class="section">
                <div class="section-title">请求体</div>
                <VueJsonPretty v-if="currentStep.request_body" :data="currentStep.request_body" />
                <el-empty v-else description="无请求体" :image-size="40" />
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
                <el-empty v-else description="无响应体" :image-size="40" />
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
                <el-table-column label="实际值" min-width="140">
                  <template #default="{ row }">
                    <span class="mono">{{ row.actual_value ?? '—' }}</span>
                  </template>
                </el-table-column>
                <el-table-column label="期望值" min-width="140">
                  <template #default="{ row }">
                    <span class="mono">{{ row.expected_value ?? '—' }}</span>
                  </template>
                </el-table-column>
                <el-table-column label="消息" min-width="180">
                  <template #default="{ row }">
                    <span class="muted">{{ row.message ?? '—' }}</span>
                  </template>
                </el-table-column>
              </el-table>
              <el-empty v-if="!currentStep.assertions.length" description="该步骤无断言" :image-size="60" />
            </el-tab-pane>
          </el-tabs>
        </template>
        <el-empty v-else description="请选择左侧步骤查看详情" :image-size="80" />
      </el-card>
    </div>

    <!-- 打印专用视图：导出 PDF 时显示完整报告（含所有步骤），与屏幕交互式布局解耦 -->
    <div class="print-view">
      <h1 class="pv-title">执行报告 #{{ record?.id ?? '-' }}</h1>
      <div class="pv-summary">
        <div><span class="pv-label">用例</span>{{ record?.case_name || `#${record?.case_id}` || '-' }}</div>
        <div><span class="pv-label">环境</span>{{ record?.env_name || `#${record?.env_id}` || '-' }}</div>
        <div><span class="pv-label">状态</span>{{ statusText(record?.status) }}</div>
        <div><span class="pv-label">步骤通过 / 总数</span>{{ passedCount }} / {{ totalCount }}</div>
        <div><span class="pv-label">断言通过 / 总数</span>{{ assertionPassed }} / {{ assertionTotal }}</div>
        <div><span class="pv-label">开始时间</span>{{ record?.started_at ?? '-' }}</div>
        <div><span class="pv-label">结束时间</span>{{ record?.ended_at ?? '-' }}</div>
        <div><span class="pv-label">耗时</span>{{ durationText }}</div>
      </div>

      <div class="pv-step" v-for="(s, idx) in steps" :key="s.id">
        <h2 class="pv-step-title">
          #{{ idx + 1 }} {{ s.api_name || s.node_id || '未命名步骤' }}
          <span class="pv-step-status" :class="pvStatusClass(s.status)">{{ stepStatusText(s.status) }}</span>
        </h2>
        <div class="pv-step-meta">
          <span>{{ s.api_method }} {{ s.api_path }}</span>
          <span>HTTP {{ s.response_status ?? '-' }}</span>
          <span>{{ s.response_time_ms ?? '-' }} ms</span>
          <span>{{ s.started_at ?? '' }} ~ {{ s.ended_at ?? '' }}</span>
        </div>

        <div class="pv-section">
          <h3>请求头</h3>
          <pre class="pv-json">{{ formatJson(s.request_headers) }}</pre>
        </div>
        <div class="pv-section">
          <h3>请求体</h3>
          <pre class="pv-json">{{ formatJson(s.request_body) }}</pre>
        </div>
        <div class="pv-section">
          <h3>响应体</h3>
          <pre class="pv-json">{{ formatJson(s.response_body) }}</pre>
        </div>
        <div class="pv-section" v-if="s.assertions && s.assertions.length">
          <h3>断言（{{ s.assertions.length }}）</h3>
          <table class="pv-assert-table">
            <thead>
              <tr>
                <th>结果</th>
                <th>类型</th>
                <th>实际值</th>
                <th>期望值</th>
                <th>消息</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="a in s.assertions" :key="a.id">
                <td :class="a.result ? 'pv-pass' : 'pv-fail'">{{ a.result ? '通过' : '失败' }}</td>
                <td>{{ a.rule_type }}</td>
                <td>{{ a.actual_value ?? '—' }}</td>
                <td>{{ a.expected_value ?? '—' }}</td>
                <td>{{ a.message ?? '—' }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import VueJsonPretty from 'vue-json-pretty'
import 'vue-json-pretty/lib/styles.css'
import { execApi, caseApi, type ExecutionRecord, type StepRecord } from '@/api'

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

// 打印视图专用：步骤状态样式类
function pvStatusClass(s?: string): string {
  if (s === 'success') return 'pv-ok'
  if (s === 'failed') return 'pv-err'
  return 'pv-warn'
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
  link.download = `execution_report_${record.value?.id ?? Date.now()}.csv`
  link.click()
  URL.revokeObjectURL(url)
  ElMessage.success('已导出 CSV')
}

function exportPdf() {
  // 零依赖方案：调用浏览器打印，用户可选"另存为 PDF"
  // 打印前给 body 加 class 触发打印样式
  document.body.classList.add('printing-report')
  ElMessage.info('在弹出的打印窗口中选择"另存为 PDF"')
  // 下一帧触发打印，确保 class 生效
  requestAnimationFrame(() => {
    window.print()
    document.body.classList.remove('printing-report')
  })
}

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
  border-radius: 16px;
  overflow: hidden;
}

.trend-card {
  background: var(--app-card);
  backdrop-filter: saturate(180%) blur(20px);
  border-radius: 16px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
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
  border-radius: 12px;
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
  color: #34c759;
}

.metric-value .sep {
  color: #aeaeb2;
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
  border-radius: 16px;
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
  border-radius: 10px;
  transition: background 0.15s;
}

.step-item:hover {
  background: var(--app-hover);
}

.step-item.active {
  background: rgba(0, 122, 255, 0.08);
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
  color: #8e8e93;
  font-size: 12px;
}

.mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12px;
  word-break: break-all;
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

<!-- 打印样式：导出 PDF 时隐藏交互式布局，显示完整打印视图 -->
<style>
/* 屏幕上隐藏打印视图 */
.print-view {
  display: none;
}

@media print {
  /* 隐藏应用主框架的侧边栏和顶栏 */
  .printing-report .sidebar,
  .printing-report .topbar,
  .printing-report .summary-actions {
    display: none !important;
  }
  /* 隐藏交互式布局（顶部摘要卡+趋势图、主体时间轴+详情卡） */
  .printing-report .top-row,
  .printing-report .body {
    display: none !important;
  }
  /* 显示打印专用视图 */
  .printing-report .print-view {
    display: block !important;
  }
  /* 报告区域铺满 */
  .printing-report .report {
    height: auto !important;
    overflow: visible !important;
  }
  body {
    background: #fff !important;
  }

  /* ===== 打印视图样式 ===== */
  .print-view {
    font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
    color: var(--app-text);
    padding: 0;
  }
  .pv-title {
    font-size: 22px;
    font-weight: 600;
    margin: 0 0 12px;
  }
  .pv-summary {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 8px;
    margin-bottom: 20px;
    padding: 12px 16px;
    background: var(--app-bg);
    border-radius: 8px;
    font-size: 13px;
  }
  .pv-summary .pv-label {
    display: inline-block;
    min-width: 90px;
    color: var(--app-text-muted);
    margin-right: 6px;
  }
  .pv-step {
    margin-bottom: 24px;
    padding-bottom: 16px;
    border-bottom: 1px solid var(--app-border);
  }
  /* 仅对小元素避免分页截断，长内容（如大JSON）允许跨页 */
  .pv-step-title,
  .pv-step-meta,
  .pv-section h3 {
    break-inside: avoid;
  }
  .pv-step-title {
    font-size: 16px;
    font-weight: 600;
    margin: 0 0 6px;
  }
  .pv-step-status {
    display: inline-block;
    margin-left: 8px;
    padding: 1px 8px;
    border-radius: 10px;
    font-size: 12px;
    font-weight: 500;
  }
  .pv-step-status.pv-ok {
    background: #e8f7ec;
    color: #1a8a3f;
  }
  .pv-step-status.pv-err {
    background: #fdeceb;
    color: #d32f2f;
  }
  .pv-step-status.pv-warn {
    background: #fff4e6;
    color: #b8761a;
  }
  .pv-step-meta {
    display: flex;
    flex-wrap: wrap;
    gap: 16px;
    font-size: 12px;
    color: var(--app-text-muted);
    margin-bottom: 12px;
  }
  .pv-section {
    margin-bottom: 12px;
  }
  .pv-section h3 {
    font-size: 13px;
    font-weight: 600;
    margin: 0 0 4px;
    color: var(--app-text);
  }
  .pv-json {
    background: var(--app-bg);
    border-radius: 6px;
    padding: 8px 10px;
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    font-size: 11px;
    line-height: 1.5;
    white-space: pre-wrap;
    word-break: break-all;
    margin: 0;
  }
  .pv-assert-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 12px;
  }
  .pv-assert-table th,
  .pv-assert-table td {
    border: 1px solid #e0e0e0;
    padding: 5px 8px;
    text-align: left;
    vertical-align: top;
  }
  .pv-assert-table th {
    background: var(--app-bg);
    font-weight: 600;
  }
  .pv-assert-table .pv-pass {
    color: #1a8a3f;
    font-weight: 600;
  }
  .pv-assert-table .pv-fail {
    color: #d32f2f;
    font-weight: 600;
  }
}
</style>

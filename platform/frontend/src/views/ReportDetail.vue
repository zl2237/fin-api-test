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
        用例执行中，每 3 秒自动刷新…
        <el-icon class="is-loading"><Loading /></el-icon>
      </template>
    </el-alert>
    <!-- 执行级错误横幅：登录失败/环境异常等无步骤产出的失败，原因只在 summary.error -->
    <el-alert
      v-if="record?.status === 'failed' && record.summary?.error"
      class="exec-error-banner"
      type="error"
      :closable="false"
      show-icon
    >
      <template #title>执行失败原因：{{ record.summary.error }}</template>
    </el-alert>
    <!-- 页面级加载失败：内联错误块 + 重试（详情页失败后不能只剩空壳） -->
    <div v-if="loadError" class="app-load-error">
      <el-icon><WarningFilled /></el-icon>
      <span>{{ loadError }}</span>
      <el-button size="small" @click="load()">重试</el-button>
    </div>
    <!-- 顶部：紧凑摘要横带（结论 + 分数 + 迷你趋势 + meta/动作），垂直空间让给下方工作区 -->
    <el-card shadow="never" class="summary-card">
      <!-- 结论章：本页唯一 bold 处。票据审核章式 verdict（双线框 + 结论色 + 记录号） -->
      <div :class="['verdict-stamp', verdictClass]" aria-label="执行结论">
        <span class="stamp-text">{{ stampText }}</span>
        <span class="stamp-id">#{{ record?.id ?? '-' }}</span>
      </div>
      <!-- 结论数字：断言/步骤两组分数（排障第一眼要看的两件事） -->
      <div class="verdict-nums">
        <div class="vnum">
          <span class="vnum-label">断言</span>
          <span class="vnum-value app-data">
            <span :class="numClass">{{ assertionPassed }}</span>
            <span class="sep">/</span>
            <span>{{ assertionTotal }}</span>
          </span>
        </div>
        <div class="vnum-divider" aria-hidden="true"></div>
        <div class="vnum">
          <span class="vnum-label">步骤</span>
          <span class="vnum-value app-data">
            <span :class="numClass">{{ passedCount }}</span>
            <span class="sep">/</span>
            <span>{{ totalCount }}</span>
          </span>
        </div>
      </div>
      <!-- 迷你趋势：横带内 sparkline（悬浮提示/点击选步骤与全尺寸版一致） -->
      <StepTrendChart v-if="steps.length" :steps="steps" compact class="summary-trend" @select="currentStepId = $event" />
      <!-- 右侧：上下文 meta + 动作 -->
      <div class="summary-side">
        <div class="summary-meta" :title="metaText">{{ metaText }}</div>
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
    </el-card>

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
        <el-tooltip :content="fs.api_name || fs.node_id || '未命名步骤'" placement="top" popper-class="app-tip">
          <span class="fs-name">{{ fs.api_name || fs.node_id || '未命名步骤' }}</span>
        </el-tooltip>
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
                    <!-- 状态由时间轴节点色表达（去三重冗余）；tag 只承载增量信息：
                         HTTP 码（非 2xx 升 danger 警示）与耗时（mono 机器数据） -->
                    <el-tag v-if="s.response_status" size="small" :type="httpStatusType(s.response_status)" effect="light">
                      HTTP {{ s.response_status }}
                    </el-tag>
                    <el-tag v-if="s.response_time_ms != null" size="small" type="info" effect="light">
                      <span class="mono">{{ s.response_time_ms }} ms</span>
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
                <div class="section-title">前置处理 ({{ currentStep.pre_process?.length || 0 }})</div>
                <template v-if="currentStep.pre_process?.length">
                  <div v-for="(p, i) in currentStep.pre_process" :key="i" class="pre-item">
                    <el-tag size="small" type="info" effect="light">{{ preTypeText(p.type) }}</el-tag>
                    <span v-if="p.type === 'exec_sql'" class="mono pre-val pre-sql">{{ p.sql || '—' }}</span>
                    <template v-else>
                      <span class="mono">{{ p.path || '—' }}</span>
                      <template v-if="p.type !== 'delete_field'">
                        <span class="muted">=</span>
                        <span class="mono pre-val">{{ preValueText(p.value) }}</span>
                      </template>
                    </template>
                  </div>
                </template>
                <EmptyState v-else description="无前置处理" :image-size="40" />
              </div>
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
                <el-tag :type="httpStatusType(currentStep.response_status)" effect="light">
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

            <el-tab-pane :label="`提取 (${currentStep.post_extract?.length || 0})`" name="extract">
              <template v-if="currentStep.post_extract?.length">
                <el-table :data="currentStep.post_extract" size="small" border>
                  <el-table-column label="变量名" min-width="110">
                    <template #default="{ row }">
                      <span class="mono">{{ row.name || '—' }}</span>
                    </template>
                  </el-table-column>
                  <el-table-column label="来源" width="80">
                    <template #default="{ row }">{{ extractSourceText(row.source) }}</template>
                  </el-table-column>
                  <el-table-column label="规则" min-width="240" show-overflow-tooltip>
                    <template #default="{ row }">
                      <span class="mono">{{ extractRuleText(row) }}</span>
                    </template>
                  </el-table-column>
                  <el-table-column label="提取结果" min-width="180" show-overflow-tooltip>
                    <template #default="{ row }">
                      <span v-if="extractActual(row.name) !== undefined" class="mono pre-val">
                        {{ preValueText(extractActual(row.name)) }}
                      </span>
                      <span v-else class="muted">未提取到</span>
                    </template>
                  </el-table-column>
                </el-table>
              </template>
              <EmptyState v-else description="该步骤无提取规则" :image-size="60" />
            </el-tab-pane>

            <el-tab-pane :label="`断言 (${currentStep.assertions.length})`" name="assertions">
              <el-table :data="currentStep.assertions" size="small" border :row-class-name="assertionRowClass">
                <el-table-column label="结果" width="80">
                  <template #default="{ row }">
                    <el-tag :type="row.result ? 'success' : 'danger'" effect="light" size="small">
                      {{ row.result ? '通过' : '失败' }}
                    </el-tag>
                  </template>
                </el-table-column>
                <el-table-column prop="rule_type" label="断言类型" min-width="130" />
                <el-table-column label="规则配置" min-width="260">
                  <template #default="{ row }">
                    <div class="config-cell">
                      <VueJsonPretty v-if="row.rule_config" :data="row.rule_config" :deep="2" />
                      <span v-else class="muted">—</span>
                    </div>
                  </template>
                </el-table-column>
                <el-table-column label="实际值" min-width="130" show-overflow-tooltip>
                  <template #default="{ row }">
                    <!-- 失败行：实际值升结论红 + 加重，与期望值形成 diff 对比强调 -->
                    <span class="mono actual-bad" v-if="!row.result">{{ row.actual_value ?? '—' }}</span>
                    <span v-else class="mono">{{ row.actual_value ?? '—' }}</span>
                  </template>
                </el-table-column>
                <el-table-column label="期望值" min-width="130" show-overflow-tooltip>
                  <template #default="{ row }">
                    <span class="mono">{{ row.expected_value ?? '—' }}</span>
                  </template>
                </el-table-column>
                <el-table-column label="消息" min-width="160" show-overflow-tooltip>
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

    <!-- 断言值完整查看：长 JSON 期望/实际值单元格截断难读，点击弹窗格式化展示 + 一键复制 -->
    <el-dialog v-model="valueDialog.visible" :title="valueDialog.title" width="720px">
      <pre class="value-pre">{{ prettyValue }}</pre>
      <template #footer>
        <el-button @click="valueDialog.visible = false">关闭</el-button>
        <el-button type="primary" @click="copyValue">复制</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Loading, Search, CircleCloseFilled, WarningFilled } from '@element-plus/icons-vue'
import VueJsonPretty from 'vue-json-pretty'
import 'vue-json-pretty/lib/styles.css'
import EmptyState from '@/components/EmptyState.vue'
import StepTrendChart from '@/components/StepTrendChart.vue'
import { execApi, caseApi, type ExecutionRecord, type StepRecord } from '@/api'
import { generateReportFilename } from '@/utils/reportFilename'
import { execStatusType as stepType, execStatusText as statusText } from '@/utils/format'
import { useExecutionRunner } from '@/composables/useExecutionRunner'

const route = useRoute()
const router = useRouter()
const record = ref<ExecutionRecord | null>(null)
const loading = ref(false)
const loadError = ref('')
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
        : (s.status ? statusText(s.status) : '失败')
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

// ===== 断言值完整查看弹窗（长 JSON 不再被单元格截断） =====
const valueDialog = ref({ visible: false, title: '', raw: '' as any })

function openValue(title: string, v: any) {
  if (v == null || v === '') return
  valueDialog.value = { visible: true, title: `断言${title}`, raw: v }
}

/** JSON 值格式化缩进展示；普通字符串原样（保留换行） */
const prettyValue = computed(() => {
  const v = valueDialog.value.raw
  if (typeof v === 'object') return JSON.stringify(v, null, 2)
  if (typeof v === 'string') {
    const s = v.trim()
    if (s.startsWith('{') || s.startsWith('[')) {
      try {
        return JSON.stringify(JSON.parse(s), null, 2)
      } catch {
        // 非合法 JSON 原样展示
      }
    }
    return v
  }
  return String(v)
})

async function copyValue() {
  try {
    await navigator.clipboard.writeText(prettyValue.value)
    ElMessage.success('已复制')
  } catch {
    ElMessage.error('复制失败，请手动选择复制')
  }
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

// 摘要指标：排障工具页数据即显（不做 count-up 滚动演出）
// 耗时格式化：<1s 显示整数 ms，否则秒两位小数
const durationMs = computed(() => {
  if (!record.value?.started_at || !record.value?.ended_at) return 0
  return new Date(record.value.ended_at).getTime() - new Date(record.value.started_at).getTime()
})
function formatDuration(ms: number): string {
  if (ms < 1000) return `${Math.round(ms)} ms`
  return `${(ms / 1000).toFixed(2)} s`
}
const durationText = computed(() => formatDuration(durationMs.value))

// ===== 结论章（verdict）：状态 → 章文案/配色；执行中为静态琥珀章（不做脉冲动画） =====
const verdictClass = computed(() => {
  const s = record.value?.status
  if (s === 'success') return 'is-success'
  if (s === 'failed') return 'is-failed'
  if (s === 'running') return 'is-running'
  return 'is-unknown'
})
const stampText = computed(() => {
  const s = record.value?.status
  if (s === 'success') return '通过'
  if (s === 'failed') return '未通过'
  if (s === 'running') return '执行中'
  return '—'
})
/** 结论分子配色：通过=绿、失败=红、执行中/未知=墨色 */
const numClass = computed(() => {
  const s = record.value?.status
  if (s === 'success') return 'num-ok'
  if (s === 'failed') return 'num-bad'
  return ''
})
/** 上下文 meta 单行：用例 / 环境 / 开始时间 / 耗时（空格分隔，title 提供全文） */
const metaText = computed(() => {
  const r = record.value
  return [
    r?.case_name || `#${r?.case_id}` || '-',
    r?.env_name || `#${r?.env_id}` || '-',
    r?.started_at ?? '-',
    durationText.value,
  ].join('   ')
})

// 状态映射统一走 utils/format（记录级与步骤级共用 execStatusType/execStatusText，含 skipped）

function httpStatusType(code?: number) {
  if (code == null) return 'info'
  if (code >= 200 && code < 300) return 'success'
  // 接口测试语义：非 2xx 即请求层面失败（原 4xx 归 warning 与失败层级冲突）
  if (code >= 400) return 'danger'
  return 'info'
}

// ===== 前置处理 / 后置提取展示辅助（文案与 PreProcessTable 配置端一致） =====
const PRE_TYPE_TEXT: Record<string, string> = {
  set_field: '设置字段',
  add_field: '新增字段',
  delete_field: '删除字段',
  iterate_set: '遍历赋值',
  exec_sql: '执行 SQL',
}

function preTypeText(t?: string) {
  return (t && PRE_TYPE_TEXT[t]) || t || '—'
}

/** 快照值为执行时规则原文：字符串原样（可含 ${} 引用），对象/数组 JSON 化 */
function preValueText(v: any): string {
  if (v == null) return '—'
  if (typeof v === 'string') return v
  try {
    return JSON.stringify(v)
  } catch {
    return String(v)
  }
}

function extractSourceText(s?: string) {
  return s === 'db' ? '数据库' : '响应'
}

/** db 规则展示 SQL + 取值字段；response 规则展示 JSONPath */
function extractRuleText(r: any): string {
  if (r?.source === 'db') {
    const sql = r.sql || '—'
    return r.field ? `${sql} → ${r.field}` : sql
  }
  return r?.json_path || '—'
}

/** 从实际提取结果中取变量值；undefined 表示未提取到（规则失败或值缺失） */
function extractActual(name?: string) {
  if (!name) return undefined
  const vars = currentStep.value?.extracted_vars
  return vars && Object.prototype.hasOwnProperty.call(vars, name) ? vars[name] : undefined
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

// running 态轮询：单次触发静默刷新，load 内部再决定是否续排（保持原递归语义）
const runner = useExecutionRunner()
let stopRefresh: (() => void) | null = null

function stopPolling() {
  stopRefresh?.()
  stopRefresh = null
}

/** running 态自动轮询直到出结果；终态即停（含页面失活兜底） */
function schedulePollIfRunning() {
  stopPolling()
  if (record.value?.status !== 'running') return
  stopRefresh = runner.refreshWhileRunning(async () => {
    await load(true)
    return false // load(true) 完成后会再调 schedulePollIfRunning，由它决定续排与否
  }, { interval: 3000 })
}

async function load(silent = false) {
  const id = Number(route.params.id)
  if (!id) return
  if (!silent) {
    loading.value = true
    loadError.value = ''
  }
  try {
    record.value = await execApi.report(id)
    // 套件主记录无步骤明细，转套件报告页（成员×数据行层级视图）
    if (record.value?.summary?.suite) {
      router.replace(`/suite-reports/${id}`)
      return
    }
    if (steps.value.length && currentStepId.value == null) {
      // 默认定位首个失败步骤（排障第一诉求）；无失败则回第 1 步
      const firstFailed = steps.value.find((s) => s.status !== 'success')
      currentStepId.value = (firstFailed ?? steps.value[0]).id
    }
    schedulePollIfRunning()
  } catch (e: any) {
    // 静默轮询失败不清已有数据、不打错误块（瞬时网络抖动）；首次加载失败才展示错误块 + 重试
    if (!silent) loadError.value = e?.message || '加载失败'
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

/* ===== 摘要横带：紧凑单行（窄窗口自动换行防裁切），高度最小化，垂直空间让给工作区 ===== */
.summary-card {
  background: var(--app-card);
  border-radius: var(--app-radius-lg);
  overflow: hidden;
  flex-shrink: 0;
}

.summary-card :deep(.el-card__body) {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  row-gap: 8px;
  gap: 18px;
  padding: 10px 16px;
}

/* 结论章：票据审核章（双线框 = border 外线 + inset outline 内线），结论色经 currentColor 派生 */
.verdict-stamp {
  flex-shrink: 0;
  width: 74px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1px;
  padding: 8px 6px 7px;
  border: 2px solid currentColor;
  outline: 1px solid currentColor;
  outline-offset: -5px;
  border-radius: var(--app-radius-sm);
}
.verdict-stamp.is-success { color: var(--app-success-text); }
.verdict-stamp.is-failed { color: var(--app-danger-text); }
.verdict-stamp.is-running { color: var(--app-warn-text); }
.verdict-stamp.is-unknown { color: var(--app-text-faint); }
.stamp-text {
  font-size: 15px;
  font-weight: 700;
  letter-spacing: 0.12em;
  padding-left: 0.12em; /* 抵消末字间距，视觉居中 */
  line-height: 1.2;
}
.stamp-id {
  /* 记录号无需语义色：中性 muted 全对比度（原 accent 78% 透明仅 ~3:1） */
  font-family: var(--app-font-mono);
  font-variant-numeric: tabular-nums;
  font-size: 10px;
  color: var(--app-text-muted);
}

/* 结论数字：断言/步骤两组 mono 分数 */
.verdict-nums {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 16px;
}
.vnum {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.vnum-label {
  font-size: 11px;
  color: var(--app-text-muted);
}
.vnum-value {
  font-size: 20px;
  font-weight: 700;
  line-height: 1.1;
  color: var(--app-text);
  white-space: nowrap;
}
.vnum-value .num-ok { color: var(--app-success-text); }
.vnum-value .num-bad { color: var(--app-danger-text); }
.vnum-value .sep {
  color: var(--app-text-faint);
  font-weight: 500;
  margin: 0 2px;
}
.vnum-divider {
  width: 1px;
  height: 30px;
  background: var(--app-border);
}

/* 迷你趋势：横带中间弹性占位，左右发丝线分隔 */
.summary-trend {
  flex: 1 1 260px;
  min-width: 220px;
  border-left: 1px solid var(--app-border);
  border-right: 1px solid var(--app-border);
  padding: 0 14px;
}

/* 右侧列：meta（上）+ 动作（下），整体贴右 */
.summary-side {
  margin-left: auto;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 6px;
}

/* 上下文 meta：单行小字（省略号 + title 全文） */
.summary-meta {
  max-width: 360px;
  font-size: 12px;
  color: var(--app-text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.summary-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
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
  /* 失败列表的悬停保持中性底（原主色淡底会让失败语义跑色） */
  background: var(--app-hover);
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
/* 断言失败行实际值：结论红 + 加重（与期望值构成 diff 对比） */
.actual-bad {
  color: var(--app-danger-text);
  font-weight: 600;
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

/* 前置处理动作行：标签 + path = 值（值可含 ${} 引用，规则原文快照） */
.pre-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 3px 0;
  flex-wrap: wrap;
}

.pre-val {
  color: var(--app-text);
  max-width: 420px;
  vertical-align: middle;
}

/* 前置 SQL 原文（单行长 SQL 自动换行） */
.pre-sql {
  white-space: pre-wrap;
  word-break: break-all;
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
/* 可点击展开的值单元格：截断内容点击弹窗看全量 */
.cell-expand {
  cursor: pointer;
  border-bottom: 1px dashed var(--app-border);
}
.cell-expand:hover {
  color: var(--el-color-primary);
}
.value-pre {
  font-family: var(--app-font-mono);
  font-size: 12px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 60vh;
  overflow: auto;
  margin: 0;
  background: var(--app-hover);
  border-radius: var(--app-radius-xs);
  padding: 12px;
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

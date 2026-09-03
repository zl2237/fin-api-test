<template>
  <div class="home-page">
    <!-- 无项目：引导创建（首登主路径） -->
    <el-card v-if="!store.currentProjectId" shadow="never" class="card empty-project">
      <EmptyState description="还没有项目。创建一个项目，把要测的接口和用例装进来" :image-size="110">
        <el-button type="primary" @click="router.push('/projects')">创建项目</el-button>
        <el-button @click="openGuide">先看上手指南</el-button>
      </EmptyState>
    </el-card>

    <template v-else>
      <!-- ===== 欢迎条：问候 + 当前上下文 + 上次执行 + 主操作 ===== -->
      <section class="welcome">
        <div class="welcome-text">
          <h1 class="welcome-title">{{ greeting }}，{{ displayName }}<span class="welcome-project"> · {{ currentProjectName }}</span></h1>
          <p v-if="lastExec" class="welcome-sub">
            上次执行：{{ formatRelativeTime(lastExec.started_at) }} · {{ lastExec.case_name || `#${lastExec.case_id}` }}
            <span :class="['last-status', `is-${lastExec.status}`]">{{ statusText(lastExec.status) }}</span>
            <span v-if="lastExec.summary?.total">（{{ lastExec.summary.passed ?? 0 }}/{{ lastExec.summary.total }} 步通过）</span>
          </p>
          <p v-else class="welcome-sub">当前项目还没有执行记录</p>
        </div>
        <!-- 品牌 DAG 插画缩小版（与 favicon/登录页同视觉语言） -->
        <svg class="welcome-art" viewBox="0 0 150 100" fill="none" aria-hidden="true">
          <path d="M30 26 C 48 26, 44 50, 62 50" class="dag-edge" />
          <path d="M30 74 C 48 74, 44 50, 62 50" class="dag-edge" />
          <path d="M96 50 C 110 50, 106 26, 124 26" class="dag-edge" />
          <rect x="6" y="12" width="34" height="28" rx="2" class="dag-node" />
          <rect x="6" y="60" width="34" height="28" rx="2" class="dag-node" />
          <rect x="62" y="36" width="36" height="28" rx="2" class="dag-node dag-node-main" />
          <rect x="120" y="12" width="22" height="28" rx="2" class="dag-badge" />
          <path d="M126 24 l3.5 4.5 l6 -7.5" class="dag-check" />
        </svg>
      </section>

      <!-- ===== 统计行：当前项目概览（点击直达对应页面；语义化 <button> 保证键盘可达） ===== -->
      <section class="stats">
        <button type="button" class="stat" @click="router.push('/apis')">
          <b>{{ loading ? '…' : apiCount }}</b>
          <span>接口</span>
        </button>
        <button type="button" class="stat" @click="router.push('/cases')">
          <b>{{ loading ? '…' : caseCount }}</b>
          <span>用例</span>
        </button>
        <button type="button" class="stat" @click="router.push('/executions')">
          <b>{{ loading ? '…' : weekStats.count }}</b>
          <span>7 天执行</span>
        </button>
        <button type="button" class="stat" @click="router.push('/executions')">
          <b :class="{ 'is-pass': (weekStats.rate ?? 0) >= 90 }">{{ loading ? '…' : (weekStats.rate === null ? '—' : weekStats.rate + '%') }}</b>
          <span>7 天通过率</span>
        </button>
      </section>

      <!-- ===== 主区：最近执行 + 快速执行/指南 ===== -->
      <div class="workbench">
        <!-- 最近执行 -->
        <section class="panel">
          <header class="panel-head">
            <h3>最近执行</h3>
            <div class="panel-tools">
              <el-button text size="small" title="刷新" aria-label="刷新" @click="loadHome">
                <el-icon><Refresh /></el-icon>
              </el-button>
              <el-button text type="primary" size="small" @click="router.push('/executions')">
                全部记录<el-icon class="go-icon"><ArrowRight /></el-icon>
              </el-button>
            </div>
          </header>

          <!-- 加载失败：内联错误块 + 重试（全局 .app-load-error） -->
          <div v-if="loadError" class="app-load-error">
            <el-icon><WarningFilled /></el-icon>
            <span>{{ loadError }}</span>
            <el-button size="small" @click="loadHome">重试</el-button>
          </div>

          <el-skeleton v-else-if="loading" :rows="6" animated class="skeleton-wrap" />

          <EmptyState
            v-else-if="!recentExecs.length"
            description="当前项目还没有执行记录"
            :image-size="80"
          >
            <el-button type="primary" @click="router.push('/cases')">去执行用例</el-button>
          </EmptyState>

          <div v-else class="exec-list">
            <button
              v-for="r in recentExecs"
              :key="r.id"
              type="button"
              class="exec-row"
              @click="router.push(`/reports/${r.id}`)"
            >
              <span :class="['exec-dot', `is-${r.status}`]">
                <el-icon v-if="r.status === 'running'" class="is-loading"><Loading /></el-icon>
              </span>
              <span class="exec-name" :title="r.case_name || `#${r.case_id}`">{{ r.case_name || `#${r.case_id}` }}</span>
              <span class="exec-env" :title="r.env_name || `环境#${r.env_id}`">{{ r.env_name || `环境#${r.env_id}` }}</span>
              <span class="exec-summary" :class="`is-${r.status}`">
                {{ r.status === 'running' ? `${r.summary?.total ?? '?'} 步` : `${r.summary?.passed ?? 0}/${r.summary?.total ?? 0}` }}
              </span>
              <span class="exec-time" :title="formatTime(r.started_at)">{{ formatRelativeTime(r.started_at) }}</span>
            </button>
          </div>
        </section>

        <!-- 右栏：快速执行 + 指南入口 -->
        <div class="side-col">
          <section class="panel">
            <header class="panel-head">
              <h3>快速执行</h3>
              <el-button text type="primary" size="small" @click="router.push('/cases')">全部用例</el-button>
            </header>
            <div v-if="!recentCases.length" class="quick-empty">还没有用例，去 <el-button text type="primary" size="small" @click="router.push('/cases')">创建第一个</el-button></div>
            <ul v-else class="quick-list">
              <li v-for="c in recentCases" :key="c.id" class="quick-row">
                <span class="quick-name" :title="c.name">{{ c.name }}</span>
                <el-button
                  link
                  type="primary"
                  size="small"
                  :loading="runningId === c.id"
                  :disabled="runningId !== null && runningId !== c.id"
                  @click="runCase(c)"
                >
                  <el-icon v-if="runningId !== c.id"><VideoPlay /></el-icon>运行
                </el-button>
              </li>
            </ul>
          </section>

          <section class="panel guide-panel">
            <header class="panel-head"><h3>上手指南</h3></header>
            <div class="guide-links">
              <el-button text type="primary" @click="openGuide">五步上手流程</el-button>
              <el-button text type="primary" @click="store.openCoreCapability('expression')">表达式语法</el-button>
              <el-button text type="primary" @click="store.openCoreCapability('assertion')">17 种断言</el-button>
            </div>
            <div class="guide-kbd">
              <span><kbd>Ctrl</kbd>/<kbd>⌘</kbd> + <kbd>K</kbd> 全局搜索</span>
              <span><kbd>Ctrl</kbd> + <kbd>Enter</kbd> 执行选中用例</span>
            </div>
          </section>
        </div>
      </div>
    </template>

    <!-- ===== 上手指南抽屉（自包含组件：v-model 显隐，首登自动展示与常量内聚） ===== -->
    <HomeGuideDrawer v-model="guideVisible" />
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowRight, Refresh, VideoPlay, Loading, WarningFilled } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useAppStore } from '@/stores'
import { apiApi, caseApi, execApi } from '@/api'
import type { ExecutionRecord, TestCase } from '@/api'
import { formatTime, formatRelativeTime, execStatusText as statusText } from '@/utils/format'
import EmptyState from '@/components/EmptyState.vue'
import HomeGuideDrawer from '@/components/HomeGuideDrawer.vue'

const router = useRouter()
const store = useAppStore()

// ===== 数据 =====
const loading = ref(false)
const loadError = ref('')
const apiCount = ref(0)
const caseCount = ref(0)
const recentCases = ref<TestCase[]>([])
const recentExecs = ref<ExecutionRecord[]>([])

const displayName = computed(() => store.user?.name || store.user?.username || '用户')
const currentProjectName = computed(() => store.projects.find(p => p.id === store.currentProjectId)?.name || '当前项目')
const lastExec = computed(() => recentExecs.value[0])
const greeting = computed(() => {
  const h = new Date().getHours()
  if (h < 6) return '夜深了'
  if (h < 12) return '早上好'
  if (h < 14) return '中午好'
  if (h < 18) return '下午好'
  return '晚上好'
})

// 7 天执行量与通过率（口径与执行记录页一致：最近 200 条本地过滤）
const weekStats = computed(() => {
  const now = Date.now()
  const week = recentExecs.value.filter(r => r.started_at && now - new Date(r.started_at).getTime() < 7 * 864e5)
  const done = week.filter(r => r.status === 'success' || r.status === 'failed')
  const passed = week.filter(r => r.status === 'success').length
  return {
    count: week.length,
    rate: done.length ? Math.round((passed / done.length) * 1000) / 10 : null,
  }
})

async function loadHome() {
  if (!store.currentProjectId) return
  loading.value = true
  loadError.value = ''
  try {
    const [apis, cases, execs] = await Promise.all([
      apiApi.list(store.currentProjectId),
      caseApi.list(store.currentProjectId),
      execApi.list({ project_id: store.currentProjectId, limit: 200 }),
    ])
    apiCount.value = apis.length
    caseCount.value = cases.length
    recentCases.value = cases.slice(0, 3)
    recentExecs.value = execs.slice(0, 8)
  } catch (e: any) {
    loadError.value = e?.message || '加载失败'
  } finally {
    loading.value = false
  }
}

// 项目切换即刷新工作台（immediate 兜底首次挂载时序）
watch(() => store.currentProjectId, () => { loadHome() }, { immediate: true })

// ===== 快速执行 =====
const runningId = ref<number | null>(null)
async function runCase(c: TestCase) {
  if (!store.currentEnvId) return ElMessage.warning('请先在顶部选择环境')
  runningId.value = c.id
  try {
    const rec = await caseApi.execute(c.id, store.currentEnvId)
    ElMessage.success('已开始执行，正在跳转报告')
    router.push(`/reports/${rec.id}`)
  } catch (e: any) {
    ElMessage.error(e?.message || '执行失败')
  } finally {
    runningId.value = null
  }
}

// ===== 上手指南（显隐状态留父级供入口按钮使用；内容与首登逻辑内聚在 HomeGuideDrawer） =====
const guideVisible = ref(false)
function openGuide() {
  guideVisible.value = true
}
</script>

<style scoped>
.home-page {
  max-width: 1080px;
  margin: 0 auto;
  padding: 20px 24px 40px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.empty-project { border-radius: var(--app-radius-lg); }

/* ===== 欢迎条：实底面板 + 左侧主色状态轨（工程面板语言，去渐变） ===== */
.welcome {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  padding: 22px 28px;
  border-radius: var(--app-radius-lg);
  background: var(--app-card-solid);
  border: 1px solid var(--app-border);
  border-left: 3px solid var(--app-primary);
  box-shadow: var(--app-shadow-sm);
  min-height: 96px;
  overflow: hidden;
}
.welcome-text { min-width: 0; }
.welcome-title {
  font-size: 22px;
  font-weight: 700;
  color: var(--app-text);
  margin: 0 0 8px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.welcome-project { font-size: 15px; font-weight: 500; color: var(--app-text-muted); }
.welcome-sub {
  font-size: 13px;
  color: var(--app-text-muted);
  margin: 0;
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}
.last-status { font-weight: 600; }
.last-status.is-success { color: var(--app-success-text); }
.last-status.is-failed { color: var(--app-danger-text); }
.last-status.is-running { color: var(--app-warn-text); }

.welcome-art { flex-shrink: 0; width: 150px; height: 100px; }
.dag-node {
  fill: color-mix(in srgb, var(--app-primary) 8%, var(--app-card-solid));
  stroke: var(--app-primary);
  stroke-width: 1.4;
}
.dag-node-main { fill: color-mix(in srgb, var(--app-primary) 16%, var(--app-card-solid)); }
.dag-edge {
  stroke: var(--app-primary);
  stroke-width: 1.4;
  stroke-dasharray: 5 4;
  opacity: 0.6;
  fill: none;
}
.dag-badge { fill: var(--app-success); opacity: 0.18; }
.dag-check { stroke: var(--app-success); stroke-width: 2.2; stroke-linecap: round; stroke-linejoin: round; fill: none; }

/* ===== 统计行：台账条（单一面板 + 列间发丝线，替代 4 张等分卡片的仪表盘套路） ===== */
.stats {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  background: var(--app-card-solid);
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius);
}
.stat {
  padding: 16px 20px;
  min-height: 72px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 2px;
  cursor: pointer;
  transition: background 0.15s;
}
/* 台账列分隔：发丝线，首列无 */
.stat + .stat {
  border-left: 1px solid var(--app-border);
}
.stat:hover {
  background: var(--app-hover);
}
.stat b {
  font-size: 22px;
  font-weight: 700;
  color: var(--app-text);
  /* 机器数据 mono 身份：计数/百分比用等宽表格数字 */
  font-family: var(--app-font-mono);
  font-variant-numeric: tabular-nums;
  line-height: 1.2;
}
.stat b.is-pass { color: var(--app-success-text); }
.stat span { font-size: 12px; color: var(--app-text-muted); }
/* .stat / .exec-row 为语义化 <button>：清除浏览器默认按钮外观，保持台账条视觉 */
.stat,
.exec-row {
  appearance: none;
  font: inherit;
  color: inherit;
  text-align: left;
  background: transparent;
  border: none;
  width: 100%;
}
/* .stat + .stat 列分隔线（button 无 border 时重绘） */
.stat + .stat {
  border-left: 1px solid var(--app-border);
}
/* 键盘焦点可见（规范：focus-visible 焦点环） */
.stat:focus-visible,
.exec-row:focus-visible {
  outline: 2px solid var(--app-primary);
  outline-offset: -2px;
}

/* ===== 主区两栏 ===== */
.workbench {
  display: grid;
  grid-template-columns: 1.65fr 1fr;
  gap: 12px;
  align-items: start;
}
.panel {
  background: var(--app-card-solid);
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius);
  padding: 14px 16px;
  min-width: 0; /* grid item：防行内长内容（环境名等）把列宽撑破 */
}
.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
  min-height: 28px;
}
.panel-head h3 { font-size: 14px; font-weight: 600; color: var(--app-text); margin: 0; }
.panel-tools { display: flex; align-items: center; gap: 2px; }
.go-icon { margin-left: 2px; }

/* 最近执行列表：固定行高，状态点 + 摘要 + 相对时间 */
.exec-list { list-style: none; margin: 0; padding: 0; }
.exec-row {
  display: flex;
  align-items: center;
  gap: 10px;
  height: 36px;
  padding: 0 8px;
  border-radius: var(--app-radius-sm);
  cursor: pointer;
  font-size: 13px;
}
.exec-row:hover { background: var(--app-hover); }
.exec-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
.exec-dot.is-success { background: var(--app-success); }
.exec-dot.is-failed { background: var(--app-danger); }
.exec-dot.is-running { background: transparent; }
.exec-dot.is-running .el-icon { font-size: 13px; color: var(--app-warn-text); }
.exec-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--app-text);
}
.exec-env {
  flex-shrink: 0;
  max-width: 150px; /* 环境名过长截断，防把行/卡片撑宽 */
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 11.5px;
  color: var(--app-text-muted);
  border: 1px solid var(--app-border);
  border-radius: 5px;
  padding: 1px 6px;
}
.exec-summary { flex-shrink: 0; font-size: 12px; color: var(--app-text-muted); font-variant-numeric: tabular-nums; }
.exec-summary.is-failed { color: var(--app-danger-text); }
.exec-summary.is-success { color: var(--app-success-text); }
.exec-time { flex-shrink: 0; min-width: 64px; text-align: right; font-size: 12px; color: var(--app-text-faint); }

/* 右栏：min-width:0 斩断 grid min-content 传播（快速执行里的超长用例名 nowrap 不再撑爆列宽） */
.side-col { display: flex; flex-direction: column; gap: 12px; min-width: 0; }
.side-col .panel { width: 100%; }
.quick-list { list-style: none; margin: 0; padding: 0; min-width: 0; }
.quick-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  height: 38px;
  padding: 0 10px;
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius-sm);
  margin-bottom: 6px;
  min-width: 0;
  transition: border-color 0.15s;
}
.quick-row:hover { border-color: color-mix(in srgb, var(--app-primary) 40%, var(--app-border)); }
.quick-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
  color: var(--app-text);
}
.quick-empty { font-size: 13px; color: var(--app-text-muted); padding: 8px 0; }

/* 指南面板 */
.guide-links { display: flex; flex-direction: column; align-items: flex-start; gap: 2px; }
.guide-kbd {
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px dashed var(--app-border);
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 12px;
  color: var(--app-text-muted);
}
kbd {
  font-family: var(--app-font-mono);
  font-size: 11px;
  background: var(--app-bg);
  border: 1px solid var(--app-border);
  border-bottom-width: 2px;
  border-radius: 5px;
  padding: 0 5px;
  color: var(--app-text);
}

/* ===== 指南抽屉样式已随 HomeGuideDrawer 组件内聚 ===== */

/* ===== 窄屏 ===== */
@media (max-width: 960px) {
  .workbench { grid-template-columns: 1fr; }
  .stats { grid-template-columns: repeat(2, 1fr); }
  .welcome-art { display: none; }
}
</style>

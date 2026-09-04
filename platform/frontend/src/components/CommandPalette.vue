<template>
  <el-dialog
    v-model="visible"
    :show-close="false"
    :close-on-click-modal="true"
    width="560px"
    class="cmd-palette"
    top="18vh"
    @opened="onOpened"
  >
    <div class="cmd-input-wrap">
      <el-icon class="cmd-icon"><Search /></el-icon>
      <input
        ref="inputRef"
        v-model="keyword"
        class="cmd-input"
        aria-label="全局搜索"
        placeholder="搜索用例 / 接口 / 数据集 / 环境 / 文件 / 字典，或输入命令"
        @keydown.down.prevent="moveDown"
        @keydown.up.prevent="moveUp"
        @keydown.enter.prevent="onEnter"
      />
      <el-tag size="small" effect="plain" round class="cmd-kbd">Esc</el-tag>
    </div>
    <div class="cmd-list">
      <div
        v-for="(item, idx) in results"
        :key="item.key"
        class="cmd-item"
        :class="{ active: idx === activeIdx }"
        @mouseenter="activeIdx = idx"
        @click="onSelect(item)"
      >
        <el-icon class="cmd-item-icon"><component :is="iconComp(item.type)" /></el-icon>
        <div class="cmd-item-main">
          <el-tooltip :content="item.title" placement="top" popper-class="app-tip">
            <div class="cmd-item-title">{{ item.title }}</div>
          </el-tooltip>
          <el-tooltip :content="item.sub" placement="top" popper-class="app-tip">
            <div class="cmd-item-sub">{{ item.sub }}</div>
          </el-tooltip>
        </div>
        <el-tag size="small" type="info" effect="plain" round>{{ item.kindLabel }}</el-tag>
      </div>
      <EmptyState v-if="!results.length" description="无匹配项" :image-size="40" />
    </div>
    <div class="cmd-footer">
      <span>↑↓ 选择</span>
      <span>↵ 跳转</span>
      <span>Esc 关闭</span>
    </div>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted, shallowRef } from 'vue'
import { useRouter } from 'vue-router'
import { Search, Share, Connection, Folder, Document, Coin, Monitor, Paperclip, Notebook } from '@element-plus/icons-vue'
import {
  caseApi, apiApi, projectApi, datasetApi, envApi, fileApi, dictApi,
  type TestCase, type ApiDef, type Project, type DataSet, type Environment, type TestFile, type FieldDictionary,
} from '@/api'
import { useAppStore } from '@/stores'
import { fuzzyMatch } from '@/utils/fuzzy'
import { toPinyinInitials } from '@/utils/pinyin'
import EmptyState from '@/components/EmptyState.vue'

const router = useRouter()
const store = useAppStore()

const visible = ref(false)
const keyword = ref('')
const inputRef = shallowRef<HTMLInputElement | null>(null)
const activeIdx = ref(0)

const cases = ref<TestCase[]>([])
const apis = ref<ApiDef[]>([])
const projects = ref<Project[]>([])
const datasets = ref<DataSet[]>([])
const envs = ref<Environment[]>([])
const files = ref<TestFile[]>([])
const dicts = ref<FieldDictionary[]>([])

type ItemType = 'case' | 'api' | 'project' | 'dataset' | 'env' | 'file' | 'dict' | 'nav'
interface CmdItem {
  key: string
  type: ItemType
  title: string
  sub: string
  kindLabel: string
  action: () => void
}

function iconComp(type: ItemType) {
  return {
    case: Share, api: Connection, project: Folder,
    dataset: Coin, env: Monitor, file: Paperclip, dict: Notebook,
    nav: Document,
  }[type]
}

/**
 * 多字段模糊评分：对 query 在各字段上的 fuzzy + 拼音首字母匹配取最高分。
 * 返回 -1 表示无匹配；query 为空返回 0（表示全部命中，用于无搜索词场景）。
 */
function scoreMatch(query: string, ...fields: string[]): number {
  if (!query) return 0
  let best = -1
  for (const field of fields) {
    if (!field) continue
    // 直接 fuzzy 匹配（中英文均适用）
    const direct = fuzzyMatch(query, field)
    if (direct.matched && direct.score > best) best = direct.score
    // 拼音首字母匹配（仅对含中文的字段生效）
    if (/[\u4e00-\u9fff]/.test(field)) {
      const pinyin = toPinyinInitials(field)
      if (pinyin) {
        const pm = fuzzyMatch(query, pinyin)
        if (pm.matched && pm.score > best) best = pm.score
      }
    }
  }
  return best
}

const results = computed<CmdItem[]>(() => {
  const kw = keyword.value.trim().toLowerCase()
  const scored: { item: CmdItem; score: number }[] = []
  for (const c of cases.value) {
    const item: CmdItem = {
      key: 'case-' + c.id, type: 'case', title: c.name,
      sub: `用例 #${c.id}`, kindLabel: '用例',
      action: () => { router.push(`/cases/designer/${c.id}`); close() }
    }
    const score = scoreMatch(kw, item.title, item.sub)
    if (!kw || score >= 0) scored.push({ item, score })
  }
  for (const a of apis.value) {
    const item: CmdItem = {
      key: 'api-' + a.id, type: 'api', title: a.name,
      sub: `${a.method} ${a.code}`, kindLabel: '接口',
      action: () => { router.push(`/apis/edit/${a.id}`); close() }
    }
    const score = scoreMatch(kw, item.title, item.sub, a.code, a.path || '')
    if (!kw || score >= 0) scored.push({ item, score })
  }
  for (const p of projects.value) {
    const item: CmdItem = {
      key: 'proj-' + p.id, type: 'project', title: p.name,
      sub: `项目 #${p.id}`, kindLabel: '项目',
      action: () => { store.setProject(p.id); router.push('/apis'); close() }
    }
    const score = scoreMatch(kw, item.title, item.sub)
    if (!kw || score >= 0) scored.push({ item, score })
  }
  // 项目内资源：数据集 / 环境 / 文件 / 字典（命中即跳对应管理页）
  for (const d of datasets.value) {
    const item: CmdItem = {
      key: 'ds-' + d.id, type: 'dataset', title: d.name,
      sub: `数据集 #${d.id}`, kindLabel: '数据集',
      action: () => { router.push('/datasets'); close() }
    }
    const score = scoreMatch(kw, item.title, item.sub)
    if (!kw || score >= 0) scored.push({ item, score })
  }
  for (const v of envs.value) {
    const item: CmdItem = {
      key: 'env-' + v.id, type: 'env', title: v.name,
      sub: `环境 #${v.id}`, kindLabel: '环境',
      action: () => { router.push('/envs'); close() }
    }
    const score = scoreMatch(kw, item.title, item.sub)
    if (!kw || score >= 0) scored.push({ item, score })
  }
  for (const f of files.value) {
    const item: CmdItem = {
      key: 'file-' + f.id, type: 'file', title: f.name,
      sub: '文件', kindLabel: '文件',
      action: () => { router.push('/files'); close() }
    }
    const score = scoreMatch(kw, item.title, item.sub)
    if (!kw || score >= 0) scored.push({ item, score })
  }
  for (const d of dicts.value) {
    const item: CmdItem = {
      key: 'dict-' + d.id, type: 'dict', title: `${d.key}（${d.label}）`,
      sub: '字段字典', kindLabel: '字典',
      action: () => { router.push('/dictionary'); close() }
    }
    const score = scoreMatch(kw, item.title, d.key, d.label)
    if (!kw || score >= 0) scored.push({ item, score })
  }
  // 导航快捷项（首页置顶；顺序与侧边栏一致：工作流在前、准备项与管理沉底）
  const navs: { title: string; path: string }[] = [
    { title: '首页', path: '/home' },
    { title: '项目管理', path: '/projects' },
    { title: '接口管理', path: '/apis' },
    { title: '用例管理', path: '/cases' },
    { title: '数据集', path: '/datasets' },
    { title: '执行记录', path: '/executions' },
    { title: '环境配置', path: '/envs' },
    { title: '字段字典', path: '/dictionary' },
    { title: '文件中心', path: '/files' },
  ]
  if (store.user?.role === 'admin') {
    navs.push({ title: '用户管理', path: '/users' })
    navs.push({ title: '操作日志', path: '/operation-logs' })
  }
  for (const n of navs) {
    const item: CmdItem = {
      key: 'nav-' + n.path, type: 'nav', title: '前往 ' + n.title,
      sub: '页面导航', kindLabel: '导航',
      action: () => { router.push(n.path); close() }
    }
    const score = scoreMatch(kw, item.title, item.sub)
    if (!kw || score >= 0) scored.push({ item, score })
  }
  // 有搜索词时按分数降序，无搜索词时保持原始顺序
  if (kw) scored.sort((a, b) => b.score - a.score)
  return scored.slice(0, 30).map(s => s.item)
})

watch(results, () => { activeIdx.value = 0 })

function moveDown() { activeIdx.value = (activeIdx.value + 1) % (results.value.length || 1) }
function moveUp() { activeIdx.value = (activeIdx.value - 1 + (results.value.length || 1)) % (results.value.length || 1) }
function onEnter() {
  const item = results.value[activeIdx.value]
  if (item) onSelect(item)
}
function onSelect(item: CmdItem) { item.action() }
function close() { visible.value = false }

function onOpened() {
  setTimeout(() => inputRef.value?.focus(), 30)
}

async function loadAll() {
  if (!store.currentProjectId) return
  try {
    // 四类新数据源独立兜底：任一失败不影响其余搜索范围
    const [cs, as, dss, vs, fs, ds2] = await Promise.all([
      caseApi.list(store.currentProjectId),
      apiApi.list(store.currentProjectId),
      datasetApi.list({ project_id: store.currentProjectId }).catch(() => []),
      envApi.list(store.currentProjectId).catch(() => []),
      fileApi.list(store.currentProjectId).catch(() => []),
      dictApi.list(store.currentProjectId).catch(() => []),
    ])
    cases.value = cs
    apis.value = as
    datasets.value = dss
    envs.value = vs
    files.value = fs
    dicts.value = ds2
  } catch { /* ignore */ }
}

async function ensureProjects() {
  if (!projects.value.length) {
    try { projects.value = await projectApi.list() } catch { /* ignore */ }
  }
}

function open() {
  ensureProjects()
  loadAll()
  keyword.value = ''
  visible.value = true
}

function onGlobalKey(e: KeyboardEvent) {
  // Ctrl+K / Cmd+K 切换：已打开时再按为关闭，避免重复 open 重置关键词的「叠感」
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
    e.preventDefault()
    if (visible.value) close()
    else open()
    return
  }
  // Esc 关闭（el-dialog 默认支持，这里只处理输入框焦点态）
  if (e.key === 'Escape' && visible.value) {
    visible.value = false
  }
}

onMounted(() => window.addEventListener('keydown', onGlobalKey))
onUnmounted(() => window.removeEventListener('keydown', onGlobalKey))

defineExpose({ open, close })
</script>

<style scoped>
.cmd-input-wrap {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 4px 8px 12px;
  border-bottom: 1px solid var(--app-border);
}
/* 键盘焦点可见性：输入框本身无描边（视觉整合），焦点环由外层容器承载 */
.cmd-input-wrap:focus-within {
  box-shadow: inset 0 -2px 0 var(--app-primary);
}
.cmd-icon {
  font-size: 18px;
  color: var(--app-text-muted);
}
.cmd-input {
  flex: 1;
  border: none;
  outline: none;
  background: transparent;
  font-size: 15px;
  color: var(--app-text);
}
.cmd-kbd {
  flex-shrink: 0;
}
.cmd-list {
  max-height: 360px;
  overflow-y: auto;
  padding: 6px 0;
}
.cmd-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  cursor: pointer;
  border-radius: var(--app-radius-sm);
}
.cmd-item.active {
  background: var(--app-active);
}
.cmd-item-icon {
  font-size: 16px;
  color: var(--app-primary);
  flex-shrink: 0;
}
.cmd-item-main {
  flex: 1;
  min-width: 0;
}
.cmd-item-title {
  font-size: 14px;
  color: var(--app-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.cmd-item-sub {
  font-size: 12px;
  color: var(--app-text-muted);
  margin-top: 2px;
}
.cmd-footer {
  display: flex;
  gap: 16px;
  padding: 8px 12px;
  border-top: 1px solid var(--app-border);
  font-size: 12px;
  color: var(--app-text-muted);
}
</style>

<style>
.cmd-palette .el-dialog__header {
  display: none;
}
.cmd-palette .el-dialog__body {
  padding: 12px 16px 0;
}
</style>

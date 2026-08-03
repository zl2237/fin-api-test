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
        placeholder="搜索用例 / 接口 / 项目，或输入命令"
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
          <div class="cmd-item-title">{{ item.title }}</div>
          <div class="cmd-item-sub">{{ item.sub }}</div>
        </div>
        <el-tag size="small" type="info" effect="plain" round>{{ item.kindLabel }}</el-tag>
      </div>
      <el-empty v-if="!results.length" description="无匹配项" :image-size="40" />
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
import { Search, Share, Connection, Folder, Document } from '@element-plus/icons-vue'
import { caseApi, apiApi, projectApi, type TestCase, type ApiDef, type Project } from '@/api'
import { useAppStore } from '@/stores'

const router = useRouter()
const store = useAppStore()

const visible = ref(false)
const keyword = ref('')
const inputRef = shallowRef<HTMLInputElement | null>(null)
const activeIdx = ref(0)

const cases = ref<TestCase[]>([])
const apis = ref<ApiDef[]>([])
const projects = ref<Project[]>([])

type ItemType = 'case' | 'api' | 'project' | 'nav'
interface CmdItem {
  key: string
  type: ItemType
  title: string
  sub: string
  kindLabel: string
  action: () => void
}

function iconComp(type: ItemType) {
  return { case: Share, api: Connection, project: Folder, nav: Document }[type]
}

const results = computed<CmdItem[]>(() => {
  const kw = keyword.value.trim().toLowerCase()
  const list: CmdItem[] = []
  const match = (s: string) => !kw || s.toLowerCase().includes(kw)
  for (const c of cases.value) {
    if (match(c.name)) list.push({
      key: 'case-' + c.id, type: 'case', title: c.name,
      sub: `用例 #${c.id}`, kindLabel: '用例',
      action: () => { router.push(`/cases/designer/${c.id}`); close() }
    })
  }
  for (const a of apis.value) {
    if (match(a.name) || match(a.code) || match(a.path || '')) list.push({
      key: 'api-' + a.id, type: 'api', title: a.name,
      sub: `${a.method} ${a.code}`, kindLabel: '接口',
      action: () => { router.push(`/apis/edit/${a.id}`); close() }
    })
  }
  for (const p of projects.value) {
    if (match(p.name)) list.push({
      key: 'proj-' + p.id, type: 'project', title: p.name,
      sub: `项目 #${p.id}`, kindLabel: '项目',
      action: () => { store.setProject(p.id); router.push('/apis'); close() }
    })
  }
  // 导航快捷项
  const navs: { title: string; path: string }[] = [
    { title: '项目管理', path: '/projects' },
    { title: '接口管理', path: '/apis' },
    { title: '用例列表', path: '/cases' },
    { title: '环境配置', path: '/envs' },
    { title: '执行记录', path: '/executions' },
  ]
  if (store.user?.role === 'admin') {
    navs.push({ title: '用户管理', path: '/users' })
    navs.push({ title: '操作日志', path: '/operation-logs' })
  }
  for (const n of navs) {
    if (match(n.title)) list.push({
      key: 'nav-' + n.path, type: 'nav', title: '前往 ' + n.title,
      sub: '页面导航', kindLabel: '导航',
      action: () => { router.push(n.path); close() }
    })
  }
  return list.slice(0, 30)
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
    const [cs, as] = await Promise.all([
      caseApi.list(store.currentProjectId),
      apiApi.list(store.currentProjectId),
    ])
    cases.value = cs
    apis.value = as
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
  // Ctrl+K / Cmd+K 打开
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
    e.preventDefault()
    open()
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
  color: var(--el-color-primary);
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

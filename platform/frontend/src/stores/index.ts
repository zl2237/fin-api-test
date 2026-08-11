import { defineStore } from 'pinia'
import { ref, watch } from 'vue'
import { projectApi, envApi, authApi, dictApi, getToken, setToken, clearToken, type Project, type Environment, type User } from '@/api'

export const useAppStore = defineStore('app', () => {
  const projects = ref<Project[]>([])
  const currentProjectId = ref<number | null>(null)
  const environments = ref<Environment[]>([])
  const currentEnvId = ref<number | null>(null)
  const user = ref<User | null>(null)
  // 字段字典：当前项目的 {英文字段名: 中文含义} 映射
  const fieldDictMap = ref<Record<string, string>>({})

  // 核心能力详情弹窗（表达式引擎 / 17 种断言）：跨组件共享，节点配置弹窗等可触发
  const coreCapVisible = ref(false)
  const coreCapTab = ref<'expression' | 'assertion'>('expression')
  function openCoreCapability(tab: 'expression' | 'assertion') {
    coreCapTab.value = tab
    coreCapVisible.value = true
  }
  function setCoreCapVisible(visible: boolean) {
    coreCapVisible.value = visible
  }

  // 主题：light / dark / auto，auto 跟随系统
  const THEME_KEY = 'fin_theme'
  const theme = ref<'light' | 'dark' | 'auto'>('auto')

  function applyTheme(t: 'light' | 'dark' | 'auto') {
    theme.value = t
    localStorage.setItem(THEME_KEY, t)
    const sysDark = window.matchMedia('(prefers-color-scheme: dark)').matches
    const isDark = t === 'dark' || (t === 'auto' && sysDark)
    document.documentElement.classList.toggle('dark', isDark)
  }

  function initTheme() {
    const saved = (localStorage.getItem(THEME_KEY) as 'light' | 'dark' | 'auto' | null) ?? 'auto'
    applyTheme(saved)
    // 系统主题变化时，若处于 auto 则跟随
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
      if (theme.value === 'auto') applyTheme('auto')
    })
  }

  function toggleTheme() {
    const next = theme.value === 'light' ? 'dark' : 'light'
    applyTheme(next)
  }

  // 当前项目记忆：localStorage 持久化，刷新后恢复
  const PROJECT_KEY = 'fin_current_project_id'
  const ENV_KEY = 'fin_current_env_id'

  function isLoggedIn(): boolean {
    return !!getToken()
  }

  async function loadUser() {
    if (!getToken()) {
      user.value = null
      return
    }
    try {
      user.value = await authApi.me()
    } catch {
      user.value = null
      clearToken()
    }
  }

  async function login(username: string, password: string) {
    const res = await authApi.login(username, password)
    setToken(res.token)
    user.value = res.user
    return res.user
  }

  function logout() {
    clearToken()
    user.value = null
    projects.value = []
    environments.value = []
    currentProjectId.value = null
    currentEnvId.value = null
    // 退出登录不清理 localStorage 项目记忆，下次登录仍可恢复
  }

  async function loadProjects() {
    projects.value = await projectApi.list()
    // 恢复记忆的项目：优先 localStorage，其次取第一个
    if (!currentProjectId.value) {
      const saved = Number(localStorage.getItem(PROJECT_KEY))
      const exists = saved && projects.value.some((p) => p.id === saved)
      currentProjectId.value = exists ? saved : (projects.value[0]?.id ?? null)
    }
  }

  async function loadEnvironments() {
    if (!currentProjectId.value) {
      environments.value = []
      return
    }
    environments.value = await envApi.list(currentProjectId.value)
    // 恢复记忆的环境：优先 localStorage，其次默认环境，最后第一个
    if (!currentEnvId.value) {
      const saved = Number(localStorage.getItem(ENV_KEY))
      const exists = saved && environments.value.some((e) => e.id === saved)
      if (exists) {
        currentEnvId.value = saved
      } else {
        const def = environments.value.find((e) => e.is_default)
        currentEnvId.value = def?.id ?? environments.value[0]?.id ?? null
      }
    }
  }

  // 加载当前项目的字段字典映射（供配置界面自动展示中文标签）
  async function loadFieldDict() {
    // 立即清空旧数据，避免切换项目期间残留上一个项目的字典
    if (!currentProjectId.value) {
      fieldDictMap.value = {}
      return
    }
    const targetId = currentProjectId.value
    fieldDictMap.value = {}
    try {
      const map = await dictApi.getMap(targetId)
      // 异步期间项目可能又切换了，仅当目标项目仍是当前项目时才写入
      if (currentProjectId.value === targetId) {
        fieldDictMap.value = map
      }
    } catch {
      fieldDictMap.value = {}
    }
  }

  function setProject(id: number) {
    currentProjectId.value = id
    localStorage.setItem(PROJECT_KEY, String(id))
    currentEnvId.value = null
    localStorage.removeItem(ENV_KEY)
    loadEnvironments()
    loadFieldDict()
  }

  // 环境切换时自动记忆（顶部选择器 v-model 改变 currentEnvId 即触发）
  watch(currentEnvId, (v) => {
    if (v !== null) localStorage.setItem(ENV_KEY, String(v))
  })

  return {
    projects,
    currentProjectId,
    environments,
    currentEnvId,
    user,
    fieldDictMap,
    coreCapVisible,
    coreCapTab,
    theme,
    isLoggedIn,
    loadUser,
    login,
    logout,
    loadProjects,
    loadEnvironments,
    loadFieldDict,
    setProject,
    initTheme,
    applyTheme,
    toggleTheme,
    openCoreCapability,
    setCoreCapVisible,
  }
})

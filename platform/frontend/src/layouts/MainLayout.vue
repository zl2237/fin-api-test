<template>
  <el-container class="layout">
    <el-aside class="sidebar" :width="collapsed ? '64px' : '220px'">
      <div class="brand">
        <span class="brand-dot"></span>
        <span v-if="!collapsed" class="brand-text">fin-api-test</span>
      </div>
      <el-menu
        :default-active="route.path"
        router
        class="nav-menu"
        :collapse="collapsed"
      >
        <el-menu-item index="/projects">
          <el-icon><Folder /></el-icon>
          <span>项目管理</span>
        </el-menu-item>
        <el-menu-item index="/apis">
          <el-icon><Connection /></el-icon>
          <span>接口管理</span>
        </el-menu-item>
        <el-menu-item index="/cases">
          <el-icon><Share /></el-icon>
          <span>用例列表</span>
        </el-menu-item>
        <el-menu-item index="/envs">
          <el-icon><Setting /></el-icon>
          <span>环境配置</span>
        </el-menu-item>
        <el-menu-item index="/executions">
          <el-icon><Histogram /></el-icon>
          <span>执行记录</span>
        </el-menu-item>
        <el-menu-item v-if="store.user?.role === 'admin'" index="/users">
          <el-icon><UserFilled /></el-icon>
          <span>用户管理</span>
        </el-menu-item>
        <el-menu-item v-if="store.user?.role === 'admin'" index="/operation-logs">
          <el-icon><List /></el-icon>
          <span>操作日志</span>
        </el-menu-item>
      </el-menu>
    </el-aside>

    <el-container>
      <el-header class="topbar">
        <div class="topbar-left">
          <el-button text class="collapse-btn" @click="toggleSidebar">
            <el-icon><Fold v-if="!collapsed" /><Expand v-else /></el-icon>
          </el-button>
          <el-breadcrumb :separator-icon="ArrowRight" class="topbar-breadcrumb">
            <el-breadcrumb-item :to="{ path: '/' }">
              <el-icon><HomeFilled /></el-icon>
            </el-breadcrumb-item>
            <el-breadcrumb-item v-for="item in breadcrumbItems" :key="item.path" :to="item.path">
              {{ item.title }}
            </el-breadcrumb-item>
          </el-breadcrumb>
          <el-button text class="cmd-trigger" @click="cmdPaletteRef?.open()">
            <el-icon><Search /></el-icon>
            <span class="cmd-trigger-text">搜索</span>
            <el-tag size="small" effect="plain" round class="cmd-trigger-kbd">Ctrl K</el-tag>
          </el-button>
        </div>
        <div class="topbar-selectors">
          <el-select
            v-model="store.currentProjectId"
            :placeholder="store.projects.length ? '选择项目' : '暂无项目'"
            size="default"
            style="width: 180px"
            @change="onProjectChange"
          >
            <el-option
              v-for="p in store.projects"
              :key="p.id"
              :label="p.name"
              :value="p.id"
            />
          </el-select>
          <el-button v-if="!store.projects.length" link type="primary" @click="router.push('/projects')">
            + 去创建
          </el-button>
          <el-select
            v-model="store.currentEnvId"
            placeholder="选择环境"
            size="default"
            style="width: 160px"
          >
            <el-option
              v-for="e in store.environments"
              :key="e.id"
              :label="e.name"
              :value="e.id"
            />
          </el-select>
          <el-button text @click="helpVisible = true">
            <el-icon><QuestionFilled /></el-icon>使用说明
          </el-button>
          <el-dropdown trigger="click" @command="onThemeCommand">
            <el-button text :title="themeLabel">
              <el-icon><Sunny v-if="effectiveDark" /><Moon v-else /></el-icon>
            </el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="light" :class="{ 'is-active': store.theme === 'light' }">
                  <el-icon><Sunny /></el-icon>浅色
                </el-dropdown-item>
                <el-dropdown-item command="dark" :class="{ 'is-active': store.theme === 'dark' }">
                  <el-icon><Moon /></el-icon>深色
                </el-dropdown-item>
                <el-dropdown-item command="auto" :class="{ 'is-active': store.theme === 'auto' }">
                  <el-icon><Monitor /></el-icon>跟随系统
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
          <el-dropdown trigger="click" @command="onUserCommand">
            <span class="user-chip">
              <el-icon><UserFilled /></el-icon>
              <span class="user-name">{{ store.user?.name || store.user?.username || '用户' }}</span>
              <el-tag v-if="store.user?.role === 'admin'" size="small" type="warning" effect="plain" round>管理员</el-tag>
            </span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="logout">
                  <el-icon><SwitchButton /></el-icon>退出登录
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </el-header>
      <el-main class="main">
        <router-view />
      </el-main>
    </el-container>
  </el-container>

  <!-- 使用说明弹窗 -->
  <el-dialog v-model="helpVisible" title="平台使用说明" width="640px">
    <el-steps direction="vertical" :active="5">
      <el-step title="创建项目" description="在「项目管理」新建项目。新用户注册后首个项目是操作起点，顶部选择器切换当前项目。" />
      <el-step title="配置环境" description="在「环境配置」新建环境，填写 base_url、数据库、登录配置（用于自动获取 token 注入后续请求）。可点「测试连接」「测试登录」验证。" />
      <el-step title="管理接口" description="在「接口管理」新建接口或导入 Swagger/OpenAPI 规范。可点「调试」单独测试单个接口。" />
      <el-step title="编排用例" description="在「用例列表」新建用例进入编排画布：左侧点接口添加节点，连线建立执行顺序，点节点配置预处理/提取/断言。工具栏「自动布局」可一键整理节点。" />
      <el-step title="执行与报告" description="工具栏选环境后点「执行」，查看报告：步骤详情、断言结果、耗时趋势，支持导出 CSV/PDF 和「重新执行」。" />
    </el-steps>
    <template #footer>
      <el-button type="primary" @click="helpVisible = false">我知道了</el-button>
    </template>
  </el-dialog>

  <!-- 全局命令面板（Ctrl+K） -->
  <CommandPalette ref="cmdPaletteRef" />
</template>

<script setup lang="ts">
import { onMounted, ref, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessageBox, ElMessage } from 'element-plus'
import { Connection, Share, Setting, Histogram, UserFilled, SwitchButton, List, Folder, QuestionFilled, Expand, Fold, Sunny, Moon, Monitor, Search, HomeFilled, ArrowRight } from '@element-plus/icons-vue'
import { useAppStore } from '@/stores'
import CommandPalette from '@/components/CommandPalette.vue'

const route = useRoute()
const router = useRouter()
const store = useAppStore()
const helpVisible = ref(false)
const cmdPaletteRef = ref<InstanceType<typeof CommandPalette> | null>(null)
// 侧边栏折叠状态：localStorage 记忆，默认展开
const SIDEBAR_KEY = 'fin_sidebar_collapsed'
const collapsed = ref(localStorage.getItem(SIDEBAR_KEY) === '1')
function toggleSidebar() {
  collapsed.value = !collapsed.value
  localStorage.setItem(SIDEBAR_KEY, collapsed.value ? '1' : '0')
}

// 主题：当前生效是否深色，用于图标显示
const effectiveDark = computed(() =>
  store.theme === 'dark' ||
  (store.theme === 'auto' && window.matchMedia('(prefers-color-scheme: dark)').matches)
)
const themeLabel = computed(() => {
  if (store.theme === 'light') return '浅色模式'
  if (store.theme === 'dark') return '深色模式'
  return '跟随系统'
})
function onThemeCommand(cmd: 'light' | 'dark' | 'auto') {
  store.applyTheme(cmd)
  ElMessage.success(`已切换为${cmd === 'light' ? '浅色' : cmd === 'dark' ? '深色' : '跟随系统'}模式`)
}

function onProjectChange(id: number) {
  store.setProject(id)
}

// 面包屑：取路由 matched 链中带 title 的项（排除根布局）
const breadcrumbItems = computed(() => {
  return route.matched
    .filter((r) => r.meta.title && !r.redirect)
    .map((r) => ({ path: r.path, title: r.meta.title as string }))
})

async function onUserCommand(cmd: string) {
  if (cmd === 'logout') {
    await ElMessageBox.confirm('确定退出登录吗？', '提示', { type: 'warning' })
    store.logout()
    ElMessage.success('已退出登录')
    router.replace('/login')
  }
}

onMounted(async () => {
  // 主题已在 App.vue 初始化，这里无需重复
  await store.loadUser()
  if (!store.user) return
  await store.loadProjects()
  if (store.currentProjectId) {
    await store.loadEnvironments()
  } else if (route.path !== '/projects') {
    // 无项目时自动引导到项目管理页，避免后续页面因 currentProjectId 为空而卡死
    router.replace('/projects')
  }
})
</script>

<style scoped>
.layout {
  height: 100%;
}
.sidebar {
  background: var(--app-sidebar);
  backdrop-filter: saturate(180%) blur(20px);
  border-right: 1px solid var(--app-border);
  padding: 16px 12px;
  transition: width 0.25s ease;
  overflow: hidden;
}
.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px 18px;
  font-weight: 600;
  font-size: 16px;
  white-space: nowrap;
}
.brand-dot {
  width: 10px;
  height: 10px;
  flex-shrink: 0;
  border-radius: 50%;
  background: linear-gradient(135deg, var(--app-primary), #42a1ff);
}
.nav-menu {
  border-right: none;
  background: transparent;
}
:deep(.nav-menu .el-menu-item) {
  border-radius: var(--app-radius-sm);
  margin-bottom: 4px;
}
:deep(.nav-menu .el-menu-item.is-active) {
  background: var(--app-active);
  color: var(--el-color-primary);
}
/* 折叠态：菜单项居中，tooltip 由 el-menu 原生提供 */
:deep(.nav-menu.el-menu--collapse) {
  width: 40px;
}
:deep(.nav-menu.el-menu--collapse .el-menu-item) {
  display: flex;
  justify-content: center;
  padding: 0 !important;
}
.topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: var(--app-card);
  backdrop-filter: saturate(180%) blur(20px);
  border-bottom: 1px solid var(--app-border);
}
.topbar-left {
  display: flex;
  align-items: center;
  gap: 8px;
}
.collapse-btn {
  padding: 6px 8px;
  font-size: 18px;
  color: var(--app-text);
}
.topbar-breadcrumb {
  font-size: 15px;
  font-weight: 500;
  line-height: 1;
}
:deep(.topbar-breadcrumb .el-breadcrumb__inner) {
  color: var(--app-text-muted);
  font-weight: 500;
}
:deep(.topbar-breadcrumb .el-breadcrumb__item:last-child .el-breadcrumb__inner) {
  color: var(--app-text);
  font-weight: 600;
}
.cmd-trigger {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px !important;
  background: var(--app-chip-bg);
  border-radius: 16px;
}
.cmd-trigger-text {
  font-size: 13px;
  color: var(--app-text-muted);
}
.cmd-trigger-kbd {
  font-size: 11px;
}
.topbar-selectors {
  display: flex;
  gap: 12px;
  align-items: center;
}
.user-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: 16px;
  background: var(--app-chip-bg);
  cursor: pointer;
  font-size: 13px;
  outline: none;
}
.user-chip .user-name {
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.main {
  padding: 20px;
  overflow: auto;
}
</style>

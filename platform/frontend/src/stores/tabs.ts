/**
 * 标签页状态管理
 * 管理已打开的页面标签，配合 keep-alive 实现页面状态保留
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { RouteLocationNormalized } from 'vue-router'

export interface TabItem {
  /** 路由完整路径，作为唯一标识 */
  path: string
  /** 标签标题（取自 route.meta.title） */
  title: string
  /** 路由 name */
  name: string
  /** 是否可关闭（首页/默认页不可关闭） */
  closable: boolean
}

export const useTabStore = defineStore('tabs', () => {
  const tabs = ref<TabItem[]>([])
  const activePath = ref('')

  const activeIndex = computed(() =>
    tabs.value.findIndex((t) => t.path === activePath.value)
  )

  /**
   * 从路由对象创建标签项
   * 根路径和重定向不创建标签
   */
  function tabFromRoute(route: RouteLocationNormalized): TabItem | null {
    const path = route.path
    // 根路径、重定向不创建标签
    if (!path || path === '/' || path === '/login' || path === '/change-password') {
      return null
    }
    const title = (route.meta?.title as string) || route.name?.toString() || path
    // 首页（接口管理）不可关闭，保留至少一个标签
    const closable = path !== '/apis'
    return { path, title, name: route.name?.toString() || '', closable }
  }

  /**
   * 添加标签（去重），并设为激活
   */
  function addTab(route: RouteLocationNormalized) {
    const item = tabFromRoute(route)
    if (!item) return
    // 去重：同 path 不重复添加
    const exists = tabs.value.find((t) => t.path === item.path)
    if (!exists) {
      tabs.value.push(item)
    }
    activePath.value = item.path
  }

  /**
   * 关闭指定标签，返回应该激活的相邻标签路径
   */
  function removeTab(path: string): string | null {
    const idx = tabs.value.findIndex((t) => t.path === path)
    if (idx === -1) return null
    // 不可关闭的标签（如首页）
    if (!tabs.value[idx].closable) return null
    tabs.value.splice(idx, 1)
    // 如果关闭的是当前激活标签，需要导航到相邻标签
    if (activePath.value === path) {
      // 优先激活右侧，没有则左侧，都没有则首页
      const next = tabs.value[idx] || tabs.value[idx - 1] || tabs.value[0]
      activePath.value = next?.path || '/apis'
      return activePath.value
    }
    return null
  }

  /**
   * 关闭其他标签（保留指定标签和不可关闭的标签）
   */
  function removeOthers(path: string) {
    tabs.value = tabs.value.filter((t) => t.path === path || !t.closable)
    activePath.value = path
  }

  /**
   * 关闭所有可关闭的标签，激活首页
   */
  function removeAll() {
    tabs.value = tabs.value.filter((t) => !t.closable)
    activePath.value = tabs.value[0]?.path || '/apis'
    return activePath.value
  }

  /**
   * 重置（退出登录时调用）
   */
  function reset() {
    tabs.value = []
    activePath.value = ''
  }

  return {
    tabs,
    activePath,
    activeIndex,
    addTab,
    removeTab,
    removeOthers,
    removeAll,
    reset,
  }
})

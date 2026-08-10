/**
 * 顶部请求进度条状态管理
 *
 * 设计：
 * - 并发请求计数：多个请求同时进行时，只有全部完成才结束进度条
 * - 进度模拟：启动后快速到 80%，剩余 20% 缓慢前进，避免长时间静止
 * - 完成时瞬间到 100% 后淡出
 *
 * 不引入 NProgress 依赖，自实现轻量版。
 */

import { reactive } from 'vue'

interface ProgressState {
  /** 当前进度 0-100 */
  percent: number
  /** 是否可见 */
  visible: boolean
}

export const progressState = reactive<ProgressState>({
  percent: 0,
  visible: false,
})

let activeCount = 0
let trickleTimer: ReturnType<typeof setInterval> | null = null
let hideTimer: ReturnType<typeof setTimeout> | null = null

function clearTimers() {
  if (trickleTimer) {
    clearInterval(trickleTimer)
    trickleTimer = null
  }
  if (hideTimer) {
    clearTimeout(hideTimer)
    hideTimer = null
  }
}

/** 启动进度条：快速到 80%，剩余缓慢前进 */
export function startProgress() {
  activeCount++
  if (activeCount > 1) return // 已有请求在进行，无需重复启动
  clearTimers()
  progressState.visible = true
  progressState.percent = 0
  // 快速起步
  progressState.percent = 30
  // 缓慢前进到 80%
  trickleTimer = setInterval(() => {
    if (progressState.percent < 80) {
      // 越接近 80 增速越慢
      const remain = 80 - progressState.percent
      progressState.percent += Math.max(0.5, remain * 0.1)
      if (progressState.percent > 80) progressState.percent = 80
    } else if (progressState.percent < 95) {
      // 极慢前进到 95%，给长时间请求留余地
      progressState.percent += 0.2
    }
  }, 200)
}

/** 完成进度条：瞬间到 100% 后淡出 */
export function doneProgress() {
  activeCount = Math.max(0, activeCount - 1)
  if (activeCount > 0) return // 还有并发请求未完成
  clearTimers()
  progressState.percent = 100
  // 100% 后短暂停留再隐藏，让用户看到完成态
  hideTimer = setTimeout(() => {
    progressState.visible = false
    // 隐藏后重置，下次启动从 0 开始
    setTimeout(() => { progressState.percent = 0 }, 300)
  }, 200)
}

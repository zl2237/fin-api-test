/**
 * Favicon 执行状态指示
 *
 * 用例执行时动态切换浏览器标签页图标：
 * - running：蓝色旋转圆环
 * - success：绿色对勾（3 秒后自动恢复）
 * - failed：红色叉号（3 秒后自动恢复）
 *
 * 不支持 SMIL 动画的浏览器（Safari）会降级为静态首帧。
 */

type FaviconState = 'default' | 'running' | 'success' | 'failed'

const DEFAULT_HREF = '/favicon.svg'

// SVG 模板：返回 data URI（encodeURIComponent 保证 #、<、> 等字符正确）
function buildSvg(state: FaviconState): string {
  if (state === 'default') return DEFAULT_HREF
  const svgs: Record<Exclude<FaviconState, 'default'>, string> = {
    running: `
<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 32 32">
  <rect width="32" height="32" rx="8" fill="#1f2d3d"/>
  <circle cx="16" cy="16" r="11" fill="none" stroke="#409eff" stroke-width="2.6" stroke-dasharray="22 48" stroke-linecap="round">
    <animateTransform attributeName="transform" type="rotate" from="0 16 16" to="360 16 16" dur="0.9s" repeatCount="indefinite"/>
  </circle>
  <circle cx="16" cy="16" r="3" fill="#409eff"/>
</svg>`,
    success: `
<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 32 32">
  <rect width="32" height="32" rx="8" fill="#67c23a"/>
  <path d="M9 16.5 L14 21.5 L23 11" fill="none" stroke="#fff" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>
</svg>`,
    failed: `
<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 32 32">
  <rect width="32" height="32" rx="8" fill="#f56c6c"/>
  <path d="M11 11 L21 21 M21 11 L11 21" fill="none" stroke="#fff" stroke-width="3" stroke-linecap="round"/>
</svg>`,
  }
  return `data:image/svg+xml,${encodeURIComponent(svgs[state].trim())}`
}

let currentState: FaviconState = 'default'
let restoreTimer: ReturnType<typeof setTimeout> | null = null

function getLinkEl(): HTMLLinkElement | null {
  return document.querySelector('link[rel="icon"]') as HTMLLinkElement | null
}

function applyState(state: FaviconState) {
  currentState = state
  const link = getLinkEl()
  if (!link) return
  link.href = buildSvg(state)
  // 部分浏览器需要重新触发渲染
  if (state !== 'default') {
    link.type = 'image/svg+xml'
  }
}

function clearRestoreTimer() {
  if (restoreTimer) {
    clearTimeout(restoreTimer)
    restoreTimer = null
  }
}

/**
 * 设置 favicon 状态
 * - success / failed 会在 3 秒后自动恢复默认
 * - running 持续显示直到显式调用 setSuccess/setFailed/reset
 */
function setState(state: FaviconState) {
  clearRestoreTimer()
  applyState(state)
  if (state === 'success' || state === 'failed') {
    restoreTimer = setTimeout(() => applyState('default'), 3000)
  }
}

export function useFaviconStatus() {
  return {
    /** 标记为执行中（旋转图标） */
    running: () => setState('running'),
    /** 标记为执行成功（绿勾，3 秒后恢复） */
    success: () => setState('success'),
    /** 标记为执行失败（红叉，3 秒后恢复） */
    failed: () => setState('failed'),
    /** 立即恢复默认图标 */
    reset: () => setState('default'),
    /** 当前状态 */
    get state() {
      return currentState
    },
  }
}

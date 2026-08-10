/**
 * 全局按钮点击涟漪效果
 *
 * 零侵入方案：监听 document click 事件，点击 .el-button 时从点击点扩散水波纹。
 * - 使用 currentColor 自适应按钮文字颜色（深色背景→白色涟漪，浅色背景→深色涟漪）
 * - 排除 disabled 按钮
 * - 动画结束后自动移除 DOM 元素
 *
 * 尊重 prefers-reduced-motion：减少动态效果时不触发涟漪。
 */

export function setupRipple() {
  const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)')

  document.addEventListener('click', (e: MouseEvent) => {
    if (prefersReducedMotion.matches) return

    const target = e.target as HTMLElement
    if (!target || target.nodeType !== 1) return

    const button = target.closest('.el-button') as HTMLElement | null
    if (!button) return
    // 排除禁用按钮
    if (button.classList.contains('is-disabled')) return
    // 排除文本按钮（link/text 类型），涟漪在透明背景上不美观
    if (button.classList.contains('is-text') || button.classList.contains('is-link')) return

    const rect = button.getBoundingClientRect()
    // 涟漪直径取按钮对角线，确保覆盖整个按钮
    const size = Math.sqrt(rect.width * rect.width + rect.height * rect.height) * 2
    const x = e.clientX - rect.left - size / 2
    const y = e.clientY - rect.top - size / 2

    // 确保 button 有定位上下文
    const computed = getComputedStyle(button)
    if (computed.position === 'static') {
      button.style.position = 'relative'
    }
    if (computed.overflow !== 'hidden') {
      button.style.overflow = 'hidden'
    }

    const ripple = document.createElement('span')
    ripple.className = 'btn-ripple'
    ripple.style.width = ripple.style.height = `${size}px`
    ripple.style.left = `${x}px`
    ripple.style.top = `${y}px`

    button.appendChild(ripple)

    // 动画结束清理（兼容动画未触发的情况，加超时兜底）
    const cleanup = () => ripple.remove()
    ripple.addEventListener('animationend', cleanup, { once: true })
    setTimeout(cleanup, 800)
  })
}

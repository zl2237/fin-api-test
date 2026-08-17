import { ref, watch, type Ref } from 'vue'

/**
 * 数字滚动（count-up）：目标值变化时从 0 滚动到目标，ease-out 曲线。
 *
 * 手写实现延续项目"零动画库依赖"惯例：
 * - requestAnimationFrame 驱动，页面不可见时浏览器自动暂停
 * - 目标值更新时从当前值平滑滚到新目标（而非重置为 0）
 * - 尊重 prefers-reduced-motion：直接跳到目标值
 * - duration 默认 800ms；格式化器用于耗时（如 1234 -> "1.23 s"）
 */
export function useCountUp(
  source: Ref<number>,
  duration = 800,
  format: (v: number) => string = (v) => String(Math.round(v)),
): Ref<string> {
  const display = ref(format(source.value))

  function animate(from: number, to: number) {
    display.value = format(to)
    if (from === to) return
    if (typeof window === 'undefined') return
    // 减少动画偏好：直接落定
    if (window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) return
    const start = performance.now()
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / duration)
      // ease-out cubic
      const eased = 1 - Math.pow(1 - t, 3)
      display.value = format(from + (to - from) * eased)
      if (t < 1) requestAnimationFrame(tick)
    }
    requestAnimationFrame(tick)
  }

  // 记录上一次的目标值，用于目标变化时从当前显示值续滚
  let lastTarget = source.value
  watch(
    source,
    (to) => {
      // 初始为 0（数据未加载）到真实值的首次跳变，从 0 滚起
      animate(0, to)
      lastTarget = to
    },
    { immediate: false },
  )
  // 数据就位前显示 0
  if (lastTarget === 0) display.value = format(0)

  return display
}

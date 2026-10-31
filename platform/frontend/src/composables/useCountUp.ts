/**
 * 数字滚动（提示词 7）：数值变化时从旧值滚动到新值，而非瞬间跳变。
 *
 * - rAF + easeOutCubic：先快后慢，符合计数动画的阅读节奏
 * - 源值为 null（如通过率无数据）时不滚动，展示落定占位由调用方处理
 * - prefers-reduced-motion：直接落定目标值
 * - 组件卸载自动取消进行中的动画
 */
import { ref, watch, onUnmounted, type Ref } from 'vue'

const easeOutCubic = (t: number) => 1 - Math.pow(1 - t, 3)

export function useCountUp(
  source: Readonly<Ref<number | null>>,
  options: { duration?: number } = {},
) {
  const { duration = 800 } = options
  // 数值源初始从 0 起滚（而非直接展示目标值，否则首屏无滚动效果）；null 源保持 null
  const display = ref<number | null>(typeof source.value === 'number' ? 0 : null)

  let rafId = 0
  let from = 0

  function stop() {
    if (rafId) {
      cancelAnimationFrame(rafId)
      rafId = 0
    }
  }

  function run(target: number) {
    stop()
    const reduce =
      typeof window !== 'undefined' &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches
    if (reduce || duration <= 0) {
      display.value = target
      return
    }
    const start = performance.now()
    const step = (now: number) => {
      const progress = Math.min((now - start) / duration, 1)
      display.value = Math.round(from + (target - from) * easeOutCubic(progress))
      if (progress < 1) {
        rafId = requestAnimationFrame(step)
      } else {
        rafId = 0
      }
    }
    rafId = requestAnimationFrame(step)
  }

  watch(
    source,
    (val) => {
      if (val === null) {
        stop()
        display.value = null
        return
      }
      // 首次（display 为 null）从 0 滚入；后续从当前展示值续滚
      from = typeof display.value === 'number' ? display.value : 0
      run(val)
    },
    { immediate: true },
  )

  onUnmounted(stop)

  return { display }
}

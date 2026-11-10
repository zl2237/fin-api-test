import { ref, onUnmounted, getCurrentInstance } from 'vue'

/** 短暂标志位：trigger() 置 true，ms 后自动回落；窗口期内重复触发重置计时。
 *  用于「就地反馈」类动效（如保存按钮对勾 1.5s），替代一次性的全局 toast。
 *  组件卸载时清计时器；非组件上下文（纯逻辑调用）安全降级不注册钩子。 */
export function useTransientFlag(ms = 1500) {
  const active = ref(false)
  let timer: ReturnType<typeof setTimeout> | null = null

  function trigger() {
    active.value = true
    if (timer) clearTimeout(timer)
    timer = setTimeout(() => {
      active.value = false
      timer = null
    }, ms)
  }

  if (getCurrentInstance()) {
    onUnmounted(() => {
      if (timer) clearTimeout(timer)
    })
  }

  return { active, trigger }
}

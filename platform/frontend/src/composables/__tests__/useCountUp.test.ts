import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { createApp, ref, nextTick } from 'vue'
import { useCountUp } from '../useCountUp'

/** 在真实组件 setup 中执行 composable（onUnmounted 需组件实例），返回 {结果, 卸载} */
function withSetup<T>(composable: () => T): { result: T; unmount: () => void } {
  let result!: T
  const app = createApp({ setup() { result = composable(); return () => {} } })
  app.mount(document.createElement('div'))
  return { result, unmount: () => app.unmount() }
}

// jsdom 无 matchMedia：手动桩，测试内可切换 reduce 开关
let reduceMotion = false
vi.stubGlobal('matchMedia', vi.fn().mockImplementation((query: string) => ({
  matches: query.includes('prefers-reduced-motion') ? reduceMotion : false,
  addEventListener: () => {},
  removeEventListener: () => {},
})))

// rAF 手动驱动：收集回调，flush(t) 以给定时间戳逐帧执行，动画进度完全可控
let frames: ((now: number) => void)[] = []
let now = 0
vi.stubGlobal('requestAnimationFrame', vi.fn((cb: (t: number) => void) => {
  frames.push(cb)
  return frames.length
}))
vi.stubGlobal('cancelAnimationFrame', vi.fn(() => {
  frames = []
}))
vi.stubGlobal('performance', { now: () => now })

/** 推进时间到动画结束（默认时长 800ms） */
function flushAnimation() {
  for (let guard = 0; guard < 100; guard++) {
    now += 100
    const pending = frames
    frames = []
    if (!pending.length) return
    pending.forEach((cb) => cb(now))
  }
}

describe('useCountUp', () => {
  beforeEach(() => {
    frames = []
    now = 0
    reduceMotion = false
  })
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('初值从 0 滚动到目标值', async () => {
    const src = ref<number | null>(66)
    const { result } = withSetup(() => useCountUp(src))
    flushAnimation()
    expect(result.display.value).toBe(66)
  })

  it('源值变化时从当前展示值续滚到新值', async () => {
    const src = ref<number | null>(10)
    const { result } = withSetup(() => useCountUp(src))
    flushAnimation()
    src.value = 42
    await nextTick()
    flushAnimation()
    expect(result.display.value).toBe(42)
  })

  it('滚动中间态单调逼近目标（easeOut 先快后慢）', () => {
    const src = ref<number | null>(100)
    const { result } = withSetup(() => useCountUp(src))
    // 第一帧（100ms / 800ms，easeOutCubic≈0.33）：应已滚过目标的三分之一
    now += 100
    const pending = frames
    frames = []
    pending.forEach((cb) => cb(now))
    expect(result.display.value).toBeGreaterThan(30)
    expect(result.display.value).toBeLessThan(100)
  })

  it('null 源不滚动，display 同步为 null', async () => {
    const src = ref<number | null>(null)
    const { result } = withSetup(() => useCountUp(src))
    expect(result.display.value).toBeNull()
    src.value = 7
    await nextTick()
    flushAnimation()
    src.value = null
    await nextTick()
    expect(result.display.value).toBeNull()
  })

  it('prefers-reduced-motion：直接落定不逐帧滚', () => {
    reduceMotion = true
    const src = ref<number | null>(99)
    const { result } = withSetup(() => useCountUp(src))
    expect(result.display.value).toBe(99)
    expect(frames.length).toBe(0)
  })

  it('组件卸载取消进行中的动画', () => {
    const src = ref<number | null>(50)
    const { result, unmount } = withSetup(() => useCountUp(src))
    unmount()
    // 卸载后残留帧全部丢弃，display 停在原地不再变化
    frames = []
    flushAnimation()
    expect(result.display.value).toBeLessThan(50)
  })
})

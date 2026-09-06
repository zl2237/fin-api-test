import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import type { progressState as PS, startProgress as SP, doneProgress as DP } from '../requestProgress'

// requestProgress 持有模块级 activeCount 计数器，跨测试会累积。
// 用 vi.resetModules + 动态导入，每个测试拿到全新模块实例。
let progressState: typeof PS
let startProgress: typeof SP
let doneProgress: typeof DP

beforeEach(async () => {
  vi.useFakeTimers()
  vi.resetModules()
  const mod = await import('../requestProgress')
  progressState = mod.progressState
  startProgress = mod.startProgress
  doneProgress = mod.doneProgress
})

afterEach(() => vi.useRealTimers())

describe('requestProgress', () => {
  it('startProgress 首次调用显示进度条', () => {
    startProgress()
    expect(progressState.visible).toBe(true)
    expect(progressState.percent).toBeGreaterThan(0)
  })

  it('并发 startProgress 不重复启动（计数累加）', () => {
    startProgress()
    const firstPercent = progressState.percent
    startProgress()
    // 第二次调用直接 return，percent 不重置
    expect(progressState.percent).toBe(firstPercent)
  })

  it('doneProgress 计数递减，未归零不结束', () => {
    startProgress()
    startProgress()
    doneProgress()
    // 还有 1 个并发，不进入完成态
    expect(progressState.percent).toBeLessThan(100)
  })

  it('doneProgress 归零后到 100% 并淡出', () => {
    startProgress()
    doneProgress()
    expect(progressState.percent).toBe(100)
    // 200ms 后隐藏
    vi.advanceTimersByTime(200)
    expect(progressState.visible).toBe(false)
  })

  it('doneProgress 计数不会负数', () => {
    doneProgress()
    doneProgress()
    // 不抛错即可
    expect(progressState.percent).toBeGreaterThanOrEqual(0)
  })
})

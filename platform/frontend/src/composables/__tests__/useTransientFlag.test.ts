import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { useTransientFlag } from '../useTransientFlag'

/**
 * useTransientFlag：就地反馈动效的时序原语。
 * 重点：trigger 即置位、到期自动回落、窗口期内重复触发重置计时（不提前回落）。
 */

describe('useTransientFlag', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())

  it('trigger 置位后到 ms 自动回落', async () => {
    const { active, trigger } = useTransientFlag(1500)
    expect(active.value).toBe(false)
    trigger()
    expect(active.value).toBe(true)
    await vi.advanceTimersByTimeAsync(1500)
    expect(active.value).toBe(false)
  })

  it('窗口期内重复触发重置计时，不提前回落', async () => {
    const { active, trigger } = useTransientFlag(1500)
    trigger()
    await vi.advanceTimersByTimeAsync(1400)
    trigger() // 距首次 1.4s 再次触发：计时从头算
    await vi.advanceTimersByTimeAsync(1400)
    expect(active.value).toBe(true)
    await vi.advanceTimersByTimeAsync(200)
    expect(active.value).toBe(false)
  })
})

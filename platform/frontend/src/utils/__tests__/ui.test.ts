import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { resolveMenuActive, debounce } from '../ui'

describe('resolveMenuActive', () => {
  const menuPaths = ['/home', '/apis', '/cases', '/executions', '/envs']

  it('完全匹配', () => {
    expect(resolveMenuActive('/apis', menuPaths)).toBe('/apis')
  })

  it('前缀匹配（段边界）', () => {
    expect(resolveMenuActive('/envs/edit/5', menuPaths)).toBe('/envs')
  })

  it('段边界不误匹配（/executions2 不匹配 /executions）', () => {
    expect(resolveMenuActive('/executions2', menuPaths)).toBe('/executions2')
  })

  it('无匹配回退当前路径', () => {
    expect(resolveMenuActive('/unknown', menuPaths)).toBe('/unknown')
  })

  it('最长前缀优先', () => {
    expect(resolveMenuActive('/apis/group/1', ['/api', '/apis', '/apis/group'])).toBe('/apis/group')
  })
})

describe('debounce', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())

  it('多次调用只生效最后一次', () => {
    const fn = vi.fn()
    const debounced = debounce(fn, 300)
    debounced('a')
    debounced('b')
    debounced('c')
    expect(fn).not.toHaveBeenCalled()
    vi.advanceTimersByTime(300)
    expect(fn).toHaveBeenCalledTimes(1)
    expect(fn).toHaveBeenCalledWith('c')
  })

  it('间隔超过 wait 的调用各生效一次', () => {
    const fn = vi.fn()
    const debounced = debounce(fn, 100)
    debounced('first')
    vi.advanceTimersByTime(100)
    debounced('second')
    vi.advanceTimersByTime(100)
    expect(fn).toHaveBeenCalledTimes(2)
    expect(fn).toHaveBeenNthCalledWith(1, 'first')
    expect(fn).toHaveBeenNthCalledWith(2, 'second')
  })

  it('默认 wait=300', () => {
    const fn = vi.fn()
    const debounced = debounce(fn)
    debounced()
    vi.advanceTimersByTime(299)
    expect(fn).not.toHaveBeenCalled()
    vi.advanceTimersByTime(1)
    expect(fn).toHaveBeenCalledTimes(1)
  })
})

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { useFaviconStatus } from '../useFaviconStatus'

function addLink(): HTMLLinkElement {
  const link = document.createElement('link')
  link.rel = 'icon'
  document.head.appendChild(link)
  return link
}

describe('useFaviconStatus', () => {
  let link: HTMLLinkElement
  const fav = useFaviconStatus()

  beforeEach(() => {
    vi.useFakeTimers()
    link = addLink()
    fav.reset()
  })
  afterEach(() => {
    fav.reset()
    link.remove()
    vi.useRealTimers()
  })

  it('running：data URI 且持续显示（不自动恢复）', () => {
    fav.running()
    expect(fav.state).toBe('running')
    expect(link.href.startsWith('data:image/svg+xml,')).toBe(true)
    expect(link.type).toBe('image/svg+xml')
    vi.advanceTimersByTime(10_000)
    expect(fav.state).toBe('running')
  })

  it('success/failed：3 秒后自动恢复默认', () => {
    fav.success()
    expect(fav.state).toBe('success')
    vi.advanceTimersByTime(3000)
    expect(fav.state).toBe('default')
    expect(link.href.endsWith('/favicon.svg')).toBe(true)

    fav.failed()
    expect(fav.state).toBe('failed')
    vi.advanceTimersByTime(2999)
    expect(fav.state).toBe('failed')
    vi.advanceTimersByTime(1)
    expect(fav.state).toBe('default')
  })

  it('状态切换会取消上一个恢复定时器（success 后 running 不被复位）', () => {
    fav.success()
    fav.running() // 覆盖恢复定时器
    vi.advanceTimersByTime(5000)
    expect(fav.state).toBe('running')
  })

  it('reset 立即恢复默认', () => {
    fav.running()
    fav.reset()
    expect(fav.state).toBe('default')
    expect(link.href.endsWith('/favicon.svg')).toBe(true)
  })

  it('SVG 内容按状态区分（token 缺省时用兜底色）', () => {
    fav.success()
    const svg = decodeURIComponent(link.href)
    expect(svg).toContain('#34c759') // getComputedStyle 无值 → success 兜底色
    fav.failed()
    expect(decodeURIComponent(link.href)).toContain('#ff3b30')
    fav.running()
    expect(decodeURIComponent(link.href)).toContain('#0f7285')
  })
})

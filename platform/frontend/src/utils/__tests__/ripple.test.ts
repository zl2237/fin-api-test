import { describe, it, expect, beforeEach, afterEach, vi, type MockInstance } from 'vitest'
import { setupRipple } from '../ripple'

describe('setupRipple', () => {
  let addSpy: ReturnType<typeof vi.spyOn>
  let matchMediaSpy: MockInstance<(query: string) => MediaQueryList>

  beforeEach(() => {
    addSpy = vi.spyOn(document, 'addEventListener')
    matchMediaSpy = vi.spyOn(window, 'matchMedia').mockReturnValue({
      matches: false,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    } as unknown as MediaQueryList)
  })
  afterEach(() => {
    addSpy.mockRestore()
    matchMediaSpy.mockRestore()
  })

  it('注册 document click 监听', () => {
    setupRipple()
    expect(addSpy).toHaveBeenCalledWith('click', expect.any(Function))
  })

  it('prefers-reduced-motion 时不触发涟漪', () => {
    matchMediaSpy.mockReturnValue({
      matches: true,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    } as unknown as MediaQueryList)
    setupRipple()
    const handler = addSpy.mock.calls[0][1] as (e: MouseEvent) => void
    const btn = document.createElement('button')
    btn.className = 'el-button'
    document.body.appendChild(btn)
    const e = { target: btn } as unknown as MouseEvent
    handler(e)
    expect(btn.querySelector('.btn-ripple')).toBeNull()
    btn.remove()
  })

  it('点击 .el-button 创建涟漪 span', () => {
    setupRipple()
    const handler = addSpy.mock.calls[0][1] as (e: MouseEvent) => void
    const btn = document.createElement('button')
    btn.className = 'el-button'
    btn.getBoundingClientRect = () => ({ width: 80, height: 32, left: 0, top: 0, right: 80, bottom: 32, x: 0, y: 0, toJSON: () => ({}) } as DOMRect)
    document.body.appendChild(btn)
    const e = { target: btn, clientX: 40, clientY: 16 } as unknown as MouseEvent
    handler(e)
    const ripple = btn.querySelector('.btn-ripple')
    expect(ripple).not.toBeNull()
    btn.remove()
  })

  it('disabled 按钮不触发涟漪', () => {
    setupRipple()
    const handler = addSpy.mock.calls[0][1] as (e: MouseEvent) => void
    const btn = document.createElement('button')
    btn.className = 'el-button is-disabled'
    document.body.appendChild(btn)
    const e = { target: btn, clientX: 0, clientY: 0 } as unknown as MouseEvent
    handler(e)
    expect(btn.querySelector('.btn-ripple')).toBeNull()
    btn.remove()
  })

  it('非按钮元素不触发涟漪', () => {
    setupRipple()
    const handler = addSpy.mock.calls[0][1] as (e: MouseEvent) => void
    const div = document.createElement('div')
    document.body.appendChild(div)
    const e = { target: div, clientX: 0, clientY: 0 } as unknown as MouseEvent
    handler(e)
    expect(div.querySelector('.btn-ripple')).toBeNull()
    div.remove()
  })
})

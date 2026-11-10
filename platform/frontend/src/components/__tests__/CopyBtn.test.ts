import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { createApp, nextTick } from 'vue'

/**
 * CopyBtn：报告页一键复制（icon 点击即复制 + 对勾短暂反馈）。
 * 重点：序列化口径（对象 2 空格 JSON / 标量 String）、空值静默、
 * 成功后 is-ok 1.2s 回落、失败提示不打断。
 */

vi.mock('@/utils/clipboard', () => ({
  writeClipboard: vi.fn(),
}))
vi.mock('element-plus', () => {
  const ElMessage: any = vi.fn()
  ElMessage.success = vi.fn()
  ElMessage.error = vi.fn()
  return { ElMessage }
})

import { writeClipboard } from '@/utils/clipboard'
import { ElMessage } from 'element-plus'

async function mountBtn(props: Record<string, unknown>) {
  const { default: CopyBtn } = await import('../CopyBtn.vue')
  const app = createApp(CopyBtn as any, props)
  // element-plus 被 mock（仅 ElMessage），el-icon 用轻量替身注册
  app.component('el-icon', { template: '<i><slot /></i>' })
  const host = document.createElement('div')
  document.body.appendChild(host)
  const vm: any = app.mount(host)
  await nextTick()
  return { host, vm }
}

function clickBtn(host: HTMLElement) {
  const btn = host.querySelector<HTMLButtonElement>('.copy-btn')
  expect(btn).toBeTruthy()
  btn!.click()
}

describe('CopyBtn 一键复制', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.clearAllMocks()
    ;(writeClipboard as any).mockResolvedValue(true)
  })
  afterEach(() => {
    vi.useRealTimers()
    document.body.innerHTML = ''
  })

  it('对象按 2 空格 JSON 序列化写入剪贴板，成功后 icon 切对勾并在 1.2s 回落', async () => {
    const { host } = await mountBtn({ value: { a: 1 } })
    clickBtn(host)
    await vi.advanceTimersByTimeAsync(0)
    expect(writeClipboard).toHaveBeenCalledWith('{\n  "a": 1\n}')
    // 对勾态：class 标记 + title 切换
    expect(host.querySelector('.copy-btn')!.classList.contains('is-ok')).toBe(true)
    expect((host.querySelector('.copy-btn') as HTMLButtonElement).title).toBe('已复制')
    await vi.advanceTimersByTimeAsync(1200)
    expect(host.querySelector('.copy-btn')!.classList.contains('is-ok')).toBe(false)
  })

  it('标量转字符串原样复制（数字/长 ID 字符串）', async () => {
    // 注：大整数不能用 JS number 字面量断言（>2^53 会精度丢失成 …850），
    // 实际数据里这类 ID 均以字符串到达
    const { host } = await mountBtn({ value: 12345 })
    clickBtn(host)
    await vi.advanceTimersByTimeAsync(0)
    expect(writeClipboard).toHaveBeenCalledWith('12345')

    const { host: h2 } = await mountBtn({ value: '378385244119630848' })
    clickBtn(h2)
    await vi.advanceTimersByTimeAsync(0)
    expect(writeClipboard).toHaveBeenLastCalledWith('378385244119630848')
  })

  it('空值点击静默忽略：不写剪贴板、不进对勾态', async () => {
    const { host } = await mountBtn({ value: '' })
    clickBtn(host)
    await vi.advanceTimersByTimeAsync(0)
    expect(writeClipboard).not.toHaveBeenCalled()
    expect(host.querySelector('.copy-btn')!.classList.contains('is-ok')).toBe(false)
  })

  it('复制失败（剪贴板不可用）：报错误提示，不进对勾态', async () => {
    ;(writeClipboard as any).mockResolvedValue(false)
    const { host } = await mountBtn({ value: 'x' })
    clickBtn(host)
    await vi.advanceTimersByTimeAsync(0)
    expect(ElMessage.error).toHaveBeenCalledWith('复制失败，请手动选择复制')
    expect(host.querySelector('.copy-btn')!.classList.contains('is-ok')).toBe(false)
  })
})

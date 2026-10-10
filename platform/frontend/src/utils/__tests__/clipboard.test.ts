import { describe, it, expect, beforeEach, vi } from 'vitest'

vi.mock('element-plus', () => {
  const ElMessage: any = vi.fn()
  ElMessage.success = vi.fn()
  ElMessage.error = vi.fn()
  return { ElMessage }
})

import { ElMessage } from 'element-plus'
import { writeClipboard, copyText } from '../clipboard'

describe('clipboard', () => {
  beforeEach(() => vi.clearAllMocks())

  it('navigator.clipboard 可用时走 writeText 快路径', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    vi.stubGlobal('navigator', { clipboard: { writeText } })
    // jsdom 无 isSecureContext 属性 → undefined（falsy）；直接定义以覆盖分支
    Object.defineProperty(window, 'isSecureContext', { configurable: true, get: () => true })
    await expect(writeClipboard('abc')).resolves.toBe(true)
    expect(writeText).toHaveBeenCalledWith('abc')
    vi.unstubAllGlobals()
    Object.defineProperty(window, 'isSecureContext', { configurable: true, get: () => false })
  })

  it('降级 execCommand：成功与失败两条路径都清理临时节点', async () => {
    vi.stubGlobal('navigator', {})
    Object.defineProperty(window, 'isSecureContext', { configurable: true, get: () => false })
    // jsdom 未实现 execCommand，直接注入替身
    const exec = vi.fn().mockReturnValue(true)
    document.execCommand = exec as unknown as typeof document.execCommand
    await expect(writeClipboard('x')).resolves.toBe(true)
    expect(exec).toHaveBeenCalledWith('copy')

    exec.mockReturnValue(false)
    await expect(writeClipboard('x')).resolves.toBe(false)
    expect(document.querySelectorAll('textarea')).toHaveLength(0) // 节点已清理
    delete (document as any).execCommand
    vi.unstubAllGlobals()
  })

  it('copyText：成功/失败提示', async () => {
    vi.stubGlobal('navigator', {})
    Object.defineProperty(window, 'isSecureContext', { configurable: true, get: () => false })
    const exec = vi.fn().mockReturnValue(true)
    document.execCommand = exec as unknown as typeof document.execCommand
    await copyText('data', '已复制到剪贴板')
    expect(ElMessage.success).toHaveBeenCalledWith('已复制到剪贴板')
    exec.mockReturnValue(false)
    await copyText('data')
    expect(ElMessage.error).toHaveBeenCalledWith('复制失败，请手动选择复制')
    delete (document as any).execCommand
    vi.unstubAllGlobals()
  })
})

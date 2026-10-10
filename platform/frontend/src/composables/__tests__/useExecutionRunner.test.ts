import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { createApp, ref } from 'vue'

vi.mock('@/api', () => ({
  caseApi: { execute: vi.fn() },
  execApi: { get: vi.fn() },
}))
vi.mock('element-plus', () => {
  const ElMessage: any = vi.fn(() => ({ close: vi.fn() }))
  ElMessage.success = vi.fn()
  ElMessage.warning = vi.fn()
  ElMessage.error = vi.fn()
  return { ElMessage }
})

import { ElMessage } from 'element-plus'
import { caseApi, execApi } from '@/api'
import { useExecutionRunner, type ExecRecordLike } from '../useExecutionRunner'

/** 在真实组件 setup 中执行 composable（onUnmounted 需组件实例），返回 {结果, 卸载} */
function withSetup<T>(composable: () => T): { result: T; unmount: () => void } {
  let result!: T
  const app = createApp({ setup() { result = composable(); return () => {} } })
  app.mount(document.createElement('div'))
  return { result, unmount: () => app.unmount() }
}

const mockedExecute = vi.mocked(caseApi.execute)
const mockedGet = vi.mocked(execApi.get)

// any：mock 返回值需同时满足 composable 的宽松接口与真实 API 签名（测试替身不逐字段构造）
function rec(status: string, summary?: Record<string, unknown>): any {
  return { id: 7, status, summary }
}

describe('useExecutionRunner', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.clearAllMocks()
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('pollUntilDone：轮询到终态 resolve，不再继续轮询', async () => {
    mockedGet.mockResolvedValueOnce(rec('running')).mockResolvedValueOnce(rec('success'))
    const { result } = withSetup(() => useExecutionRunner())
    const p = result.pollUntilDone(7, { interval: 10 })
    await vi.advanceTimersByTimeAsync(10)
    await vi.advanceTimersByTimeAsync(10)
    await expect(p).resolves.toMatchObject({ status: 'success' })
    expect(mockedGet).toHaveBeenCalledTimes(2)
  })

  it('pollUntilDone：达上限不抛错，resolve 最后一次 running 记录', async () => {
    mockedGet.mockResolvedValue(rec('running'))
    const { result } = withSetup(() => useExecutionRunner())
    const p = result.pollUntilDone(7, { interval: 10, maxPolls: 3 })
    await vi.advanceTimersByTimeAsync(100)
    await expect(p).resolves.toMatchObject({ status: 'running' })
    expect(mockedGet).toHaveBeenCalledTimes(3)
  })

  it('pollUntilDone：网络错误 reject', async () => {
    mockedGet.mockRejectedValue(new Error('boom'))
    const { result } = withSetup(() => useExecutionRunner())
    const p = result.pollUntilDone(7, { interval: 10 })
    const assertion = expect(p).rejects.toThrow('boom') // 先挂接再走定时器，避免未处理拒绝告警
    await vi.advanceTimersByTimeAsync(10)
    await assertion
  })

  it('runWithFeedback：成功路径（进度消息关闭 + 成功提示）', async () => {
    mockedExecute.mockResolvedValue(rec('running'))
    mockedGet.mockResolvedValueOnce(rec('running')).mockResolvedValueOnce(
      rec('success', { passed: 2, total: 3 }))
    const { result } = withSetup(() => useExecutionRunner())
    const p = result.runWithFeedback(1, 2, { interval: 10 })
    await vi.advanceTimersByTimeAsync(20)
    await expect(p).resolves.toMatchObject({ status: 'success' })
    expect(ElMessage).toHaveBeenCalledTimes(1) // 进度消息
    expect(ElMessage.success).toHaveBeenCalledWith('执行通过：2/3')
  })

  it('runWithFeedback：超时提示 + failed 路径带原因', async () => {
    mockedExecute.mockResolvedValue(rec('running'))
    mockedGet.mockResolvedValue(rec('running'))
    const { result } = withSetup(() => useExecutionRunner())
    const p1 = result.runWithFeedback(1, 2, { interval: 10, maxPolls: 1 })
    await vi.advanceTimersByTimeAsync(50)
    await expect(p1).resolves.toMatchObject({ status: 'running' })
    expect(ElMessage.warning).toHaveBeenCalledWith('执行超时，请到执行记录查看结果')

    mockedGet.mockResolvedValue(rec('failed', { failed: 4, error: '登录失败' }))
    const p2 = result.runWithFeedback(1, 2, { interval: 10 })
    await vi.advanceTimersByTimeAsync(50)
    await expect(p2).resolves.toMatchObject({ status: 'failed' })
    expect(ElMessage.warning).toHaveBeenCalledWith('执行失败：4 项未通过（登录失败）')
  })

  it('refreshWhileRunning：fetcher 返回 true 继续 / false 停止 / 抛错静默停止 / stop() 主动终止', async () => {
    const { result } = withSetup(() => useExecutionRunner())
    const fetcher = vi.fn().mockResolvedValue(true)
    const stop = result.refreshWhileRunning(fetcher, { interval: 10 })
    await vi.advanceTimersByTimeAsync(10)
    expect(fetcher).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(10)
    expect(fetcher).toHaveBeenCalledTimes(2)

    stop()
    await vi.advanceTimersByTimeAsync(30)
    expect(fetcher).toHaveBeenCalledTimes(2)

    const ending = vi.fn().mockResolvedValue(false)
    result.refreshWhileRunning(ending, { interval: 10 })
    await vi.advanceTimersByTimeAsync(30)
    expect(ending).toHaveBeenCalledTimes(1)

    const failing = vi.fn().mockRejectedValue(new Error('x'))
    result.refreshWhileRunning(failing, { interval: 10 })
    await vi.advanceTimersByTimeAsync(30)
    expect(failing).toHaveBeenCalledTimes(1)
  })

  it('组件卸载统一清理定时器（不再产生新轮询）', async () => {
    mockedGet.mockResolvedValue(rec('running'))
    const { result, unmount } = withSetup(() => useExecutionRunner())
    result.pollUntilDone(7, { interval: 10 })
    await vi.advanceTimersByTimeAsync(10)
    expect(mockedGet).toHaveBeenCalledTimes(1)
    unmount()
    await vi.advanceTimersByTimeAsync(100)
    expect(mockedGet).toHaveBeenCalledTimes(1) // 清理后无新轮询
  })
})

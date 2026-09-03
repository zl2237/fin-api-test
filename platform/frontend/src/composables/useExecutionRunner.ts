/**
 * 执行轮询深模块：单点管理「执行是异步资源，轮询到终态并反馈 UI」的全部机制——
 * 定时器注册表、卸载清理、间隔/上限策略、favicon 三态、结果提示。
 *
 * 此前 5 份实现（CaseList runCase/pollOne、CaseDesigner onRun、ReportDetail
 * schedulePollIfRunning、Execution startAutoRefresh）各自维护定时器数组与
 * 魔法数（2s/3s、150/300），节奏与超时策略漂移且无法单点治理。
 *
 * 接口（窄）：
 * - runWithFeedback：单用例完整体验（执行→进度消息→轮询→三态 favicon→结果提示）
 * - pollUntilDone：纯轮询到终态（批量/数据驱动的 Promise.all 汇总用）
 * - refreshWhileRunning：running 态自刷新循环（列表/详情页）；fetcher 返回 false
 *   或抛错即停；返回 stop() 供主动终止
 */
import { onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'
import { caseApi, execApi } from '@/api'
import { useFaviconStatus } from '@/composables/useFaviconStatus'

export interface ExecSummary {
  total?: number
  passed?: number
  failed?: number
  [key: string]: unknown
}

export interface ExecRecordLike {
  id: number
  status: string
  summary?: ExecSummary
}

export interface PollOptions {
  /** 轮询间隔（ms），缺省 2000 */
  interval?: number
  /** 最大轮询次数，缺省 300（2s 间隔约 10 分钟） */
  maxPolls?: number
}

export function useExecutionRunner() {
  const favicon = useFaviconStatus()
  const timers: ReturnType<typeof setTimeout>[] = []
  const track = (t: ReturnType<typeof setTimeout>) => {
    timers.push(t)
    return t
  }
  const clearAll = () => {
    timers.forEach(clearTimeout)
    timers.length = 0
  }
  // 组件卸载统一清理：调用方不必再各自维护 pollTimers 数组
  onUnmounted(clearAll)

  /**
   * 轮询执行记录直到终态或达上限。超限不抛错——resolve 最后一次记录
   * （status 仍为 running），由调用方按「超时」语义处理。
   */
  function pollUntilDone(execId: number, opts: PollOptions = {}): Promise<ExecRecordLike> {
    const interval = opts.interval ?? 2000
    const maxPolls = opts.maxPolls ?? 300
    return new Promise((resolve, reject) => {
      let count = 0
      const poll = async () => {
        count++
        try {
          const cur: ExecRecordLike = await execApi.get(execId, true)
          if (cur.status === 'running' && count < maxPolls) {
            track(setTimeout(poll, interval))
          } else {
            resolve(cur)
          }
        } catch (e) {
          reject(e)
        }
      }
      track(setTimeout(poll, interval))
    })
  }

  /**
   * 单用例执行完整反馈：execute → 进度消息（不自动关）→ 轮询 → favicon 三态
   * + 结果提示。返回最终记录（超时时 status 为 running）；execute 失败或轮询
   * 网络错误在关闭进度消息、复位 favicon 后原样抛出。
   */
  async function runWithFeedback(
    caseId: number,
    envId: number,
    opts: PollOptions & { runningMsg?: string } = {},
  ): Promise<ExecRecordLike> {
    const rec: ExecRecordLike = await caseApi.execute(caseId, envId)
    favicon.running()
    const msg = ElMessage({ message: opts.runningMsg ?? '执行中...', type: 'info', duration: 0 })
    try {
      const cur = await pollUntilDone(rec.id, opts)
      msg.close()
      if (cur.status === 'success') {
        favicon.success()
        ElMessage.success(`执行通过：${cur.summary?.passed ?? 0}/${cur.summary?.total ?? 0}`)
      } else if (cur.status === 'running') {
        favicon.reset()
        ElMessage.warning('执行超时，请到执行记录查看结果')
      } else {
        favicon.failed()
        ElMessage.warning(`执行失败：${cur.summary?.failed ?? 0} 项未通过`)
      }
      return cur
    } catch (e) {
      msg.close()
      favicon.reset()
      throw e
    }
  }

  /**
   * running 态自刷新循环：每隔 interval 执行一次 fetcher；fetcher 返回 false
   * 或抛错即静默停止（刷新失败由调用方的加载逻辑兜底）。返回 stop()。
   */
  function refreshWhileRunning(fetcher: () => Promise<boolean>, opts: PollOptions = {}): () => void {
    let stopped = false
    let timer: ReturnType<typeof setTimeout> | null = null
    const tick = async () => {
      if (stopped) return
      try {
        const still = await fetcher()
        if (!stopped && still) timer = track(setTimeout(tick, opts.interval ?? 3000))
      } catch {
        stopped = true
      }
    }
    timer = track(setTimeout(tick, opts.interval ?? 3000))
    return () => {
      stopped = true
      if (timer) clearTimeout(timer)
    }
  }

  return { runWithFeedback, pollUntilDone, refreshWhileRunning, clearAllPolls: clearAll }
}

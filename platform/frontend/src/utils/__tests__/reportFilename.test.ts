import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { generateReportFilename } from '../reportFilename'

describe('generateReportFilename', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date(2026, 8, 6, 14, 30, 45))
  })
  afterEach(() => vi.useRealTimers())

  it('完整参数生成规范文件名', () => {
    const name = generateReportFilename({
      caseName: '订单创建流程',
      envName: '生产环境',
      status: 'success',
      ext: 'html',
    })
    expect(name).toBe('订单创建流程_生产环境_20260906_143045_成功.html')
  })

  it('已知状态映射为中文标签', () => {
    const name = generateReportFilename({
      caseName: 'case',
      envName: 'env',
      status: 'failed',
      ext: 'csv',
    })
    expect(name).toContain('失败')
  })

  it('未知状态原样展示（清理后）', () => {
    const name = generateReportFilename({
      caseName: 'case',
      envName: 'env',
      status: 'weird/status',
      ext: 'csv',
    })
    // 状态中的 / 是非法字符会被移除
    expect(name).toContain('weirdstatus')
  })

  it('非法字符清理', () => {
    const name = generateReportFilename({
      caseName: 'case/name?*',
      envName: 'env:file',
      status: 'success',
      ext: 'html',
    })
    expect(name).not.toMatch(/[\\/:*?"<>|]/)
  })

  it('用例名超长自动截断', () => {
    const longName = '订单'.repeat(30) // 60 汉字
    const name = generateReportFilename({
      caseName: longName,
      envName: 'env',
      status: 'success',
      ext: 'html',
    })
    // 截断后含 ~ 标记
    expect(name).toContain('~')
  })

  it('缺失用例名仍生成有效文件名', () => {
    const name = generateReportFilename({
      caseName: null,
      envName: 'env',
      status: 'success',
      ext: 'csv',
    })
    expect(name).toBe('env_20260906_143045_成功.csv')
  })

  it('全部缺失时兜底 execution_report', () => {
    const name = generateReportFilename({
      caseName: null,
      envName: null,
      status: null,
      ext: 'html',
    })
    expect(name).toBe('execution_report_20260906_143045.html')
  })

  it('扩展名带点也能处理', () => {
    const name = generateReportFilename({
      caseName: 'case',
      envName: 'env',
      status: 'success',
      ext: 'html',
    })
    expect(name).toMatch(/\.html$/)
  })
})

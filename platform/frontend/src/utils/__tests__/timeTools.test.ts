import { describe, expect, it } from 'vitest'
import {
  fmtIso, fmtLocal, fmtRelative, fmtUtc, fmtWeekday,
  parseDateInput, parseTimestamp,
} from '../timeTools'

// 固定基准：2026-11-16 12:30:45 Asia/Shanghai（UTC+8）= 2026-11-16 04:30:45Z
const MS = Date.UTC(2026, 10, 16, 4, 30, 45)

describe('parseTimestamp', () => {
  it('10 位数字按秒', () => {
    const r = parseTimestamp('1763267445')
    expect(r.ok).toBe(true)
    expect(r.unit).toBe('s')
    expect(r.ms).toBe(1763267445 * 1000)
  })
  it('13 位数字按毫秒', () => {
    const r = parseTimestamp('1763267445000')
    expect(r.ok).toBe(true)
    expect(r.unit).toBe('ms')
    expect(r.ms).toBe(1763267445000)
  })
  it('16 位数字按微秒', () => {
    const r = parseTimestamp('1763267445000000')
    expect(r.ok).toBe(true)
    expect(r.unit).toBe('us')
    expect(r.ms).toBe(1763267445000)
  })
  it('支持负数（1970 前）', () => {
    const r = parseTimestamp('-100')
    expect(r.ok).toBe(true)
    expect(r.ms).toBe(-100_000)
  })
  it('非法输入拒绝', () => {
    expect(parseTimestamp('abc').ok).toBe(false)
    expect(parseTimestamp('').ok).toBe(false)
    expect(parseTimestamp('1763267445x').ok).toBe(false)
  })
})

describe('parseDateInput', () => {
  it('空格分隔按本地时区解析（Safari 兼容 T 归一）', () => {
    const r = parseDateInput('2026-11-16 12:30:45')
    expect(r.ok).toBe(true)
    // 本地时区无关性：解析结果应等于「本地构造的同一时刻」
    expect(r.ms).toBe(new Date(2026, 10, 16, 12, 30, 45).getTime())
  })
  it('Z 后缀按 UTC', () => {
    expect(parseDateInput('2026-11-16T04:30:45Z').ms).toBe(MS)
  })
  it('+08:00 后缀按显式时区', () => {
    expect(parseDateInput('2026-11-16 12:30:45+08:00').ms).toBe(MS)
  })
  it('纯数字输入回落时间戳口径', () => {
    expect(parseDateInput('1763267445').ms).toBe(1763267445 * 1000)
  })
  it('非法日期拒绝', () => {
    expect(parseDateInput('2026-13-99').ok).toBe(false)
    expect(parseDateInput('hello').ok).toBe(false)
  })
})

describe('格式化输出', () => {
  it('UTC 输出带后缀', () => {
    expect(fmtUtc(MS)).toBe('2026-11-16 04:30:45 UTC')
  })
  it('ISO 输出', () => {
    expect(fmtIso(MS)).toBe('2026-11-16T04:30:45Z')
  })
  it('本地输出格式', () => {
    expect(fmtLocal(MS)).toMatch(/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/)
  })
  it('星期计算（UTC 时区下该时刻为周一）', () => {
    expect(fmtWeekday(Date.UTC(2026, 10, 16, 12))).toBe('周一')
  })
})

describe('fmtRelative', () => {
  const NOW = 1_000_000_000_000
  it('各档位', () => {
    expect(fmtRelative(NOW, NOW)).toBe('刚刚')
    expect(fmtRelative(NOW - 5_000, NOW)).toBe('5 秒前')
    expect(fmtRelative(NOW + 3 * 60_000, NOW)).toBe('3 分钟后')
    expect(fmtRelative(NOW - 2 * 3_600_000, NOW)).toBe('2 小时前')
    expect(fmtRelative(NOW + 3 * 86_400_000, NOW)).toBe('3 天后')
  })
  it('超 30 天回落绝对日期', () => {
    expect(fmtRelative(NOW - 40 * 86_400_000, NOW)).toMatch(/^\d{4}-\d{2}-\d{2} /)
  })
})

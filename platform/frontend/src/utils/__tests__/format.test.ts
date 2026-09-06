import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { formatTime, formatRelativeTime, execStatusType, execStatusText, fileTimestamp } from '../format'

describe('formatTime', () => {
  it('空值返回 —', () => {
    expect(formatTime(null)).toBe('—')
    expect(formatTime(undefined)).toBe('—')
    expect(formatTime('')).toBe('—')
  })

  it('ISO 串替换 T 为空格并截 19 位', () => {
    expect(formatTime('2026-09-06T14:30:45.123456')).toBe('2026-09-06 14:30:45')
  })

  it('不含 T 的串直接截 19 位', () => {
    expect(formatTime('2026-09-06 14:30:45')).toBe('2026-09-06 14:30:45')
  })

  it('短串原样返回', () => {
    expect(formatTime('2026-09-06')).toBe('2026-09-06')
  })
})

describe('formatRelativeTime', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-09-06T14:30:00'))
  })
  afterEach(() => vi.useRealTimers())

  it('空值返回 —', () => {
    expect(formatRelativeTime(null)).toBe('—')
    expect(formatRelativeTime(undefined)).toBe('—')
  })

  it('无效时间回退 formatTime', () => {
    expect(formatRelativeTime('not-a-date')).toBe('not-a-date'.replace('T', ' ').slice(0, 19))
  })

  it('刚刚（<1 分钟）', () => {
    expect(formatRelativeTime('2026-09-06T14:29:30')).toBe('刚刚')
  })

  it('N 分钟前', () => {
    expect(formatRelativeTime('2026-09-06T14:27:00')).toBe('3 分钟前')
  })

  it('N 小时前', () => {
    expect(formatRelativeTime('2026-09-06T11:30:00')).toBe('3 小时前')
  })

  it('昨天 HH:mm', () => {
    expect(formatRelativeTime('2026-09-05T14:20:00')).toBe('昨天 14:20')
  })

  it('N 天前（<7 天）', () => {
    expect(formatRelativeTime('2026-09-03T14:20:00')).toBe('3 天前')
  })

  it('MM-DD（7-180 天）', () => {
    expect(formatRelativeTime('2026-08-01T14:20:00')).toBe('08-01')
  })

  it('YYYY-MM-DD（>180 天）', () => {
    expect(formatRelativeTime('2025-01-01T14:20:00')).toBe('2025-01-01')
  })
})

describe('execStatusType', () => {
  it.each([
    ['success', 'success'],
    ['running', 'warning'],
    ['blocked', 'warning'],
    ['skipped', 'info'],
  ] as const)('状态 %s → %s', (status, expected) => {
    expect(execStatusType(status)).toBe(expected)
  })

  it('null → info', () => expect(execStatusType(null as unknown as string | undefined)).toBe('info'))
  it('undefined → info', () => expect(execStatusType(undefined)).toBe('info'))
  it('未知 → danger', () => expect(execStatusType('unknown')).toBe('danger'))
})

describe('execStatusText', () => {
  it.each([
    ['success', '通过'],
    ['running', '执行中'],
    ['failed', '失败'],
    ['blocked', '阻断'],
    ['skipped', '跳过'],
  ])('状态 %s → %s', (status, expected) => {
    expect(execStatusText(status)).toBe(expected)
  })

  it('未知状态原样展示', () => {
    expect(execStatusText('unknown')).toBe('unknown')
  })

  it('null → -', () => expect(execStatusText(null as unknown as string | undefined)).toBe('-'))
  it('undefined → -', () => expect(execStatusText(undefined)).toBe('-'))
})

describe('fileTimestamp', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date(2026, 8, 6, 14, 30, 45))
  })
  afterEach(() => vi.useRealTimers())

  it('格式 YYYYMMDDHHmmss', () => {
    expect(fileTimestamp()).toBe('20260906143045')
  })
})

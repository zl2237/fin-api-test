import { describe, expect, it } from 'vitest'
import { envTone } from '../envTone'

describe('envTone', () => {
  it('prod 族识别（含中文）', () => {
    expect(envTone('prod')).toBe('prod')
    expect(envTone('Production')).toBe('prod')
    expect(envTone('生产环境')).toBe('prod')
    expect(envTone('fin-prod-01')).toBe('prod')
  })

  it('pre 族识别，且 preprod 归 pre（预发优先于生产匹配）', () => {
    expect(envTone('pre')).toBe('pre')
    expect(envTone('staging')).toBe('pre')
    expect(envTone('uat')).toBe('pre')
    expect(envTone('preprod')).toBe('pre')
    expect(envTone('灰度环境')).toBe('pre')
  })

  it('test/dev 族识别', () => {
    expect(envTone('test')).toBe('test')
    expect(envTone('SIT-01')).toBe('test')
    expect(envTone('dev2')).toBe('test')
    expect(envTone('联调环境')).toBe('test')
  })

  it('兜底：无名/未知名 → unknown', () => {
    expect(envTone(null)).toBe('unknown')
    expect(envTone('')).toBe('unknown')
    expect(envTone('自定义环境A')).toBe('unknown')
  })
})

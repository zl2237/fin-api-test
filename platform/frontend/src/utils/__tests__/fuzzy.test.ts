import { describe, it, expect } from 'vitest'
import { fuzzyMatch } from '../fuzzy'

describe('fuzzyMatch', () => {
  it('空查询返回 matched=true score=0', () => {
    const r = fuzzyMatch('', 'anything')
    expect(r.matched).toBe(true)
    expect(r.score).toBe(0)
    expect(r.positions).toEqual([])
  })

  it('完全匹配', () => {
    const r = fuzzyMatch('abc', 'abc')
    expect(r.matched).toBe(true)
    expect(r.positions).toEqual([0, 1, 2])
  })

  it('子串匹配', () => {
    const r = fuzzyMatch('abc', 'xxabcxx')
    expect(r.matched).toBe(true)
    expect(r.positions).toEqual([2, 3, 4])
  })

  it('不匹配返回 false', () => {
    const r = fuzzyMatch('xyz', 'abc')
    expect(r.matched).toBe(false)
    expect(r.score).toBe(0)
    expect(r.positions).toEqual([])
  })

  it('大小写不敏感', () => {
    const r = fuzzyMatch('ABC', 'aBc')
    expect(r.matched).toBe(true)
  })

  it('连续匹配比分散匹配得分高', () => {
    const consecutive = fuzzyMatch('abc', 'xabcdef')
    const scattered = fuzzyMatch('abc', 'axbxc')
    expect(consecutive.score).toBeGreaterThan(scattered.score)
  })

  it('词首匹配加分', () => {
    const wordStart = fuzzyMatch('ab', 'ab cd')
    const midWord = fuzzyMatch('ab', 'xxabxx')
    expect(wordStart.score).toBeGreaterThan(midWord.score)
  })

  it('紧凑匹配优先（跨度惩罚）', () => {
    const tight = fuzzyMatch('abc', 'abcdef')
    const loose = fuzzyMatch('abc', 'axbxc')
    expect(tight.score).toBeGreaterThan(loose.score)
  })

  it('positions 按匹配顺序排列', () => {
    const r = fuzzyMatch('abc', 'aXbXcX')
    expect(r.positions).toEqual([0, 2, 4])
  })
})

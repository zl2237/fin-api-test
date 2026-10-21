import { describe, expect, it } from 'vitest'
import { textDiff } from '../textDiff'

function plain(segs: { text: string; kind: string }[]) {
  return segs.map(s => `${s.kind}:${s.text}`).join(' ')
}

describe('textDiff', () => {
  it('完全相等：两侧全 same，无差异标记', () => {
    const r = textDiff('SUCCESS', 'SUCCESS')
    expect(plain(r.expected)).toBe('same:SUCCESS')
    expect(plain(r.actual)).toBe('same:SUCCESS')
  })

  it('部分差异：期望侧标 del，实际侧标 add', () => {
    const r = textDiff('code=0', 'code=1')
    expect(plain(r.expected)).toBe('same:code= del:0')
    expect(plain(r.actual)).toBe('same:code= add:1')
  })

  it('实际多出内容：仅 actual 侧有 add', () => {
    const r = textDiff('P0001', 'P0001X')
    expect(plain(r.expected)).toBe('same:P0001')
    expect(plain(r.actual)).toBe('same:P0001 add:X')
  })

  it('完全不同：整体 del / add', () => {
    const r = textDiff('abc', 'xyz')
    expect(plain(r.expected)).toBe('del:abc')
    expect(plain(r.actual)).toBe('add:xyz')
  })

  it('空值一侧：另一侧整体标记', () => {
    const r = textDiff('', 'timeout')
    expect(r.expected).toEqual([])
    expect(plain(r.actual)).toBe('add:timeout')
  })

  it('超长输入（token 数超限）走降级路径：不逐词对齐，整体标记', () => {
    const words = (n: number) => Array.from({ length: n }, (_, k) => `w${k}`).join(' ')
    const long = words(900)
    const r = textDiff(long, words(901))
    expect(r.expected).toEqual([{ text: long, kind: 'del' }])
    expect(r.actual.every(s => s.kind === 'add')).toBe(true)
  })

  it('相邻同 kind 段合并（DOM 节点数收敛）', () => {
    const r = textDiff('ab', 'cd')
    expect(r.expected).toEqual([{ text: 'ab', kind: 'del' }])
    expect(r.actual).toEqual([{ text: 'cd', kind: 'add' }])
  })
})

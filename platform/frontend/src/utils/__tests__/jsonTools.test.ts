import { describe, expect, it } from 'vitest'
import { locateJsonError, transformJson } from '../jsonTools'

describe('transformJson', () => {
  it('格式化（2 空格）+ 换行结构', () => {
    const r = transformJson('{"b":1,"a":[2,3]}', { indent: 2 })
    expect(r.ok).toBe(true)
    expect(r.output).toBe('{\n  "b": 1,\n  "a": [\n    2,\n    3\n  ]\n}')
  })
  it('压缩为单行', () => {
    const r = transformJson('{\n  "b": 1,\n  "a": [2, 3]\n}', { indent: 0 })
    expect(r.ok).toBe(true)
    expect(r.output).toBe('{"b":1,"a":[2,3]}')
  })
  it('递归键排序：所有层级字典序（与 Fastjson2 规范化同口径）', () => {
    const r = transformJson('{"z":1,"a":{"y":2,"b":3}}', { indent: 0, sortKeys: true })
    expect(r.output).toBe('{"a":{"b":3,"y":2},"z":1}')
  })
  it('排序不动数组元素顺序', () => {
    const r = transformJson('[{"b":1,"a":2},{"d":3,"c":4}]', { indent: 0, sortKeys: true })
    expect(r.output).toBe('[{"a":2,"b":1},{"c":4,"d":3}]')
  })
  it('非法 JSON 报错（行列定位由 locateJsonError 单测锁定，不依赖运行环境报错格式）', () => {
    const r = transformJson('{\n  "a": tru\n}')
    expect(r.ok).toBe(false)
    expect(r.error).toBeTruthy()
    expect(r.output).toBe('')
  })
})

describe('locateJsonError', () => {
  // Node ≥21 的 JSON.parse 报错无位置信息，定位逻辑用两种已知报错格式直接锁定
  it('V8/Chrome "at position N" → 换算行:列', () => {
    const text = '{\n  "a": tru\n}'
    // position 10 = 第 2 行第 8 个字符（0 起始偏移换算为 1 起始列）
    const r = locateJsonError(text, new Error("Unexpected token 't', \"…\" is not valid JSON at position 9"))
    expect(r.line).toBe(2)
    expect(r.col).toBe(8)
  })
  it('Firefox "at line X column Y" 原样提取', () => {
    const r = locateJsonError('{}', new Error('JSON.parse: unexpected character at line 3 column 7 of the JSON data'))
    expect(r.line).toBe(3)
    expect(r.col).toBe(7)
  })
  it('无位置信息 → 空（不误报）', () => {
    expect(locateJsonError('{}', new Error("Unexpected token 't', \"…\" is not valid JSON"))).toEqual({})
  })
  it('空输入提示', () => {
    expect(transformJson('   ').ok).toBe(false)
  })
})

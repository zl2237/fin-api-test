import { describe, it, expect } from 'vitest'
import { isParamSpec, toFileId } from '../paramSource'

/** 四来源参数判定/解析：ParamSourceForm 与 ParamSourceBadge 共用口径 */
describe('isParamSpec', () => {
  it('接受四来源结构', () => {
    for (const source of ['constant', 'func', 'ref', 'sql'] as const) {
      expect(isParamSpec({ source })).toBe(true)
    }
  })

  it('拒绝非 spec 形状（旧数据兜底为 constant 的分支依据）', () => {
    expect(isParamSpec(null)).toBe(false)
    expect(isParamSpec(undefined)).toBe(false)
    expect(isParamSpec('abc')).toBe(false)
    expect(isParamSpec(123)).toBe(false)
    expect(isParamSpec([])).toBe(false)              // 数组（批量体）不算 spec
    expect(isParamSpec({})).toBe(false)              // 无 source
    expect(isParamSpec({ source: 'magic' })).toBe(false) // 未知来源
    expect(isParamSpec({ source: 1 })).toBe(false)   // source 非字符串
  })
})

describe('toFileId', () => {
  it('数字与纯数字串 → file_id', () => {
    expect(toFileId(42)).toBe(42)
    expect(toFileId('42')).toBe(42)
    expect(toFileId('0')).toBe(0)
  })

  it('其余（空串/前导格式串/对象）→ null', () => {
    expect(toFileId('')).toBeNull()
    expect(toFileId('a42')).toBeNull()
    expect(toFileId('4.2')).toBeNull()
    expect(toFileId(null)).toBeNull()
    expect(toFileId({ id: 1 })).toBeNull()
  })
})

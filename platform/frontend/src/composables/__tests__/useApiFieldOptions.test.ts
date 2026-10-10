import { describe, it, expect, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useApiFieldOptions } from '../useApiFieldOptions'
import { useAppStore } from '@/stores'
import type { ApiField } from '@/api'

function field(p: Partial<ApiField>): ApiField {
  return { id: 1, key: '', field_type: 'string', required: false, sort_order: 0, ...p } as ApiField
}

describe('useApiFieldOptions', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('顶层字段：字典命中挂中文名，未命中仅类型后缀', () => {
    useAppStore().fieldDictMap = { order_id: '订单号' }
    const { fieldOptions } = useApiFieldOptions(() => [
      field({ key: 'order_id', field_type: 'string' }),
      field({ key: 'raw', field_type: 'int', label: '已有标签' }),
      field({ key: 'other', field_type: 'bool' }),
    ])
    const labels = fieldOptions.value.map((o) => o.label)
    expect(labels[0]).toBe('order_id（订单号）[string]')
    expect(labels[1]).toBe('raw（已有标签）[int]')
    expect(labels[2]).toBe('other [bool]')
    expect(fieldOptions.value[0]!.field?.key).toBe('order_id')
  })

  it('object/array 示例值嵌套展开，数组下标规范化进字典匹配，深度截断', () => {
    useAppStore().fieldDictMap = { 'supplier.name': '供应商名称' }
    const objField = field({
      key: 'ext', field_type: 'object',
      default_value: JSON.stringify({ level1: { level2: { level3: { level4: 'deep' } } }, tag: 1 }),
    })
    const arrField = field({
      key: 'supplier', field_type: 'array',
      default_value: JSON.stringify([{ name: 'n', amount: 1.5 }]),
    })
    const { fieldOptions } = useApiFieldOptions(() => [objField, arrField])
    const values = fieldOptions.value.map((o) => o.value)
    expect(values).toContain('ext')                          // 顶层
    expect(values).toContain('ext.level1')                   // 一层
    expect(values).toContain('ext.level1.level2')            // 二层
    expect(values).toContain('ext.level1.level2.level3')     // 三层（含对象本体）
    expect(values).not.toContain('ext.level1.level2.level3.level4') // 四层截断
    expect(values).toContain('supplier.0.name')
    expect(values).toContain('supplier.0.amount')
    const named = fieldOptions.value.find((o) => o.value === 'supplier.0.name')!
    expect(named.label).toBe('supplier.0.name（供应商名称）[string]')
    const num = fieldOptions.value.find((o) => o.value === 'supplier.0.amount')!
    expect(num.label).toBe('supplier.0.amount [number]') // 非整数 → number
  })

  it('非法 JSON / 空数组不展开', () => {
    const { fieldOptions } = useApiFieldOptions(() => [
      field({ key: 'bad', field_type: 'object', default_value: '{oops' }),
      field({ key: 'empty', field_type: 'array', default_value: '[]' }),
      field({ key: 'none', field_type: 'object' }),
    ])
    expect(fieldOptions.value.map((o) => o.value)).toEqual(['bad', 'empty', 'none'])
  })

  it('topFieldOf 精确取顶层字段', () => {
    const f = field({ key: 'k', field_type: 'string' })
    const { topFieldOf } = useApiFieldOptions(() => [f])
    expect(topFieldOf('k')).toBe(f)
    expect(topFieldOf('k.x')).toBeUndefined()
  })
})

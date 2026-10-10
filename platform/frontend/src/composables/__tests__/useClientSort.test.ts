import { ref, computed } from 'vue'
import { describe, it, expect, vi } from 'vitest'
import { useClientSort } from '../useClientSort'

interface Row { name: string; age: number }

const rows = ref<Row[]>([
  { name: 'c', age: 3 },
  { name: 'a', age: 1 },
  { name: 'b', age: 2 },
])
const accessors: Record<string, (r: Row) => string | number> = {
  name: (r) => r.name,
  age: (r) => r.age,
}

describe('useClientSort', () => {
  it('无排序时维持上游默认序', () => {
    const { sorted } = useClientSort(rows, accessors)
    expect(sorted.value.map((r) => r.name)).toEqual(['c', 'a', 'b'])
  })

  it('字符串列升序/降序', () => {
    const { onSortChange, sorted } = useClientSort(rows, accessors)
    onSortChange({ prop: 'name', order: 'ascending' })
    expect(sorted.value.map((r) => r.name)).toEqual(['a', 'b', 'c'])
    onSortChange({ prop: 'name', order: 'descending' })
    expect(sorted.value.map((r) => r.name)).toEqual(['c', 'b', 'a'])
  })

  it('数字列按数值比较而非字符串', () => {
    const nums = ref([{ v: 10 }, { v: 2 }, { v: 9 }])
    const { onSortChange, sorted } = useClientSort(nums, { v: (r: { v: number }) => r.v })
    onSortChange({ prop: 'v', order: 'ascending' })
    expect(sorted.value.map((r) => r.v)).toEqual([2, 9, 10])
  })

  it('三态取消（order=null）回到默认序', () => {
    const { onSortChange, sorted, sortProp } = useClientSort(rows, accessors)
    onSortChange({ prop: 'age', order: 'ascending' })
    expect(sortProp.value).toBe('age')
    onSortChange({ prop: 'age', order: null })
    expect(sortProp.value).toBeNull()
    expect(sorted.value.map((r) => r.name)).toEqual(['c', 'a', 'b'])
  })

  it('非白名单 prop 重置排序', () => {
    const { onSortChange, sortProp } = useClientSort(rows, accessors)
    onSortChange({ prop: 'age', order: 'ascending' })
    onSortChange({ prop: 'unknown', order: 'ascending' })
    expect(sortProp.value).toBeNull()
  })

  it('排序变化触发回调（页码回 1）；排序不修改源数组', () => {
    const onSortApplied = vi.fn()
    const { onSortChange, sorted } = useClientSort(rows, accessors, onSortApplied)
    onSortChange({ prop: 'age', order: 'descending' })
    expect(onSortApplied).toHaveBeenCalledTimes(1)
    expect(sorted.value).not.toBe(rows.value)
    expect(rows.value[0].name).toBe('c')
  })

  it('接受 ComputedRef 数据源', () => {
    const src = computed(() => [{ k: 'x' }, { k: 'm' }])
    const { onSortChange, sorted } = useClientSort(src, { k: (r: { k: string }) => r.k })
    onSortChange({ prop: 'k', order: 'ascending' })
    expect(sorted.value.map((r) => r.k)).toEqual(['m', 'x'])
  })
})

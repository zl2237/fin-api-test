import { ref, computed, type Ref, type ComputedRef } from 'vue'

/**
 * 本地列表表头排序（el-table sortable="custom" 配套）：
 * 在分页切片前对全量数据排序，避免 el-table 默认前端排序只排当前页切片的假象。
 * 表头三态取消排序回到 null = 维持上游默认序（接口序 / 手动拖拽序）。
 *
 * @param rows 全量数据源（过滤后的完整列表，非分页切片）
 * @param accessors 排序列白名单：prop → 取值函数（统一返回可比较的 string/number）
 * @param onSortApplied 排序变化后的回调（通常是页码回到第 1 页）
 */
export function useClientSort<T>(
  rows: Ref<T[]> | ComputedRef<T[]>,
  accessors: Record<string, (item: T) => string | number>,
  onSortApplied?: () => void,
) {
  const sortProp = ref<string | null>(null)
  const sortOrder = ref<'asc' | 'desc'>('asc')

  function onSortChange({ prop, order }: { prop?: string; order?: string | null }) {
    if (!order || !prop || !(prop in accessors)) {
      sortProp.value = null
    } else {
      sortProp.value = prop
      sortOrder.value = order === 'ascending' ? 'asc' : 'desc'
    }
    onSortApplied?.()
  }

  const sorted = computed(() => {
    const key = sortProp.value
    if (!key) return rows.value
    const get = accessors[key]
    const dir = sortOrder.value === 'asc' ? 1 : -1
    return [...rows.value].sort((a, b) => {
      const va = get(a)
      const vb = get(b)
      const cmp = typeof va === 'number' && typeof vb === 'number'
        ? va - vb
        : String(va).localeCompare(String(vb))
      return cmp * dir
    })
  })

  return { sortProp, sortOrder, onSortChange, sorted }
}

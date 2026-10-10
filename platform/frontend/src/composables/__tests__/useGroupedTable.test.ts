import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { ref, computed } from 'vue'
import { useGroupedTable, setGroupSwitchNotifier, collectTreeUpdates, type ReorderableItem } from '../useGroupedTable'
import type { FlatGroup } from '../useGroupTree'

// Node 22 实验性 localStorage 覆盖了 jsdom 实现（undefined），用内存版替换
function stubLocalStorage() {
  const store = new Map<string, string>()
  vi.stubGlobal('localStorage', {
    getItem: (k: string) => store.get(k) ?? null,
    setItem: (k: string, v: string) => void store.set(k, String(v)),
    removeItem: (k: string) => void store.delete(k),
    clear: () => store.clear(),
  })
}

const G = (id: number, parent_id: number | null, name: string): FlatGroup =>
  ({ id, parent_id, name, sort_order: 0 })

interface Item extends ReorderableItem { group_id: number | null; name: string }

const IT = (id: number, group_id: number | null, sort_order = 0, name = `i${id}`): Item =>
  ({ id, group_id, sort_order, name })

function setup(items: Item[], groups: FlatGroup[] = [G(1, null, 'g1'), G(2, 1, 'g2')], scope = 'gt') {
  return useGroupedTable(ref(groups), ref<number | null>(1), scope, ref(items))
}

describe('useGroupedTable', () => {
  beforeEach(() => {
    stubLocalStorage()
    vi.restoreAllMocks()
    setGroupSwitchNotifier(() => {})
  })
  afterEach(() => vi.unstubAllGlobals())

  it('itemsOf：按分组过滤并按 sort_order 排序（未分组 = null）', () => {
    const t = setup([IT(1, 1, 2), IT(2, 1, 1), IT(3, null), IT(4, 2, 0)])
    expect(t.itemsOf(1).map((i) => i.id)).toEqual([2, 1])
    expect(t.itemsOf(null).map((i) => i.id)).toEqual([3])
    expect(t.itemsOf(2).map((i) => i.id)).toEqual([4])
  })

  it('countWithDescendants：含子孙分组计数', () => {
    const t = setup([IT(1, 1), IT(2, 2), IT(3, 2), IT(4, null)])
    expect(t.countWithDescendants(1)).toBe(3) // 1 + 子孙 2 的两条
    expect(t.countWithDescendants(2)).toBe(2)
  })

  it('visibleGroupRows：未分组有数据才出现未分组行；onToggleGroup 忽略未分组/空分组', () => {
    const t = setup([IT(1, 1)], [G(1, null, 'g1')])
    expect(t.visibleGroupRows.value.map((r) => r.key)).toEqual([1]) // 无未分组数据
    t.onToggleGroup({ groupId: null, isUngrouped: true, expandable: false }) // 无效果不抛错
    t.onToggleGroup({ groupId: 1, isUngrouped: false, expandable: false })  // 空分组不可展开
    expect(t.isExpanded(1)).toBe(false)
  })

  it('组内分页：切片/换页/改页大小重置页码/resetPages', () => {
    const items = Array.from({ length: 12 }, (_, i) => IT(i + 1, 1, i + 1))
    const t = setup(items)
    t.applyDefaultExpand()
    expect(t.pagedDataMap.value['1'].map((i) => i.id)).toEqual([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
    t.onPageChange(1, 2)
    expect(t.pagedDataMap.value['1'].map((i) => i.id)).toEqual([11, 12])
    t.onPageSizeChange(5)
    expect(t.pagedDataMap.value['1'].map((i) => i.id)).toEqual([1, 2, 3, 4, 5]) // 页码已重置
    t.onPageChange(1, 3)
    t.resetPages()
    expect(t.pageMap.value).toEqual({})
  })

  it('applyPageDragReorder：页内拖拽映射全量列表，持久化载荷为连续 sort_order，本地即时生效', async () => {
    const items = [IT(1, 1, 0), IT(2, 1, 1), IT(3, 1, 2), IT(4, 1, 3)]
    const t = setup(items)
    t.onPageSizeChange(2)         // 每页 2 条：第 2 页 = [3, 4]
    t.onPageChange(1, 2)
    const persist = vi.fn().mockResolvedValue(undefined)
    const moved = await t.applyPageDragReorder(1, 1, 0, persist) // 页内 4↔3 互换
    expect(moved).toBe(true)
    // 全量位置：[1,2,4,3] → sort_order 0..3
    expect(persist).toHaveBeenCalledWith([
      { id: 1, sort_order: 0 }, { id: 2, sort_order: 1 },
      { id: 4, sort_order: 2 }, { id: 3, sort_order: 3 },
    ])
    expect(t.itemsOf(1).map((i) => i.id)).toEqual([1, 2, 4, 3]) // 本地对象已更新，立即呈现新序
  })

  it('applyPageDragReorder：未位移返回 false 且不调用 persist', async () => {
    const t = setup([IT(1, 1)])
    const persist = vi.fn()
    await expect(t.applyPageDragReorder(1, 0, 0, persist)).resolves.toBe(false)
    expect(persist).not.toHaveBeenCalled()
  })

  it('互斥勾选：切组清其他表并提示；清空触发的空 selection 不处理；resetSelection 复位', () => {
    const t = setup([IT(1, 1)])
    const notifier = vi.fn()
    setGroupSwitchNotifier(notifier)
    const clearOthers = vi.fn()
    t.onSelectionChange('g1', [IT(1, 1)], clearOthers)
    expect(t.selectedIds.value).toEqual([1])
    t.onSelectionChange('g2', [IT(2, 2)], clearOthers) // 切组
    expect(clearOthers).toHaveBeenCalledWith('g2')
    expect(notifier).toHaveBeenCalledTimes(1)
    expect(t.selectedIds.value).toEqual([2])
    const clearAll = vi.fn()
    t.resetSelection(clearAll)
    expect(t.selectedIds.value).toEqual([])
    expect(clearAll).toHaveBeenCalled()
    t.onSelectionChange('g2', [], vi.fn()) // resetSelection 的 clearAll 触发 → isClearing 忽略
    expect(t.selectedIds.value).toEqual([])
  })
})

describe('collectTreeUpdates', () => {
  it('深度优先展开 parent_id/sort_order，根父为 null', () => {
    const G1 = { id: 1, label: 'a', children: [{ id: 2, label: 'b', children: [] }] }
    const G3 = { id: 3, label: 'c', children: [] }
    expect(collectTreeUpdates([G1, G3])).toEqual([
      { id: 1, parent_id: null, sort_order: 0 },
      { id: 2, parent_id: 1, sort_order: 0 },
      { id: 3, parent_id: null, sort_order: 1 },
    ])
  })
})

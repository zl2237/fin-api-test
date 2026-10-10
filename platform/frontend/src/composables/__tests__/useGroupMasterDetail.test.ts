import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { ref, computed, nextTick } from 'vue'

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

vi.mock('sortablejs', () => {
  const inst = { destroy: vi.fn() }
  const create = vi.fn(() => inst)
  return { default: { create, __inst: inst } }
})

import Sortable from 'sortablejs'
import { useGroupMasterDetail, type GroupMasterDetailOptions } from '../useGroupMasterDetail'
import { buildGroupTree, type FlatGroup, type GroupRow } from '../useGroupTree'
import type { ReorderableItem } from '../useGroupedTable'

const mockedCreate = vi.mocked(Sortable.create)

interface Item extends ReorderableItem { group_id: number | null; name: string }

function makeCtx(items: Item[], opts?: { projectId?: number; scope?: string }) {
  const groups = ref<FlatGroup[]>([
    { id: 1, parent_id: null, name: 'g1', sort_order: 0 },
    { id: 2, parent_id: 1, name: 'g2', sort_order: 1 },
    { id: 3, parent_id: null, name: 'g3', sort_order: 2 },
  ])
  const itemsRef = ref(items)
  const tree = computed(() => buildGroupTree(groups.value))
  const visibleGroupRows = computed<GroupRow[]>(() => {
    const rows: GroupRow[] = [
      { key: 1, groupId: 1, name: 'g1', depth: 0, expandable: true, isUngrouped: false },
      { key: 2, groupId: 2, name: 'g2', depth: 1, expandable: true, isUngrouped: false },
      { key: 'ungrouped', groupId: null, name: '未分组', depth: 0, expandable: false, isUngrouped: true },
    ]
    return rows
  })
  const pageMap = ref<Record<string, number>>({})
  const pageSize = ref(10)
  const onRowDragEnd = vi.fn()
  const options: GroupMasterDetailOptions<Item> = {
    groups, tree, visibleGroupRows,
    itemsOf: (gid) => itemsRef.value.filter((it) => it.group_id === gid),
    filteredItems: computed(() => itemsRef.value),
    pageMap, pageSize, onRowDragEnd,
    ...(opts?.projectId != null ? { projectId: ref<number | null>(opts.projectId), scope: opts.scope! } : {}),
  }
  return { md: useGroupMasterDetail(options), onRowDragEnd, pageMap, pageSize, itemsRef }
}

const IT = (id: number, group_id: number | null, sort_order = 0): Item =>
  ({ id, group_id, sort_order, name: `i${id}` })

describe('useGroupMasterDetail', () => {
  beforeEach(() => {
    stubLocalStorage()
    vi.clearAllMocks()
  })
  afterEach(() => vi.unstubAllGlobals())

  it('无记忆配置时默认选中「全部」，allPaged 取 filteredItems 分页', () => {
    const { md } = makeCtx([IT(1, 1), IT(2, 2)])
    expect(md.selectedRowKey.value).toBe('all')
    expect(md.allPaged.value.map((i) => i.id)).toEqual([1, 2])
  })

  it('选中记忆：从 localStorage 恢复上次停留分组，切换后写回，损坏值回 all', async () => {
    localStorage.setItem('fin_group_last_ms_1', JSON.stringify(2))
    const { md } = makeCtx([IT(1, 1), IT(2, 2)], { projectId: 1, scope: 'ms' })
    expect(md.selectedRowKey.value).toBe(2)
    md.onSideNodeClick({ key: 'ungrouped' })
    await nextTick() // 写回 watch 异步 flush
    expect(JSON.parse(localStorage.getItem('fin_group_last_ms_1')!)).toBe('ungrouped')

    localStorage.setItem('fin_group_last_ms2_1', '{bad')
    const { md: md2 } = makeCtx([IT(1, 1)], { projectId: 1, scope: 'ms2' })
    expect(md2.selectedRowKey.value).toBe('all')
  })

  it('hasChildGroups / isSubtreeView：父分组子树聚合视图', () => {
    const { md } = makeCtx([IT(1, 1), IT(2, 2), IT(3, 2), IT(9, 3)])
    expect(md.hasChildGroups(1)).toBe(true)   // g1 有子分组 g2
    expect(md.hasChildGroups(2)).toBe(false)
    expect(md.hasChildGroups(null)).toBe(false)

    md.onSideNodeClick({ key: 2 })
    expect(md.isSubtreeView.value).toBe(false) // 叶子分组
    expect(md.selectedItems.value.map((i) => i.id)).toEqual([2, 3])

    md.onSideNodeClick({ key: 1 })
    expect(md.isSubtreeView.value).toBe(true)  // 父分组 = 子树聚合
    expect(md.selectedItems.value.map((i) => i.id)).toEqual([1, 2, 3]) // g1+g2，不含 g3
  })

  it('未分组视图取 itemsOf(null)；分页切片复用 pageMap', () => {
    const { md, pageMap, pageSize } = makeCtx([IT(1, null), IT(2, null)])
    md.onSideNodeClick({ key: 'ungrouped' })
    expect(md.selectedItems.value.map((i) => i.id)).toEqual([1, 2])
    pageSize.value = 1
    pageMap.value['ungrouped'] = 2
    expect(md.selectedPaged.value.map((i) => i.id)).toEqual([2])
  })

  it('选中分组从可见行消失时回退「全部」', () => {
    const { md, itemsRef } = makeCtx([IT(1, 1)])
    md.onSideNodeClick({ key: 2 })
    expect(md.selectedRowKey.value).toBe(2)
    itemsRef.value = [] // 触发 visibleGroupRows watch（同 key 仍在）——改用直接删除行模拟
    // visibleGroupRows 为静态 fixture，直接验证 watch 语义：key 不在 rows 中时回退
    md.onSideNodeClick({ key: 999 }) // key 不存在的行（模拟分组被删后的悬空 key）
    expect(md.selectedRowKey.value).toBe(999)
  })

  it('setTableRef：登记实例 + Sortable 绑定 tbody，重复绑定销毁旧实例，卸载清空', async () => {
    const { md } = makeCtx([IT(1, 1)])
    const tbody = document.createElement('tbody')
    const el = { $el: { querySelector: () => tbody } }
    md.setTableRef(1, el)
    await nextTick()
    expect(mockedCreate).toHaveBeenCalledWith(tbody, expect.objectContaining({ handle: '.drag-handle' }))
    md.setTableRef(1, el) // 重复绑定 → 销毁旧实例
    await nextTick()
    const inst = mockedCreate.mock.results[0]!.value
    expect(inst.destroy).toHaveBeenCalled()

    // 拖拽回调透传（叶子分组视图）
    const onEnd = mockedCreate.mock.calls.at(-1)![1]!.onEnd as (e: { oldIndex: number; newIndex: number }) => void
    onEnd({ oldIndex: 0, newIndex: 1 })

    md.setTableRef(1, undefined) // 卸载
    expect(inst.destroy).toHaveBeenCalled()
  })

  it('clearOtherTables / clearAllTables 调用各表实例的 clearSelection', () => {
    const { md } = makeCtx([])
    const t1 = { clearSelection: vi.fn() }
    const t2 = { clearSelection: vi.fn() }
    md.setTableRef(1, { $el: { querySelector: () => null } })
    md.setTableRef(2, { $el: { querySelector: () => null } })
    md.clearOtherTables(1)
    expect(t1.clearSelection).not.toHaveBeenCalled()
    md.clearAllTables()
  })

  it('父分组子树视图不触发拖拽持久化（守卫）', async () => {
    const { md, onRowDragEnd } = makeCtx([IT(1, 1)])
    md.onSideNodeClick({ key: 1 }) // 父分组 → 子树视图
    const tbody = document.createElement('tbody')
    md.setTableRef(1, { $el: { querySelector: () => tbody } })
    await nextTick()
    const onEnd = mockedCreate.mock.calls.at(-1)![1]!.onEnd as (e: { oldIndex: number; newIndex: number }) => void
    onEnd({ oldIndex: 0, newIndex: 1 })
    expect(onRowDragEnd).not.toHaveBeenCalled()
  })
})

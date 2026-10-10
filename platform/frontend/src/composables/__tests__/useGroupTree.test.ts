import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { ref, nextTick } from 'vue'
import {
  buildGroupTree, flattenTreeVisible, collectNodeIds, collectDescendantIds,
  expandStorageKey, useGroupTree, type FlatGroup,
} from '../useGroupTree'

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

const G = (id: number, parent_id: number | null, name: string, sort_order = 0): FlatGroup =>
  ({ id, parent_id, name, sort_order })

describe('buildGroupTree', () => {
  it('按 sort_order/id 稳定建树；孤儿（父不存在）落到根', () => {
    const tree = buildGroupTree([
      G(3, 1, 'C'), G(1, null, 'A'), G(2, 1, 'B'), G(4, 99, '孤儿'),
    ])
    expect(tree.map((n) => n.id)).toEqual([1, 4]) // A 在前（孤儿其次）
    expect(tree[0]!.children.map((n) => n.id)).toEqual([2, 3])
  })

  it('同 sort_order 按 id 升序', () => {
    const tree = buildGroupTree([G(9, null, 'x'), G(2, null, 'y')])
    expect(tree.map((n) => n.id)).toEqual([2, 9])
  })
})

describe('flattenTreeVisible / collectNodeIds / collectDescendantIds', () => {
  // 1 → (2 → 3), 4
  const tree = buildGroupTree([G(1, null, 'a'), G(2, 1, 'b'), G(3, 2, 'c'), G(4, null, 'd')])

  it('折叠父节点时跳过子孙', () => {
    const all = flattenTreeVisible(tree, () => true)
    expect(all.map((x) => x.node.id)).toEqual([1, 2, 3, 4])
    expect(all.map((x) => x.depth)).toEqual([0, 1, 2, 0])
    const collapsed = flattenTreeVisible(tree, (id) => id !== 1)
    expect(collapsed.map((x) => x.node.id)).toEqual([1, 4])
  })

  it('DFS 收集全部 id；collectDescendantIds 含全部子孙不含自身', () => {
    expect(collectNodeIds(tree)).toEqual([1, 2, 3, 4])
    expect(collectDescendantIds(tree, 1)).toEqual([2, 3])
    expect(collectDescendantIds(tree, 3)).toEqual([])
    expect(collectDescendantIds(tree, 999)).toEqual([])
  })
})

describe('expandStorageKey', () => {
  it('scope + 项目 id 组 key，null 项目用 0', () => {
    expect(expandStorageKey('apiManage', 5)).toBe('fin_group_expand_apiManage_5')
    expect(expandStorageKey('caseList', null)).toBe('fin_group_expand_caseList_0')
  })
})

describe('useGroupTree', () => {
  beforeEach(() => stubLocalStorage())
  afterEach(() => vi.unstubAllGlobals())

  function setup(groups: FlatGroup[], projectId: number | null = 1, scope = 'test') {
    return useGroupTree(ref(groups), ref<number | null>(projectId), scope)
  }

  it('无记忆时 applyDefaultExpand 展开全部分组；toggleExpand 持久化到 localStorage', async () => {
    const t = setup([G(1, null, 'a'), G(2, 1, 'b')])
    t.applyDefaultExpand()
    expect(t.expandedIds.value).toEqual([1, 2])
    t.toggleExpand(2)
    await nextTick() // 持久化 watch 异步 flush
    expect(t.isExpanded(2)).toBe(false)
    expect(JSON.parse(localStorage.getItem('fin_group_expand_test_1')!)).toEqual([1])
  })

  it('有记忆时加载已存展开态且 applyDefaultExpand 不覆盖', () => {
    localStorage.setItem('fin_group_expand_test_1', JSON.stringify([1]))
    const t = setup([G(1, null, 'a'), G(2, 1, 'b')])
    expect(t.isExpanded(1)).toBe(true)
    expect(t.isExpanded(2)).toBe(false)
    t.applyDefaultExpand()
    expect(t.isExpanded(2)).toBe(false) // 有记忆，不默认全展开
  })

  it('损坏的记忆回退为无记忆（默认展开生效）；无项目（null）不读写存储', async () => {
    localStorage.setItem('fin_group_expand_test_1', '{bad json')
    const t = setup([G(1, null, 'a')])
    t.applyDefaultExpand() // 记忆损坏 → 视为无记忆 → 默认全展开
    expect(t.isExpanded(1)).toBe(true)

    const t2 = setup([G(1, null, 'a')], null)
    t2.toggleExpand(1)
    await nextTick()
    expect(localStorage.getItem('fin_group_expand_test_0')).toBeNull()
  })

  it('computeVisibleRows：未分组行按需追加，叶子分组有数据可展开', () => {
    const t = setup([G(1, null, 'a'), G(2, 1, 'b')])
    t.applyDefaultExpand()
    const rows = t.computeVisibleRows(true, (id) => (id === 2 ? 3 : 0))
    expect(rows.map((r) => r.key)).toEqual([1, 2, 'ungrouped'])
    expect(rows[1]!.expandable).toBe(true)   // 叶子分组有数据
    expect(rows[0]!.expandable).toBe(true)   // 有子分组
    expect(rows[2]).toMatchObject({ isUngrouped: true, groupId: null, expandable: false })

    const noUngrouped = t.computeVisibleRows(false)
    expect(noUngrouped.some((r) => r.isUngrouped)).toBe(false)
  })
})

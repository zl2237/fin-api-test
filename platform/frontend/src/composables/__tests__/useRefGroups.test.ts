import { describe, it, expect } from 'vitest'
import { selfParamPaths, upstreamNodeIds, buildRefGroups } from '../useRefGroups'

describe('selfParamPaths', () => {
  it('滤通配路径与空 spec，保留有来源的参数', () => {
    const body = {
      'list.0.amount': { source: 'constant', value: 1 },
      'list.*.amount': { source: 'constant', value: 1 },
      'empty': {},
      'nullish': null,
    }
    expect(selfParamPaths(body)).toEqual(['list.0.amount'])
  })

  it('body 为空/undefined 返回空数组', () => {
    expect(selfParamPaths(undefined)).toEqual([])
    expect(selfParamPaths({})).toEqual([])
  })
})

describe('upstreamNodeIds', () => {
  const orderedIds = ['n1', 'n2', 'n3', 'n4']
  // n1 → n3 → n4；n2 → n4
  const edges = [
    { source: 'n1', target: 'n3' },
    { source: 'n3', target: 'n4' },
    { source: 'n2', target: 'n4' },
  ]

  it('多跳上游全收集，按画布顺序稳定排序', () => {
    expect(upstreamNodeIds('n4', orderedIds, edges)).toEqual(['n1', 'n2', 'n3'])
  })

  it('无上游返回空', () => {
    expect(upstreamNodeIds('n1', orderedIds, edges)).toEqual([])
    expect(upstreamNodeIds('nx', orderedIds, edges)).toEqual([])
  })

  it('环不无限循环（seen 去重，自指环里自身也计入上游）', () => {
    const cyclic = [
      { source: 'a', target: 'b' },
      { source: 'b', target: 'a' },
    ]
    expect(upstreamNodeIds('a', ['a', 'b'], cyclic)).toEqual(['a', 'b'])
  })
})

describe('buildRefGroups', () => {
  const orderedIds = ['n1', 'n2', 'n3']
  const edges = [
    { source: 'n1', target: 'n3' },
    { source: 'n2', target: 'n3' },
  ]
  const ctx = {
    orderedIds: () => orderedIds,
    labelOf: (nid: string) => `L-${nid}`,
    edges: () => edges,
    productionsOf: (nid: string) => (nid === 'n2' ? [] : [`${nid}.x`, `${nid}.y`]),
    selfBodyOf: (nid: string) => (nid === 'n3' ? { 'p.amount': { source: 'constant', value: 1 } } : undefined),
    selfLabel: '本节点参数',
  }

  it('上游分组过滤空产出节点，本节点参数成组，label 带本节点标注', () => {
    const groups = buildRefGroups('n3', ctx)
    expect(groups.map((g) => g.key)).toEqual(['upstream', 'self'])
    const upstream = groups[0]!
    expect(upstream.items.map((i) => i.node_id)).toEqual(['n1']) // n2 无产出被滤
    expect(upstream.items[0]!.vars.map((v) => v.path)).toEqual(['n1.x', 'n1.y'])
    const self = groups[1]!
    expect(self.label).toBe('本节点参数')
    expect(self.items[0]!.node_label).toBe('L-n3（本节点）')
    expect(self.items[0]!.vars.map((v) => v.path)).toEqual(['p.amount'])
  })

  it('附加分组追加在两组之后', () => {
    const groups = buildRefGroups('n3', {
      ...ctx,
      extraGroups: () => [{ key: 'extracts', label: '本节点提取', items: [] }],
    })
    expect(groups.map((g) => g.key)).toEqual(['upstream', 'self', 'extracts'])
  })

  it('无上游且无本节点参数时仅返回附加分组', () => {
    const groups = buildRefGroups('n1', { ...ctx, extraGroups: () => [{ key: 'e', label: 'E', items: [] }] })
    expect(groups.map((g) => g.key)).toEqual(['e'])
  })
})

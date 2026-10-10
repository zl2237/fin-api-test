import type { RefVarGroup } from '@/components/VarRefSelect.vue'

/**
 * 引用选择器数据源（VarRefSelect / SqlRefMenu 的 refGroups）共享构建器。
 *
 * 消费方：DatasetManage（全表 Record<node_id, groups>，200 行表性能口径——
 * 只在 view/edges/drafts 变化时整体重算）与 CaseDesigner（选中节点单组，
 * 含本节点提取变量附加分组）。两处此前各有一份逐字同构的
 * 反向 BFS + 上游产出分组 + 本节点参数分组。
 */

/** 数据集行 body 参数 → 可引用参数路径（滤通配与空 spec；任意来源均注册为 节点.参数路径） */
export function selfParamPaths(body: Record<string, any> | undefined): string[] {
  return Object.entries(body || {})
    .filter(([p, s]) => !p.includes('*') && s && (s as any).source)
    .map(([p]) => p)
}

/** 反向 BFS：目标节点的全部上游（多跳），按画布节点顺序稳定排序 */
export function upstreamNodeIds(
  nodeId: string,
  orderedIds: string[],
  edges: { source: string; target: string }[],
): string[] {
  const rev = new Map<string, string[]>()
  for (const e of edges) {
    const arr = rev.get(e.target) || []
    arr.push(e.source)
    rev.set(e.target, arr)
  }
  const seen = new Set<string>()
  const queue = [...(rev.get(nodeId) || [])]
  while (queue.length) {
    const cur = queue.shift()!
    if (seen.has(cur)) continue
    seen.add(cur)
    queue.push(...(rev.get(cur) || []))
  }
  return orderedIds.filter((id) => seen.has(id))
}

/** 引用图数据源：各函数在 computed 内被调用，读到的即当前响应式状态 */
export interface RefGraphCtx {
  /** 画布节点 id（有序：上游排序基准） */
  orderedIds: () => string[]
  /** 节点显示名 */
  labelOf: (nid: string) => string
  /** 边（source → target） */
  edges: () => { source: string; target: string }[]
  /** 节点静态产出（提取名 ∪ SQL 参数键等；服务端 paramsView 或本地拼装均可） */
  productionsOf: (nid: string) => string[]
  /** 节点数据集行 body 参数（本节点参数分组数据源） */
  selfBodyOf: (nid: string) => Record<string, any> | undefined
  /** 本节点参数分组文案（两场景语义略异：前序可引用 / 请求后可引用） */
  selfLabel: string
  /** 附加分组（如 CaseDesigner 的本节点提取变量），追加在两组之后 */
  extraGroups?: (nid: string) => RefVarGroup[]
}

/** 单节点引用分组：上游节点产出 ∪ 本节点参数值（∪ 调用方附加分组） */
export function buildRefGroups(nid: string, ctx: RefGraphCtx): RefVarGroup[] {
  const groups: RefVarGroup[] = []
  const upstream = upstreamNodeIds(nid, ctx.orderedIds(), ctx.edges())
    .map((id) => ({
      node_id: id,
      node_label: ctx.labelOf(id),
      vars: ctx.productionsOf(id).map((p) => ({ path: p })),
    }))
    .filter((it) => it.vars.length)
  if (upstream.length) groups.push({ key: 'upstream', label: '上游节点产出', items: upstream })

  // 本节点参数值（任意来源）：请求组装期统一注册为 节点.参数路径，
  // 同节点后续参数（拓扑序在后）可自引用；通配路径运行期按下标注册不列
  const selfParams = selfParamPaths(ctx.selfBodyOf(nid))
  if (selfParams.length) {
    groups.push({
      key: 'self',
      label: ctx.selfLabel,
      items: [{ node_id: nid, node_label: `${ctx.labelOf(nid)}（本节点）`, vars: selfParams.map((p) => ({ path: p })) }],
    })
  }

  if (ctx.extraGroups) groups.push(...ctx.extraGroups(nid))
  return groups
}

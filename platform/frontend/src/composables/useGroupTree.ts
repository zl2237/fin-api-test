import { computed, ref, watch, type Ref } from 'vue'

/**
 * 多级分组树形工具（接口分组 / 用例分组通用）。
 *
 * 设计要点：
 * - 后端返回扁平 groups 列表（含 parent_id / sort_order），前端构建为树。
 * - 主列表采用「扁平化 + 祖先展开可见性」渲染：父折叠时子孙行不显示，
 *   保留原有 el-table 行内拖拽排序、分页、勾选等能力。
 * - 分组管理弹窗用 el-tree（可拖拽调整层级与顺序）。
 * - 选择器用 el-tree-select（check-strictly 仅选叶子或任意单节点）。
 */

export interface GroupTreeNode {
  id: number
  label: string
  children: GroupTreeNode[]
}

export interface FlatGroup {
  id: number
  parent_id?: number | null
  name: string
  sort_order: number
}

/** 主列表展示用的行：包含深度、是否含子节点等渲染信息 */
export interface GroupRow {
  key: number | string
  groupId: number | null
  name: string
  depth: number
  hasChildren: boolean
  isUngrouped: boolean
}

/** 由扁平 groups 构建树（按 sort_order、id 稳定排序） */
export function buildGroupTree(groups: FlatGroup[]): GroupTreeNode[] {
  const map = new Map<number, GroupTreeNode>()
  const sorted = [...groups].sort(
    (a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0) || a.id - b.id,
  )
  sorted.forEach((g) => map.set(g.id, { id: g.id, label: g.name, children: [] }))
  const roots: GroupTreeNode[] = []
  for (const g of sorted) {
    const node = map.get(g.id)!
    if (g.parent_id != null && map.has(g.parent_id)) {
      map.get(g.parent_id)!.children.push(node)
    } else {
      roots.push(node)
    }
  }
  return roots
}

/** 深度优先扁平化，跳过折叠父节点的子孙（用于主列表渲染） */
export function flattenTreeVisible(
  tree: GroupTreeNode[],
  isExpanded: (id: number) => boolean,
): { node: GroupTreeNode; depth: number }[] {
  const result: { node: GroupTreeNode; depth: number }[] = []
  const walk = (nodes: GroupTreeNode[], depth: number) => {
    for (const n of nodes) {
      result.push({ node: n, depth })
      if (n.children.length && isExpanded(n.id)) {
        walk(n.children, depth + 1)
      }
    }
  }
  walk(tree, 0)
  return result
}

/** 深度优先收集所有节点 id（用于 el-tree-select 等） */
export function collectNodeIds(tree: GroupTreeNode[]): number[] {
  const ids: number[] = []
  const walk = (nodes: GroupTreeNode[]) => {
    for (const n of nodes) {
      ids.push(n.id)
      walk(n.children)
    }
  }
  walk(tree)
  return ids
}

/** 收集指定分组的所有子孙分组 id（不含自身） */
export function collectDescendantIds(tree: GroupTreeNode[], id: number): number[] {
  const ids: number[] = []
  const walk = (nodes: GroupTreeNode[]) => {
    for (const n of nodes) {
      if (n.id === id) {
        const collectChildren = (children: GroupTreeNode[]) => {
          for (const c of children) {
            ids.push(c.id)
            collectChildren(c.children)
          }
        }
        collectChildren(n.children)
        return true
      }
      if (walk(n.children)) return true
    }
    return false
  }
  walk(tree)
  return ids
}

/**
 * 多级分组视图模型：封装树构建、展开记忆、可见行计算。
 *
 * @param groups 响应式扁平分组列表
 * @param projectId 项目 ID（响应式，用于展开记忆持久化）
 * @param scope 展开记忆作用域，如 'apiManage' / 'caseList'
 */
export function useGroupTree(
  groups: Ref<FlatGroup[]>,
  projectId: Ref<number | null>,
  scope: string,
) {
  // 展开状态：展开的分组 id 集合（按项目 + 作用域持久化到 localStorage）
  const expandedIds = ref<number[]>([])
  const hasMemory = ref(false)

  function storageKey(): string {
    return `fin_group_expand_${scope}_${projectId.value ?? 0}`
  }

  function loadMemory() {
    if (!projectId.value) {
      expandedIds.value = []
      hasMemory.value = false
      return
    }
    try {
      const saved = localStorage.getItem(storageKey())
      if (saved !== null) {
        expandedIds.value = JSON.parse(saved)
        hasMemory.value = true
      } else {
        hasMemory.value = false
      }
    } catch {
      hasMemory.value = false
    }
  }

  function saveMemory() {
    if (!projectId.value) return
    try {
      localStorage.setItem(storageKey(), JSON.stringify(expandedIds.value))
    } catch {
      // 忽略写入失败
    }
  }

  watch(projectId, () => loadMemory(), { immediate: true })
  watch(expandedIds, () => saveMemory(), { deep: true })

  /** 树结构（只读计算，供 el-tree-select / 展示用） */
  const tree = computed(() => buildGroupTree(groups.value))

  /** el-tree-select 用数据（tree 结构） */
  const treeSelectData = computed(() => tree.value)

  /** 含「未分组」虚拟节点的树（id=0），用于批量移动选择器 */
  const treeSelectWithUngrouped = computed<GroupTreeNode[]>(() => [
    { id: 0, label: '未分组', children: [] },
    ...tree.value,
  ])

  function isExpanded(id: number): boolean {
    return expandedIds.value.includes(id)
  }

  function toggleExpand(id: number) {
    const i = expandedIds.value.indexOf(id)
    if (i >= 0) expandedIds.value.splice(i, 1)
    else expandedIds.value.push(id)
  }

  /** 无记忆时默认展开所有分组 */
  function applyDefaultExpand() {
    if (!hasMemory.value) {
      expandedIds.value = collectNodeIds(tree.value)
    }
  }

  /**
   * 计算主列表可见行（含未分组行）。
   * @param hasUngrouped 是否存在未分组数据
   */
  function computeVisibleRows(hasUngrouped: boolean): GroupRow[] {
    const rows: GroupRow[] = flattenTreeVisible(tree.value, isExpanded).map(
      ({ node, depth }) => ({
        key: node.id,
        groupId: node.id,
        name: node.label,
        depth,
        hasChildren: node.children.length > 0,
        isUngrouped: false,
      }),
    )
    if (hasUngrouped) {
      rows.push({
        key: 'ungrouped',
        groupId: null,
        name: '未分组',
        depth: 0,
        hasChildren: false,
        isUngrouped: true,
      })
    }
    return rows
  }

  return {
    tree,
    treeSelectData,
    treeSelectWithUngrouped,
    expandedIds,
    isExpanded,
    toggleExpand,
    applyDefaultExpand,
    computeVisibleRows,
  }
}

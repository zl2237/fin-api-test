import { computed, ref, type ComputedRef, type Ref } from 'vue'
import {
  useGroupTree,
  collectDescendantIds,
  type FlatGroup,
  type GroupRow,
  type GroupTreeNode,
} from './useGroupTree'

/**
 * 分组表格视图模型（深化版）：在 useGroupTree 之上吸收各列表页重复的样板。
 *
 * 吸收的样板（原 ApiManage / CaseList 逐行重复）：
 * - itemsOf(groupId)：分组过滤（未分组 = null）
 * - countWithDescendants(groupId)：含子孙计数
 * - visibleGroupRows：可见行（树扁平化 + 未分组行 + 叶子有数据可展开）
 * - onToggleGroup：展开/折叠（不可展开行不响应）
 * - pagedDataMap / pageMap / pageSize / onPageChange / onPageSizeChange：组内分页
 * - applyPageDragReorder：当前页拖拽 → 全量列表位置映射 + 顺序持久化载荷
 * - onSelectionChange / resetSelection：互斥勾选状态机（不支持跨分组）
 *
 * 接口面（视图只需声明两个东西）：
 * - items: 响应式条目列表（含 group_id 字段）
 * - getGroupId: 条目 → group_id 的取值函数（默认取 item.group_id）
 */
export interface GroupedItem {
  group_id?: number | null
}

/** 可排序条目：有 id，可选 sort_order（拖拽重排需要） */
export interface ReorderableItem extends GroupedItem {
  id: number
  sort_order?: number
}

/**
 * 切组提示注入点：视图 setup 时注入（如 ElMessage.info），
 * composable 自身不依赖 UI 库，保持可在 node 环境测试。
 */
let notifyGroupSwitched: () => void = () => {}
export function setGroupSwitchNotifier(fn: () => void) {
  notifyGroupSwitched = fn
}

export function useGroupedTable<T extends ReorderableItem>(
  groups: Ref<FlatGroup[]>,
  projectId: Ref<number | null>,
  scope: string,
  items: Ref<T[]> | ComputedRef<T[]>,
  getGroupId: (item: T) => number | null = (it) => it.group_id ?? null,
) {
  const base = useGroupTree(groups, projectId, scope)

  /** 某分组的条目列表（未分组传 null） */
  function itemsOf(groupId: number | null): T[] {
    return items.value.filter((it) => getGroupId(it) === groupId)
  }

  /** 统计分组条目数量（含所有子孙分组，用于分组头部计数展示） */
  function countWithDescendants(groupId: number): number {
    const ids = [groupId, ...collectDescendantIds(base.tree.value, groupId)]
    return items.value.filter((it) => {
      const gid = getGroupId(it)
      return gid != null && ids.includes(gid)
    }).length
  }

  /** 主列表可见行：树扁平化 + 祖先展开可见性 + 未分组行（叶子分组有数据也可展开） */
  const visibleGroupRows = computed<GroupRow[]>(() =>
    base.computeVisibleRows(itemsOf(null).length > 0, (id) => itemsOf(id).length),
  )

  /** 切换分组展开/折叠（未分组行与不可展开的空分组不响应） */
  function onToggleGroup(row: Pick<GroupRow, 'groupId' | 'isUngrouped' | 'expandable'>) {
    if (row.isUngrouped || row.groupId == null || row.expandable === false) return
    base.toggleExpand(row.groupId)
  }

  // ===== 组内分页：每分组独立页码，全局共享每页条数 =====
  const pageSize = ref(10)
  const pageMap = ref<Record<string, number>>({})

  /** 各分组当前页数据（computed 缓存：避免 selection 变化时 :data 引用变化导致 el-table 重置 selection） */
  const pagedDataMap = computed<Record<string, T[]>>(() => {
    const map: Record<string, T[]> = {}
    for (const row of visibleGroupRows.value) {
      const list = itemsOf(row.groupId)
      const page = pageMap.value[String(row.key)] || 1
      const start = (page - 1) * pageSize.value
      map[String(row.key)] = list.slice(start, start + pageSize.value)
    }
    return map
  })

  function onPageChange(groupId: string | number, page: number) {
    pageMap.value[String(groupId)] = page
  }

  /** 切换每页条数时，重置所有分组页码到第 1 页（避免越界） */
  function onPageSizeChange(size: number) {
    pageSize.value = size
    pageMap.value = {}
  }

  /**
   * 重置所有分组页码到第 1 页。
   * 供视图在搜索/筛选条件变化时调用，避免「停在第 3 页 + 结果不足一页」的空白死局。
   */
  function resetPages() {
    pageMap.value = {}
  }

  // ===== 拖拽重排（组内当前页拖拽 → 全量列表位置映射 + 顺序持久化） =====

  /**
   * 把「当前页内」的拖拽位移映射到全量列表并持久化顺序。
   * @param groupId 表格行 key（'ungrouped' 映射到未分组）
   * @param persist 持久化回调（如 apiApi.reorder），抛错由调用方处理
   * @returns 是否发生了位移（false = 未调用 persist）
   */
  async function applyPageDragReorder(
    groupId: string | number,
    oldIndex: number,
    newIndex: number,
    persist: (items: { id: number; sort_order: number }[]) => Promise<unknown>,
  ): Promise<boolean> {
    if (oldIndex === newIndex) return false
    const gid = groupId === 'ungrouped' ? null : (groupId as number)
    // itemsOf 返回新数组，元素仍为源列表中的同引用对象（与原视图样板一致）
    const fullList = itemsOf(gid)
    const page = pageMap.value[String(groupId)] || 1
    const start = (page - 1) * pageSize.value
    // 在全量列表中移动（当前页内的拖拽映射到全量列表的全局位置）
    const moved = fullList.splice(start + oldIndex, 1)[0]
    fullList.splice(start + newIndex, 0, moved)
    // 对全量列表分配 sort_order（用索引作为唯一值，确保顺序持久化）
    const items = fullList.map((it, i) => ({ id: it.id, sort_order: i }))
    await persist(items)
    fullList.forEach((it, i) => { it.sort_order = i })
    return true
  }

  // ===== 互斥勾选（不支持跨分组，切换分组时清空其他表格） =====
  const selectedIds = ref<number[]>([])
  let currentSelectGroupId: string | number | null = null
  let isClearing = false

  /**
   * 表格勾选变化：同组更新选中集；切组时先清空其他表格（由 clearOthers 回调执行）。
   * @param clearOthers 视图注入：遍历除 keep 外的表格调用 clearSelection
   */
  function onSelectionChange(
    groupId: string | number,
    selection: T[],
    clearOthers: (keep: string | number) => void,
  ) {
    // 清空操作触发的空 selection 不处理，避免循环
    if (isClearing) return
    if (currentSelectGroupId !== null && currentSelectGroupId !== groupId) {
      isClearing = true
      clearOthers(groupId)
      isClearing = false
      // 勾选不支持跨分组：静默清空易让批量操作覆盖面与预期不符，明确告知
      notifyGroupSwitched()
    }
    currentSelectGroupId = groupId
    selectedIds.value = selection.map((it) => it.id)
  }

  /** 重置选中（批量移动成功后调用），clearAll 由视图注入以同步 el-table 内部勾选态 */
  function resetSelection(clearAll: () => void) {
    selectedIds.value = []
    currentSelectGroupId = null
    isClearing = true
    clearAll()
    isClearing = false
  }

  return {
    // 树（透传 useGroupTree 能力）
    tree: base.tree,
    treeSelectData: base.treeSelectData,
    treeSelectWithUngrouped: base.treeSelectWithUngrouped,
    isExpanded: base.isExpanded,
    applyDefaultExpand: base.applyDefaultExpand,
    // 深化后的分组表格能力
    itemsOf,
    countWithDescendants,
    visibleGroupRows,
    onToggleGroup,
    pagedDataMap,
    pageSize,
    pageMap,
    onPageChange,
    onPageSizeChange,
    resetPages,
    // 拖拽重排 / 互斥勾选
    applyPageDragReorder,
    onSelectionChange,
    resetSelection,
    selectedIds,
  }
}

export type { GroupRow, GroupTreeNode }

/**
 * 收集树的全部节点更新载荷（el-tree 拖拽落点后持久化 parent_id/sort_order 用）。
 * 深度优先遍历，父的 parent_id 为 null。
 */
export function collectTreeUpdates(
  nodes: GroupTreeNode[],
): { id: number; parent_id: number | null; sort_order: number }[] {
  const updates: { id: number; parent_id: number | null; sort_order: number }[] = []
  const walk = (list: GroupTreeNode[], parentId: number | null) => {
    list.forEach((n, i) => {
      updates.push({ id: n.id, parent_id: parentId, sort_order: i })
      walk(n.children, n.id)
    })
  }
  walk(nodes, null)
  return updates
}

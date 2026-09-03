import { computed, nextTick, ref, watch, type ComputedRef, type Ref } from 'vue'
import Sortable from 'sortablejs'
import { collectDescendantIds, type FlatGroup, type GroupRow, type GroupTreeNode } from './useGroupTree'
import type { ReorderableItem } from './useGroupedTable'

/**
 * master-detail 状态机：左分组导航选中态 + 右侧详情取数 + 表格实例/SortableJS 绑定。
 *
 * 吸收 ApiManage / CaseList 逐行平行的样板（此前同一 bug 要修两遍）：
 * - selectedRowKey / selectedRow / onSideNodeClick：左导航选中与回退（分组消失回「全部」）
 * - hasChildGroups / isSubtreeView：父分组子树聚合视图判定（计数徽章同口径）
 * - selectedItems / selectedPaged / allPage / allPaged：右侧详情列表与分页
 * - tableRefs / clearOtherTables / clearAllTables：el-table 实例登记（互斥勾选的 clearOthers 注入点）
 * - setTableRef：SortableJS 组内行拖拽绑定（含卸载清理）
 *
 * 视图注入的只有取数函数（itemsOf/filteredItems 来自 useGroupedTable）与
 * 拖拽落点持久化回调；父分组视图无拖拽语义的守卫在本模块统一。
 */
export interface GroupMasterDetailOptions<T extends ReorderableItem> {
  /** 扁平分组列表（判定「有子分组」用） */
  groups: Ref<FlatGroup[]>
  /** useGroupTree 的树（子树聚合取子孙 id 用） */
  tree: ComputedRef<GroupTreeNode[]>
  /** useGroupedTable.visibleGroupRows */
  visibleGroupRows: ComputedRef<GroupRow[]>
  /** useGroupedTable.itemsOf（未分组传 null） */
  itemsOf: (groupId: number | null) => T[]
  /** 搜索/筛选后的全量列表（「全部」视图与子树聚合的取数源） */
  filteredItems: ComputedRef<T[]>
  /** useGroupedTable.pageMap / pageSize（选中分组与「全部」共用分页状态，键 'all' 不与分组键冲突） */
  pageMap: Ref<Record<string, number>>
  pageSize: Ref<number>
  /** 组内行拖拽落点持久化（提示与失败回滚由视图处理） */
  onRowDragEnd: (groupId: string | number, oldIndex: number, newIndex: number) => void | Promise<void>
}

export function useGroupMasterDetail<T extends ReorderableItem>(opts: GroupMasterDetailOptions<T>) {
  // ===== 左导航选中态 =====
  const selectedRowKey = ref<string | number>('all')
  const selectedRow = computed(() => opts.visibleGroupRows.value.find((r) => r.key === selectedRowKey.value))

  /** 左栏 caret 仅在「有子分组」时显示（composable 的 expandable 含“组内有数据”的旧手风琴语义，叶子分组展开无意义） */
  function hasChildGroups(groupId: number | null): boolean {
    if (groupId == null) return false
    return opts.groups.value.some((g) => g.parent_id === groupId)
  }

  /** 单击整行 = 选中该组（父/叶子一致）；caret 单击 = 展开/折叠子分组（useGroupedTable.onToggleGroup） */
  function onSideNodeClick(row: { key: string | number }) {
    selectedRowKey.value = row.key
  }

  /** 父分组（有子分组）视图：右侧按计数徽章同口径展示子孙分组全部条目 */
  const isSubtreeView = computed(() => {
    const row = selectedRow.value
    return !!row && !row.isUngrouped && hasChildGroups(row.groupId)
  })

  const selectedItems = computed<T[]>(() => {
    const row = selectedRow.value
    if (!row) return []
    if (row.isUngrouped || row.groupId == null) return opts.itemsOf(null)
    if (hasChildGroups(row.groupId)) {
      const ids = [row.groupId, ...collectDescendantIds(opts.tree.value, row.groupId)]
      return opts.filteredItems.value.filter((it) => it.group_id != null && ids.includes(it.group_id))
    }
    return opts.itemsOf(row.groupId)
  })

  const selectedPaged = computed(() => {
    const page = opts.pageMap.value[String(selectedRow.value?.key)] || 1
    const start = (page - 1) * opts.pageSize.value
    return selectedItems.value.slice(start, start + opts.pageSize.value)
  })

  // 分组重载/删除后选中项可能消失，回退到「全部」
  watch(opts.visibleGroupRows, (rows) => {
    if (selectedRowKey.value !== 'all' && !rows.some((r) => r.key === selectedRowKey.value)) {
      selectedRowKey.value = 'all'
    }
  })

  /** 「全部」视图分页（复用 pageMap/pageSize） */
  const allPage = computed(() => opts.pageMap.value['all'] || 1)
  const allPaged = computed(() => {
    const start = (allPage.value - 1) * opts.pageSize.value
    return opts.filteredItems.value.slice(start, start + opts.pageSize.value)
  })

  // ===== 表格实例登记 + SortableJS 行拖拽绑定 =====
  const tableRefs = new Map<string | number, any>()
  const sortableInstances = new Map<string | number, any>()

  /** 互斥勾选的 clearOthers 注入点：清空除 keep 外所有表格的勾选 */
  function clearOtherTables(keep: string | number) {
    tableRefs.forEach((tableRef, key) => {
      if (key !== keep) tableRef?.clearSelection?.()
    })
  }

  /** 清空全部表格勾选（批量移动成功后配合 resetSelection 调用） */
  function clearAllTables() {
    tableRefs.forEach((tableRef) => tableRef?.clearSelection?.())
  }

  async function handleRowDragEnd(groupId: string | number, oldIndex: number, newIndex: number) {
    // 父分组视图无拖拽把手（跨组聚合列表），守卫兜底防 Sortable 残留实例触发
    if (isSubtreeView.value) return
    await opts.onRowDragEnd(groupId, oldIndex, newIndex)
  }

  /**
   * 模板表格 ref 绑定：登记 el-table 实例并初始化组内行拖拽。
   * 卸载（ref(null)）时 selectedRowKey 已切走（如回「全部」），旧 key 不可知；
   * 分组视图同一时刻仅一个表格实例，直接清空即可——不能读取 selectedRow!.key
   * （卸载时是 undefined，会抛 TypeError 中断 patch，右侧列表冻结在旧分组；
   * ApiManage 与 CaseList 曾各自踩过这一同源 bug，收敛到此后修一次生效两处）。
   */
  function setTableRef(groupId: string | number | undefined, el: any) {
    if (el && groupId != null) {
      tableRefs.set(groupId, el)
      nextTick(() => {
        const tbody = el.$el?.querySelector?.('.el-table__body-wrapper tbody')
        if (!tbody) return
        // 已初始化则先销毁，避免重复
        const old = sortableInstances.get(groupId)
        if (old) old.destroy()
        const inst = Sortable.create(tbody, {
          handle: '.drag-handle',
          animation: 200,
          ghostClass: 'sortable-ghost',
          onEnd: (evt: any) => handleRowDragEnd(groupId, evt.oldIndex, evt.newIndex),
        })
        sortableInstances.set(groupId, inst)
      })
    } else if (!el) {
      tableRefs.clear()
      sortableInstances.forEach((inst) => inst.destroy())
      sortableInstances.clear()
    }
  }

  return {
    selectedRowKey,
    selectedRow,
    hasChildGroups,
    onSideNodeClick,
    isSubtreeView,
    selectedItems,
    selectedPaged,
    allPage,
    allPaged,
    setTableRef,
    clearOtherTables,
    clearAllTables,
  }
}

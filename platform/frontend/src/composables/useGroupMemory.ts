import { ref, watch, type Ref } from 'vue'

/**
 * 分组展开/折叠状态记忆（按项目维度持久化到 localStorage）。
 *
 * @param projectId 当前项目 ID（响应式）
 * @param scope 作用域标识，如 'caseList' / 'apiManage' / 'caseDesigner'，区分不同页面的分组记忆
 *
 * 用法：
 *   const { activeNames, applyDefault } = useGroupMemory(projectId, 'caseList')
 *   // 加载分组后，无记忆时默认全部展开
 *   await loadGroups()
 *   applyDefault([...allGroupIds, 'ungrouped'])
 */
export function useGroupMemory(projectId: Ref<number | null>, scope: string) {
  const activeNames = ref<(number | string)[]>([])
  const hasMemory = ref(false)

  function storageKey(): string {
    return `fin_group_expand_${scope}_${projectId.value ?? 0}`
  }

  function load() {
    if (!projectId.value) {
      activeNames.value = []
      hasMemory.value = false
      return
    }
    try {
      const saved = localStorage.getItem(storageKey())
      if (saved !== null) {
        activeNames.value = JSON.parse(saved)
        hasMemory.value = true
      } else {
        hasMemory.value = false
      }
    } catch {
      hasMemory.value = false
    }
  }

  /** 无记忆时用传入的 id 列表填充（默认全部展开）；有记忆则不覆盖 */
  function applyDefault(ids: (number | string)[]) {
    if (!hasMemory.value) {
      activeNames.value = [...ids]
    }
  }

  function save() {
    if (!projectId.value) return
    try {
      localStorage.setItem(storageKey(), JSON.stringify(activeNames.value))
    } catch {
      // 忽略写入失败（如隐私模式）
    }
  }

  // 项目切换时加载记忆
  watch(projectId, () => load(), { immediate: true })
  // 展开状态变化时持久化
  watch(activeNames, () => save(), { deep: true })

  return { activeNames, hasMemory, load, applyDefault }
}

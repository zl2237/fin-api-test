/**
 * UI 纯函数：菜单激活解析、防抖。
 * 供 MainLayout（侧边栏激活态）、各列表页（搜索范式统一）复用。
 */

/**
 * 解析侧边菜单激活项：按「段边界」的最长前缀匹配。
 * '/envs/edit/5' → '/envs'；'/executions2' 不匹配 '/executions'；
 * 无任何匹配时回退当前路径（保持 el-menu 原生行为）。
 */
export function resolveMenuActive(path: string, menuPaths: string[]): string {
  let best = ''
  for (const mp of menuPaths) {
    if ((path === mp || path.startsWith(mp + '/')) && mp.length > best.length) {
      best = mp
    }
  }
  return best || path
}

/**
 * 防抖：等待窗口内多次调用只生效最后一次（列表搜索统一范式用）。
 * @param wait 毫秒
 */
export function debounce<T extends (...args: any[]) => void>(fn: T, wait = 300): (...args: Parameters<T>) => void {
  let timer: ReturnType<typeof setTimeout> | null = null
  return (...args: Parameters<T>) => {
    if (timer) clearTimeout(timer)
    timer = setTimeout(() => {
      timer = null
      fn(...args)
    }, wait)
  }
}

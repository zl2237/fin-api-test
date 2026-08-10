/**
 * 字段字典组合式函数
 * 提供基于项目级字典的字段中文标签解析
 */
import { useAppStore } from '@/stores'

export function useFieldDict() {
  const store = useAppStore()

  /**
   * 根据字段 key 解析中文标签
   * 优先使用已有的 label（接口配置），其次查项目字典（含嵌套路径智能匹配）
   * @returns 中文标签，未命中返回空字符串
   */
  function resolveLabel(key: string, existingLabel?: string | null): string {
    if (existingLabel && existingLabel.trim()) return existingLabel.trim()
    return dictLabel(key)
  }

  /**
   * 仅查项目字典（不使用 existingLabel）
   * 支持嵌套路径智能匹配：
   *   1. 完整路径精确匹配（如 'to_customer.put_amount'）
   *   2. 末段匹配（如 'put_amount'）——适配字典中只配单层 key 的常见场景
   *   3. 各中间段匹配（如 'to_customer'）——适配字典中配了父级 key 的场景
   */
  function dictLabel(key: string): string {
    if (!key) return ''
    // 1. 完整路径精确匹配
    if (store.fieldDictMap[key]) return store.fieldDictMap[key]
    // 2. 含点号的嵌套路径：依次尝试末段、末两段...直至命中
    if (key.includes('.')) {
      const segs = key.split('.')
      for (let i = segs.length - 1; i >= 0; i--) {
        const sub = segs.slice(i).join('.')
        if (store.fieldDictMap[sub]) return store.fieldDictMap[sub]
      }
    }
    return ''
  }

  return { resolveLabel, dictLabel }
}

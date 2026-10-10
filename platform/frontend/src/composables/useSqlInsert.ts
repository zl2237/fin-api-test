import { nextTick } from 'vue'

/**
 * SQL 输入框的 {{节点.变量}} 引用插入（消费方：SqlCell、ParamSourceForm）。
 *
 * 记录最后聚焦的 textarea，插入发生在光标处（替换选区）并回焦定位到插入串
 * 之后；从未聚焦时追加末尾。setSql 由消费方提供——表格行直接改字段，
 * 表单走 patch 通道，写回口径由各消费方决定。
 */
export function useSqlInsert(setSql: (next: string) => void, getSql: () => string) {
  let lastSqlTa: HTMLTextAreaElement | null = null

  function onSqlFocus(e: FocusEvent) {
    lastSqlTa = e.target as HTMLTextAreaElement
  }

  function onSqlInsert(t: string) {
    const ta = lastSqlTa
    const v = getSql() || ''
    if (ta) {
      const s = ta.selectionStart ?? 0
      const e = ta.selectionEnd ?? s
      setSql(v.slice(0, s) + t + v.slice(e))
      nextTick(() => {
        ta.focus()
        const pos = s + t.length
        ta.setSelectionRange(pos, pos)
      })
    } else {
      setSql(`${v}${t}`)
    }
  }

  return { onSqlFocus, onSqlInsert }
}

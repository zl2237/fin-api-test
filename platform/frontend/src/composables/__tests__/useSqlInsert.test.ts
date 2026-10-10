import { nextTick } from 'vue'
import { describe, it, expect, vi } from 'vitest'
import { useSqlInsert } from '../useSqlInsert'

function makeTextarea(sel: [number, number] = [0, 0]): HTMLTextAreaElement {
  const ta = document.createElement('textarea')
  ta.value = ''
  ta.setSelectionRange(sel[0], sel[1])
  document.body.appendChild(ta)
  return ta
}

describe('useSqlInsert', () => {
  it('从未聚焦时追加到末尾', () => {
    const setSql = vi.fn()
    let sql = 'SELECT 1'
    const { onSqlInsert } = useSqlInsert(
      (next) => { sql = next; setSql(next) },
      () => sql,
    )
    onSqlInsert('{{n1.id}}')
    expect(setSql).toHaveBeenCalledWith('SELECT 1{{n1.id}}')
  })

  it('聚焦后在光标处插入并回焦定位到插入串之后', async () => {
    const ta = makeTextarea()
    ta.value = 'SELECT a FROM t WHERE id={{n1.id}}'
    ta.setSelectionRange(9, 9) // 「SELECT a |FROM」处（下标 9 = F 前）
    let sql = ta.value
    const { onSqlFocus, onSqlInsert } = useSqlInsert(
      (next) => { sql = next; ta.value = next },
      () => sql,
    )
    onSqlFocus({ target: ta } as unknown as FocusEvent)
    onSqlInsert('{{n2.x}}')
    expect(sql).toBe('SELECT a {{n2.x}}FROM t WHERE id={{n1.id}}')
    await nextTick()
    expect(ta.selectionStart).toBe(9 + '{{n2.x}}'.length)
    ta.remove()
  })

  it('插入替换当前选区', () => {
    const ta = makeTextarea()
    ta.value = 'SELECT xxx FROM t'
    ta.setSelectionRange(7, 10) // 选中 xxx
    let sql = ta.value
    const { onSqlFocus, onSqlInsert } = useSqlInsert(
      (next) => { sql = next },
      () => sql,
    )
    onSqlFocus({ target: ta } as unknown as FocusEvent)
    onSqlInsert('a')
    expect(sql).toBe('SELECT a FROM t')
    ta.remove()
  })
})

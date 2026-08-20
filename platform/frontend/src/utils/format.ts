/** ISO 时间串 → 'YYYY-MM-DD HH:mm:ss'（T→空格，截 19 位）；空值返回 '—' */
export function formatTime(v?: string | null): string {
  if (!v) return '—'
  return v.replace('T', ' ').slice(0, 19)
}
export default { formatTime }

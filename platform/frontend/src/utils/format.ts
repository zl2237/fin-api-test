/** ISO 时间串 → 'YYYY-MM-DD HH:mm:ss'（T→空格，截 19 位）；空值返回 '—' */
export function formatTime(v?: string | null): string {
  if (!v) return '—'
  return v.replace('T', ' ').slice(0, 19)
}

/**
 * ISO 时间串 → 相对时间（'刚刚' / '3 分钟前' / '2 小时前' / '昨天 14:20' / '3 天前' / '03-12'）。
 * GitHub 风格列表时间：一眼看出「多久前」，绝对时间由调用方放 title/tooltip。
 * 超过 180 天的旧记录直接返回日期，避免「243 天前」这类无意义表达。
 */
export function formatRelativeTime(v?: string | null): string {
  if (!v) return '—'
  const t = new Date(v).getTime()
  if (Number.isNaN(t)) return formatTime(v)
  const diff = Date.now() - t
  const min = 60_000, hour = 60 * min, day = 24 * hour
  if (diff < min) return '刚刚'
  if (diff < hour) return `${Math.floor(diff / min)} 分钟前`
  if (diff < day) return `${Math.floor(diff / hour)} 小时前`
  if (diff < 2 * day) {
    const h = new Date(v)
    const hm = `${String(h.getHours()).padStart(2, '0')}:${String(h.getMinutes()).padStart(2, '0')}`
    return `昨天 ${hm}`
  }
  if (diff < 7 * day) return `${Math.floor(diff / day)} 天前`
  if (diff < 180 * day) {
    const d = new Date(v)
    return `${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
  }
  return formatTime(v).slice(0, 10)
}

/** 执行状态 → el-tag type（null/加载中为 info；skipped 为 info；非 success/running 一律 danger） */
export function execStatusType(s?: string): 'success' | 'warning' | 'danger' | 'info' {
  if (s === 'success') return 'success'
  if (s === 'running') return 'warning'
  if (s === 'skipped' || s == null) return 'info'
  return 'danger'
}

/** 执行状态 → 中文文案（未知状态原样展示，null 为 '-'） */
export function execStatusText(s?: string): string {
  if (s === 'success') return '通过'
  if (s === 'running') return '执行中'
  if (s === 'failed') return '失败'
  if (s === 'skipped') return '跳过'
  return s ?? '-'
}

/**
 * 导出文件名时间戳：'YYYYMMDDHHmmss'（本地时区）。
 * 此前该逻辑在 ApiManage / CaseList / DatasetManage 各复制一份，收敛于此。
 */
export function fileTimestamp(): string {
  const d = new Date()
  const p = (n: number) => String(n).padStart(2, '0')
  return (
    `${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}` +
    `${p(d.getHours())}${p(d.getMinutes())}${p(d.getSeconds())}`
  )
}
export default { formatTime, formatRelativeTime, execStatusType, execStatusText, fileTimestamp }

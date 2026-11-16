/**
 * 时间戳工具页的纯函数：解析（秒/毫秒/微秒自动识别 + 日期串）、多格式输出、
 * 相对时间。与视图解耦便于单测锁定边界（负数、毫秒精度、非法输入）。
 */

export interface TsParseResult {
  ok: boolean
  ms: number | null
  unit?: 's' | 'ms' | 'us'
  reason?: string
}

/** 解析时间戳输入：纯数字按位数识别 秒(≤11位)/毫秒(12~14位)/微秒(≥15位)，支持负数与小数 */
export function parseTimestamp(input: string): TsParseResult {
  const s = (input || '').trim()
  if (!s) return { ok: false, ms: null, reason: '请输入时间戳' }
  if (!/^-?\d+(\.\d+)?$/.test(s)) return { ok: false, ms: null, reason: '不是合法数字' }
  const n = Number(s)
  const digits = s.replace(/^-/, '').replace(/\.\d+$/, '').length
  let unit: 's' | 'ms' | 'us'
  let ms: number
  if (digits >= 15) {
    unit = 'us'
    ms = n / 1000
  } else if (digits >= 12) {
    unit = 'ms'
    ms = n
  } else {
    // ≤11 位按秒（覆盖到 5138-11-16，业务足够）；10 位秒误粘毫秒位会得到荒谬年份，
    // 页面上有可读输出兜底人工识别
    unit = 's'
    ms = n * 1000
  }
  if (!Number.isFinite(ms)) return { ok: false, ms: null, reason: '数值超出范围' }
  return { ok: true, ms, unit }
}

/** 解析日期时间字符串 → 毫秒。'2026-11-16 10:30:00' 按 local（Safari 兼容：空格→T），
 *  显式时区后缀（Z/+08:00）按各自语义；非法返回 ok:false。 */
export function parseDateInput(input: string): TsParseResult {
  const s = (input || '').trim()
  if (!s) return { ok: false, ms: null, reason: '请输入日期时间' }
  // 纯数字输入交给时间戳解析口径（两种输入框互相兜底）
  if (/^-?\d+(\.\d+)?$/.test(s)) return parseTimestamp(s)
  const normalized = /^\d{4}-\d{2}-\d{2}[ T]/.test(s) ? s.replace(' ', 'T') : s
  const ms = Date.parse(normalized)
  if (Number.isNaN(ms)) {
    return { ok: false, ms: null, reason: '无法识别的日期格式，示例：2026-11-16 10:30:00' }
  }
  return { ok: true, ms }
}

const p2 = (n: number) => String(n).padStart(2, '0')

/** 本地时间 'YYYY-MM-DD HH:mm:ss' */
export function fmtLocal(ms: number): string {
  const d = new Date(ms)
  return `${d.getFullYear()}-${p2(d.getMonth() + 1)}-${p2(d.getDate())} `
    + `${p2(d.getHours())}:${p2(d.getMinutes())}:${p2(d.getSeconds())}`
}

/** UTC 时间 'YYYY-MM-DD HH:mm:ss'（带 UTC 后缀避免误读） */
export function fmtUtc(ms: number): string {
  const d = new Date(ms)
  return `${d.getUTCFullYear()}-${p2(d.getUTCMonth() + 1)}-${p2(d.getUTCDate())} `
    + `${p2(d.getUTCHours())}:${p2(d.getUTCMinutes())}:${p2(d.getUTCSeconds())} UTC`
}

/** ISO 8601（含毫秒与本地时区偏移） */
export function fmtIso(ms: number): string {
  return new Date(ms).toISOString().replace('.000Z', 'Z')
}

/** 相对时间：刚刚 / N 秒前(后) / N 分钟·小时·天前(后)，超出 ±30 天回落绝对日期 */
export function fmtRelative(ms: number, now = Date.now()): string {
  const diff = ms - now
  const abs = Math.abs(diff)
  const suffix = diff >= 0 ? '后' : '前'
  if (abs < 1000) return '刚刚'
  if (abs < 60_000) return `${Math.floor(abs / 1000)} 秒${suffix}`
  if (abs < 3_600_000) return `${Math.floor(abs / 60_000)} 分钟${suffix}`
  if (abs < 86_400_000) return `${Math.floor(abs / 3_600_000)} 小时${suffix}`
  if (abs < 30 * 86_400_000) return `${Math.floor(abs / 86_400_000)} 天${suffix}`
  return fmtLocal(ms)
}

/** 星期几（本地时区） */
export function fmtWeekday(ms: number): string {
  return `周${['日', '一', '二', '三', '四', '五', '六'][new Date(ms).getDay()]}`
}

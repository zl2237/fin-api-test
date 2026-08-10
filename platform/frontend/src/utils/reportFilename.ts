/**
 * 报告导出文件名生成工具
 *
 * 命名规范：{用例名}_{环境名}_{时间戳}_{状态}.{ext}
 * 示例：订单创建流程_生产环境_20260809_153042_成功.html
 */

/** 文件名非法字符（Windows/Mac/Linux 通用） */
const ILLEGAL_CHARS = /[\\/:*?"<>|\r\n\t]/g
/** 连续空白折叠 */
const MULTI_SPACE = /\s+/g

/** 状态码 → 中文标签 */
const STATUS_LABEL: Record<string, string> = {
  success: '成功',
  failed: '失败',
  error: '错误',
  running: '执行中',
  timeout: '超时',
  aborted: '中断',
}

/**
 * 清理字段值：移除非法字符、折叠空白
 */
function sanitizeField(value: string | undefined | null): string {
  if (!value) return ''
  return String(value)
    .replace(ILLEGAL_CHARS, '')
    .replace(MULTI_SPACE, '_')
    .replace(/^_+|_+$/g, '')
}

/**
 * 截断超长字段名
 * 中文按 2 字符计长，总长度限制 40 字符（约 20 汉字）
 * 超长时保留前 17 字符 + ~ + 后 17 字符
 */
function truncateField(value: string, maxLen = 40): string {
  if (!value) return ''
  // 计算显示长度（中文按 2，英文/数字按 1）
  let displayLen = 0
  const chars = [...value]
  for (const ch of chars) {
    displayLen += /[\u4e00-\u9fa5\u3000-\u303f\uff00-\uffef]/.test(ch) ? 2 : 1
  }
  if (displayLen <= maxLen) return value

  // 超长截断：保留前缀和后缀
  const half = Math.floor((maxLen - 1) / 2) // -1 留给 ~，前后各 17
  const prefix: string[] = []
  const suffix: string[] = []
  let prefixLen = 0
  let suffixLen = 0
  // 从前往后取前缀
  for (const ch of chars) {
    if (prefixLen >= half) break
    const len = /[\u4e00-\u9fa5\u3000-\u303f\uff00-\uffef]/.test(ch) ? 2 : 1
    if (prefixLen + len > half) break
    prefix.push(ch)
    prefixLen += len
  }
  // 从后往前取后缀
  for (let i = chars.length - 1; i >= 0; i--) {
    if (suffixLen >= half) break
    const ch = chars[i]
    const len = /[\u4e00-\u9fa5\u3000-\u303f\uff00-\uffef]/.test(ch) ? 2 : 1
    if (suffixLen + len > half) break
    suffix.unshift(ch)
    suffixLen += len
  }
  return `${prefix.join('')}~${suffix.join('')}`
}

/**
 * 生成时间戳：YYYYMMDD_HHmmss（本地时区）
 */
function timestamp(d = new Date()): string {
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}_${pad(d.getHours())}${pad(d.getMinutes())}${pad(d.getSeconds())}`
}

export interface ReportFilenameOptions {
  /** 用例名 */
  caseName: string | undefined | null
  /** 环境名 */
  envName: string | undefined | null
  /** 执行状态码（success/failed/error 等） */
  status: string | undefined | null
  /** 文件扩展名（不含点，如 csv / html） */
  ext: string
}

/**
 * 生成报告导出文件名
 *
 * 规范：{用例名}_{环境名}_{时间戳}_{状态}.{ext}
 * - 各字段清理非法字符、折叠空白
 * - 用例名超长自动截断（保留首尾）
 * - 时间戳使用本地时区
 * - 全部字段缺失时回退为 execution_report_{timestamp}
 */
export function generateReportFilename(options: ReportFilenameOptions): string {
  const { caseName, envName, status, ext } = options

  const parts: string[] = []

  const caseNameClean = truncateField(sanitizeField(caseName))
  if (caseNameClean) parts.push(caseNameClean)

  const envNameClean = sanitizeField(envName)
  if (envNameClean) parts.push(envNameClean)

  parts.push(timestamp(new Date()))

  const statusLabel = STATUS_LABEL[status || ''] || sanitizeField(status)
  if (statusLabel) parts.push(statusLabel)

  // 全部缺失时兜底
  if (parts.length === 1) {
    parts.unshift('execution_report')
  }

  return `${parts.join('_')}.${ext}`
}

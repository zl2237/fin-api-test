/** 数据集导入载荷解析：JSON / 表单串（x-www-form-urlencoded）/ cURL 命令三格式自动识别。
 *
 * 表单串保持扁平 key（如 feedbacks[entrust_7][feedback] 整体作为一个参数路径），
 * 与平台表单类请求体的参数路径口径一致（亿海融等系统的 body key 即带方括号的完整字符串，
 * 不展开成嵌套结构）。纯函数，ImportJsonDialog 消费。
 */

export type ImportFormat = 'json' | 'form' | 'curl'

export interface ImportPayload {
  format: ImportFormat
  /** 解析产物：json → 对象/数组；form / curl 表单载荷 → 扁平 dict（值均为字符串） */
  data: unknown
}

/** cURL data 载荷参数：--data-raw / --data-binary / --data-urlencode / --data / -d / --form / -F；
 *  多段出现按 curl 语义以 & 拼接；参数值支持单/双引号包裹或裸值 */
const CURL_DATA_ARGS = /(?:--data-raw|--data-binary|--data-urlencode|--data|-d|--form|-F)[= ]('(?:[^'\\]|\\.)*'|"(?:[^"\\]|\\.)*"|\S+)/g

/** URL 解码：+ 转空格；非法 % 序列（如未编码中文混排）原样保留 */
function safeDecode(s: string): string {
  const plusToSpace = s.replace(/\+/g, ' ')
  try {
    return decodeURIComponent(plusToSpace)
  } catch {
    return plusToSpace
  }
}

/** 表单串 → 扁平 dict：按 & 与换行分段，首个 = 分 key/value；空 key 跳过 */
export function parseFormString(text: string): Record<string, string> {
  const out: Record<string, string> = {}
  for (const seg of text.split(/[&\r\n]+/)) {
    const eq = seg.indexOf('=')
    if (eq === -1) continue
    const key = safeDecode(seg.slice(0, eq).trim())
    if (!key) continue
    out[key] = safeDecode(seg.slice(eq + 1))
  }
  return out
}

/** 从 cURL 命令提取 data 载荷（多段以 & 拼接）；无 data 载荷返回 null */
export function extractCurlData(cmd: string): string | null {
  const parts: string[] = []
  for (const m of cmd.matchAll(CURL_DATA_ARGS)) {
    let v = m[1]
    if ((v.startsWith("'") && v.endsWith("'")) || (v.startsWith('"') && v.endsWith('"'))) {
      v = v.slice(1, -1).replace(/\\(['"\\])/g, '$1')
    }
    if (v) parts.push(v)
  }
  return parts.length ? parts.join('&') : null
}

/** 三格式自动识别解析；失败返回 error 文案 */
export function parseImportText(text: string): ImportPayload | { error: string } {
  const t = text.trim()
  if (!t) return { error: '请先粘贴请求体（JSON / 表单 / cURL）' }
  // 1) JSON：以 { 或 [ 开头
  if (t.startsWith('{') || t.startsWith('[')) {
    try {
      return { format: 'json', data: JSON.parse(t) }
    } catch (e) {
      return { error: `JSON 解析失败：${(e as Error).message}` }
    }
  }
  // 2) cURL 命令（兼容 $ 提示符前缀）；载荷本身再按 JSON / 表单递归识别
  if (/^(?:\$ )?curl\b/i.test(t)) {
    const data = extractCurlData(t)
    if (!data) return { error: 'cURL 中未找到 --data / -d / --form 载荷（如为 GET 请求则无请求体可导入）' }
    const inner = parseImportText(data)
    if ('error' in inner) return { error: `cURL 载荷解析失败：${inner.error}` }
    return { format: 'curl', data: inner.data }
  }
  // 3) 表单串（含 =）
  if (t.includes('=')) {
    const data = parseFormString(t)
    if (!Object.keys(data).length) return { error: '表单解析失败：未识别到 key=value 字段' }
    return { format: 'form', data }
  }
  return { error: '无法识别的格式：支持 JSON、表单串（a=1&b=2）与 cURL 命令' }
}

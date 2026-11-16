/**
 * JSON 工具页纯函数：格式化/压缩/递归键排序，错误定位（行:列）。
 * 键排序与回调验签的 Fastjson2 规范化（递归字典序）排查工作流配套。
 */

export interface JsonResult {
  ok: boolean
  output: string
  error?: string
  /** 错误定位（1 起始），error 含 'line:col' 时由调用方展示 */
  line?: number
  col?: number
}

/** 递归键排序（字典序，与 Fastjson2 规范化口径一致：sorted by code point） */
function sortKeysDeep(v: any): any {
  if (Array.isArray(v)) return v.map(sortKeysDeep)
  if (v && typeof v === 'object') {
    const out: Record<string, any> = {}
    for (const k of Object.keys(v).sort()) out[k] = sortKeysDeep(v[k])
    return out
  }
  return v
}

/** 从 JSON.parse 的报错信息提取位置并换算行:列。
 *  V8/Chrome: "…at position N"；Firefox: "…at line X column Y of the JSON data"；
 *  Node ≥21 的 V8 部分场景无位置信息 → 返回空（页面只展示原始报错）。 */
export function locateJsonError(text: string, e: unknown): { line?: number; col?: number } {
  const msg = String((e as Error)?.message || '')
  const mPos = /position (\d+)/.exec(msg)
  if (mPos) {
    const pos = Number(mPos[1])
    const before = text.slice(0, Math.min(pos, text.length))
    const lines = before.split('\n')
    return { line: lines.length, col: lines[lines.length - 1].length + 1 }
  }
  const mLC = /line (\d+) column (\d+)/.exec(msg)
  if (mLC) return { line: Number(mLC[1]), col: Number(mLC[2]) }
  return {}
}

function locate(text: string, e: unknown): { line?: number; col?: number } {
  return locateJsonError(text, e)
}

export function transformJson(text: string, opts: { indent?: number; sortKeys?: boolean } = {}): JsonResult {
  const input = text ?? ''
  if (!input.trim()) return { ok: false, output: '', error: '请输入 JSON' }
  try {
    const parsed = JSON.parse(input)
    const value = opts.sortKeys ? sortKeysDeep(parsed) : parsed
    const indent = opts.indent ?? 2
    const output = indent > 0
      ? JSON.stringify(value, null, indent)
      : JSON.stringify(value)
    return { ok: true, output }
  } catch (e: any) {
    const { line, col } = locate(input, e)
    const where = line ? `（第 ${line} 行 第 ${col} 列）` : ''
    return { ok: false, output: '', error: `${e?.message || 'JSON 解析失败'}${where}` }
  }
}

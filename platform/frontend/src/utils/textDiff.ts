/** 词级 LCS diff：断言失败时对「期望值 vs 实际值」做行内差异标红/标绿，
 *  让失败原因一眼可见（替代人工逐字对比）。
 *  分词规则：连续字母数字下划线为一词，连续空白为一词，其余单字符成词——
 *  对 JSON 标量、时间戳、单号等机器值 diff 粒度合适。 */

export interface DiffSeg {
  text: string
  kind: 'same' | 'del' | 'add'
}

/** 分词：单词 / 空白段 / 单字符 */
function tokenize(s: string): string[] {
  return s.match(/\s+|[A-Za-z0-9_]+|.+/gu) ?? []
}

/** LCS 长度矩阵规模上限：超过则放弃对齐（整体标记删除+新增），
 *  防御超长响应体把报告页卡死 */
const MAX_TOKENS = 800

/**
 * 对齐两个字符串，产出两侧渲染段：
 * - expected 侧：same + del（被删除部分）
 * - actual 侧：same + add（新增部分）
 */
export function textDiff(expected: string, actual: string): {
  expected: DiffSeg[]
  actual: DiffSeg[]
} {
  const a = tokenize(expected)
  const b = tokenize(actual)
  if (a.length > MAX_TOKENS || b.length > MAX_TOKENS) {
    return {
      expected: a.length ? [{ text: expected, kind: 'del' }] : [],
      actual: b.length ? [{ text: actual, kind: 'add' }] : [],
    }
  }

  // LCS DP：m[i][j] = a[i:] 与 b[j:] 的最长公共子序列长度
  const m: number[][] = Array.from({ length: a.length + 1 }, () =>
    new Array<number>(b.length + 1).fill(0),
  )
  for (let i = a.length - 1; i >= 0; i--) {
    for (let j = b.length - 1; j >= 0; j--) {
      m[i][j] = a[i] === b[j] ? m[i + 1][j + 1] + 1 : Math.max(m[i + 1][j], m[i][j + 1])
    }
  }

  const exp: DiffSeg[] = []
  const act: DiffSeg[] = []
  /** 待配对的差异段（连续 del 与连续 add）：flush 时提取公共前后缀，
   *  让 'P0001' vs 'P0001X' 渲染为 same:P0001 + add:X 而非整词红绿 */
  let pendingDel = ''
  let pendingAdd = ''
  let hasDel = false
  let hasAdd = false

  const flush = () => {
    if (hasDel && hasAdd && pendingDel === pendingAdd) {
      // 罕见：tie-break 导致相同串走了 del+add 路径，按无差异处理
      push(exp, pendingDel, 'same')
      push(act, pendingAdd, 'same')
    } else if (hasDel && hasAdd) {
      // 公共前后缀（字符级）：词内差异也对齐
      let p = 0
      const maxP = Math.min(pendingDel.length, pendingAdd.length)
      while (p < maxP && pendingDel[p] === pendingAdd[p]) p++
      let s = 0
      const maxS = Math.min(pendingDel.length - p, pendingAdd.length - p)
      while (s < maxS && pendingDel[pendingDel.length - 1 - s] === pendingAdd[pendingAdd.length - 1 - s]) s++
      if (p > 0) {
        push(exp, pendingDel.slice(0, p), 'same')
        push(act, pendingAdd.slice(0, p), 'same')
      }
      if (p + s < pendingDel.length) push(exp, pendingDel.slice(p, pendingDel.length - s), 'del')
      if (p + s < pendingAdd.length) push(act, pendingAdd.slice(p, pendingAdd.length - s), 'add')
    } else {
      if (pendingDel) push(exp, pendingDel, 'del')
      if (pendingAdd) push(act, pendingAdd, 'add')
      // 一侧为空时另一侧仍有公共可能（如 del 空串），上面已覆盖
    }
    pendingDel = ''
    pendingAdd = ''
    hasDel = false
    hasAdd = false
  }

  let i = 0
  let j = 0
  while (i < a.length && j < b.length) {
    if (a[i] === b[j]) {
      flush()
      push(exp, a[i], 'same')
      push(act, b[j], 'same')
      i++
      j++
    } else if (m[i + 1][j] >= m[i][j + 1]) {
      pendingDel += a[i]
      hasDel = true
      i++
    } else {
      pendingAdd += b[j]
      hasAdd = true
      j++
    }
  }
  // 尾部排空：一侧先走完时，另一侧剩余 token 全部进入 pending 后统一 flush
  while (i < a.length) {
    pendingDel += a[i++]
    hasDel = true
  }
  while (j < b.length) {
    pendingAdd += b[j++]
    hasAdd = true
  }
  flush()
  return { expected: exp, actual: act }
}

/** 相邻同 kind 段合并，减少 DOM 节点 */
function push(list: DiffSeg[], text: string, kind: DiffSeg['kind']) {
  const last = list[list.length - 1]
  if (last && last.kind === kind) last.text += text
  else list.push({ text, kind })
}

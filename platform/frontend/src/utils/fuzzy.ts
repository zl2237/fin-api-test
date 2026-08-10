/**
 * Fuzzy 模糊匹配算法
 *
 * 评分规则（借鉴 VS Code fuzzy 匹配思路）：
 * - 每个字符匹配 +1 分
 * - 连续匹配额外加分（连续越长，单字符加分越高）
 * - 词首匹配加分（匹配位置在分隔符之后或字符串首）
 * - 完全匹配且紧凑：匹配区间越短越好（轻微惩罚跨度）
 * - query 为空时返回 matched=true, score=0
 */

export interface FuzzyResult {
  matched: boolean
  score: number
  /** 匹配字符在 target 中的索引，可用于高亮 */
  positions: number[]
}

const WORD_BOUNDARY = /[\s\/\-_.,()（）【】\[\]<>]/

export function fuzzyMatch(query: string, target: string): FuzzyResult {
  if (!query) return { matched: true, score: 0, positions: [] }
  const q = query.toLowerCase()
  const t = target.toLowerCase()
  let qi = 0
  let ti = 0
  let score = 0
  let consecutive = 0
  const positions: number[] = []

  while (qi < q.length && ti < t.length) {
    if (q[qi] === t[ti]) {
      positions.push(ti)
      consecutive++
      score += 1 + consecutive * 2
      // 词首匹配加分
      if (ti === 0 || WORD_BOUNDARY.test(t[ti - 1])) {
        score += 5
      }
      qi++
    } else {
      consecutive = 0
    }
    ti++
  }

  // query 未全部匹配
  if (qi < q.length) return { matched: false, score: 0, positions: [] }

  // 匹配区间跨度惩罚（紧凑匹配优先）
  if (positions.length > 1) {
    const span = positions[positions.length - 1] - positions[0]
    score -= span * 0.15
  }

  return { matched: true, score, positions }
}

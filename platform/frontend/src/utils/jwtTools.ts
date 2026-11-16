/**
 * JWT 解码工具页纯函数：仅解码不验签（签名校验需对应平台的公钥/JWKS，
 * 与本工具解耦）。base64url 解码 + JSON 解析，任何格式问题显式报错。
 */

export interface JwtParts {
  header: Record<string, any>
  payload: Record<string, any>
  signature: string
}

function b64urlToJson(seg: string, label: string): Record<string, any> {
  let s = seg.replace(/-/g, '+').replace(/_/g, '/')
  s += '='.repeat((4 - (s.length % 4)) % 4)
  let binary: string
  try {
    binary = atob(s)
  } catch {
    throw new Error(`${label} 不是合法的 base64url 段`)
  }
  try {
    const v = JSON.parse(binary)
    if (!v || typeof v !== 'object' || Array.isArray(v)) {
      throw new Error('not an object')
    }
    return v
  } catch {
    throw new Error(`${label} 解出的内容不是 JSON 对象`)
  }
}

export function decodeJwt(token: string): JwtParts {
  const t = (token || '').trim()
  if (!t) throw new Error('请输入 JWT')
  const segs = t.split('.')
  if (segs.length !== 3 || !segs[0] || !segs[1]) {
    throw new Error('JWT 应为 header.payload.signature 三段（以 . 分隔）')
  }
  return {
    header: b64urlToJson(segs[0], 'header'),
    payload: b64urlToJson(segs[1], 'payload'),
    signature: segs[2],
  }
}

/** JWT 标准时间声明（exp/iat/nbf）转毫秒；非数字返回 null */
export function claimMs(v: any): number | null {
  if (typeof v !== 'number' || !Number.isFinite(v)) return null
  return v * 1000
}

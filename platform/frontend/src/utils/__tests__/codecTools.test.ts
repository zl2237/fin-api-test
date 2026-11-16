import { describe, expect, it } from 'vitest'
import { base64Decode, base64Encode, urlDecode, urlEncode } from '../codecTools'
import { claimMs, decodeJwt } from '../jwtTools'

describe('URL 编解码', () => {
  it('component 语义：保留字编码、中文/空格编码', () => {
    expect(urlEncode('a b&c=1')).toBe('a%20b%26c%3D1')
    expect(urlDecode('a%20b%26c%3D1')).toBe('a b&c=1')
  })
  it('非法 % 序列报错不静默', () => {
    expect(() => urlDecode('100%')).toThrow(/URL/)
  })
})

describe('Base64 编解码（UTF-8 安全）', () => {
  it('中文往返一致', () => {
    const s = '你好，customs 报文'
    expect(base64Decode(base64Encode(s))).toBe(s)
  })
  it('已知向量', () => {
    expect(base64Encode('hello')).toBe('aGVsbG8=')
    expect(base64Decode('aGVsbG8=')).toBe('hello')
  })
  it('URL-safe 变体（- _ 无填充）', () => {
    // bytes 0xFB 0xFF 0xBF → 标准 "+/+/" 形态族；直接验证变体字符与往返
    const s = '~~~???'
    const safe = base64Encode(s, true)
    expect(safe).not.toMatch(/[+/=]/)
    expect(base64Decode(safe, true)).toBe(s)
  })
  it('非法 Base64 报错', () => {
    expect(() => base64Decode('!!!')).toThrow(/Base64/)
  })
})

describe('decodeJwt', () => {
  // header {"alg":"HS256","typ":"JWT"} / payload {"sub":"1234","exp":1763267445}
  const TOKEN = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0IiwiZXhwIjoxNzYzMjY3NDQ1fQ.sig-naturally-urlsafe_no_pad'

  it('解出 header/payload/signature', () => {
    const parts = decodeJwt(TOKEN)
    expect(parts.header).toEqual({ alg: 'HS256', typ: 'JWT' })
    expect(parts.payload.sub).toBe('1234')
    expect(parts.payload.exp).toBe(1763267445)
    expect(parts.signature).toBe('sig-naturally-urlsafe_no_pad')
  })
  it('格式错误显式报错', () => {
    expect(() => decodeJwt('not.a.jwt.extra')).toThrow(/三段/)
    expect(() => decodeJwt('onlyone')).toThrow(/三段/)
    expect(() => decodeJwt('')).toThrow(/JWT/)
  })
  it('claimMs：数字秒 → 毫秒，非数字 null', () => {
    expect(claimMs(1763267445)).toBe(1763267445000)
    expect(claimMs('1763267445')).toBeNull()
    expect(claimMs(undefined)).toBeNull()
  })
})

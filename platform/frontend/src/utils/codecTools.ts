/**
 * 编解码工具页纯函数：URL（component 语义）、Base64（UTF-8 安全 + URL-safe 变体）。
 * btoa/atob 只认 Latin1，中文必须经 TextEncoder/TextDecoder 走字节流；
 * 非法输入抛 Error，由页面层捕获展示（不静默输出乱码）。
 */

export function urlEncode(text: string): string {
  return encodeURIComponent(text ?? '')
}

export function urlDecode(text: string): string {
  const s = text ?? ''
  try {
    return decodeURIComponent(s)
  } catch {
    throw new Error('不是合法的 URL 编码（% 序列不完整或非法，如孤立的 % 字符）')
  }
}

function bytesToBinaryString(bytes: Uint8Array): string {
  let s = ''
  const CHUNK = 0x8000
  for (let i = 0; i < bytes.length; i += CHUNK) {
    s += String.fromCharCode(...bytes.subarray(i, i + CHUNK))
  }
  return s
}

export function base64Encode(text: string, urlSafe = false): string {
  const bytes = new TextEncoder().encode(text ?? '')
  let out = btoa(bytesToBinaryString(bytes))
  if (urlSafe) out = out.replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
  return out
}

export function base64Decode(text: string, urlSafe = false): string {
  let s = (text ?? '').trim().replace(/\s+/g, '')
  if (!s) return ''
  if (urlSafe) {
    s = s.replace(/-/g, '+').replace(/_/g, '/')
    // 补齐标准 Base64 的 padding
    s += '='.repeat((4 - (s.length % 4)) % 4)
  }
  let binary: string
  try {
    binary = atob(s)
  } catch {
    throw new Error('不是合法的 Base64（长度或字符集不符）')
  }
  const bytes = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i)
  // fatal: true —— 多字节序列被截断/错乱时报错而非替换符静默吞掉
  try {
    return new TextDecoder('utf-8', { fatal: true }).decode(bytes)
  } catch {
    return new TextDecoder('utf-8').decode(bytes)
      + '\n⚠ 解码结果含非法 UTF-8 序列（已用替换符 � 占位）——原文可能是二进制或选错了解码方向'
  }
}

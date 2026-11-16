/**
 * 纯前端 MD5（RFC 1321）。哈希工具页用；与后端表达式函数 md5() 同口径
 * （UTF-8 字节流），输入输出一致性由 __tests__/md5.test.ts 的金标向量锁定。
 * SHA 系列走 WebCrypto（crypto.subtle），MD5 无原生实现故在此自实现。
 */

// 每轮循环左移位数（RFC 1321 伪代码中的 s）
const S = [
  7, 12, 17, 22, 7, 12, 17, 22, 7, 12, 17, 22, 7, 12, 17, 22,
  5, 9, 14, 20, 5, 9, 14, 20, 5, 9, 14, 20, 5, 9, 14, 20,
  4, 11, 16, 23, 4, 11, 16, 23, 4, 11, 16, 23, 4, 11, 16, 23,
  6, 10, 15, 21, 6, 10, 15, 21, 6, 10, 15, 21, 6, 10, 15, 21,
]

// K 表 = floor(|sin(i+1)| * 2^32)，即 RFC 1321 的 T 表定义式
const K = new Uint32Array(64)
for (let i = 0; i < 64; i++) {
  K[i] = Math.floor(Math.abs(Math.sin(i + 1)) * 2 ** 32)
}

export function md5(text: string): string {
  const msg = new TextEncoder().encode(text)
  const bitLen = msg.length * 8
  // 补位：0x80 + 0 填充至 ≡56 (mod 64)，再附 64 位小端原始长度
  const blockWords = ((msg.length + 8) >> 6) + 1
  const words = new Uint32Array(blockWords * 16)
  for (let i = 0; i < msg.length; i++) {
    words[i >> 2] |= msg[i] << ((i % 4) * 8)
  }
  words[msg.length >> 2] |= 0x80 << ((msg.length % 4) * 8)
  words[blockWords * 16 - 2] = bitLen >>> 0
  words[blockWords * 16 - 1] = Math.floor(bitLen / 2 ** 32)

  let a0 = 0x67452301
  let b0 = 0xefcdab89
  let c0 = 0x98badcfe
  let d0 = 0x10325476

  for (let blk = 0; blk < words.length; blk += 16) {
    const m = words.subarray(blk, blk + 16)
    let a = a0, b = b0, c = c0, d = d0
    for (let i = 0; i < 64; i++) {
      let f: number, g: number
      if (i < 16) {
        f = (b & c) | (~b & d)
        g = i
      } else if (i < 32) {
        f = (d & b) | (~d & c)
        g = (5 * i + 1) % 16
      } else if (i < 48) {
        f = b ^ c ^ d
        g = (3 * i + 5) % 16
      } else {
        f = c ^ (b | ~d)
        g = (7 * i) % 16
      }
      f = (f + a + K[i] + m[g]) >>> 0
      a = d
      d = c
      c = b
      b = (b + ((f << S[i] | f >>> (32 - S[i])) >>> 0)) >>> 0
    }
    a0 = (a0 + a) >>> 0
    b0 = (b0 + b) >>> 0
    c0 = (c0 + c) >>> 0
    d0 = (d0 + d) >>> 0
  }

  // 四个 32 位寄存器按小端序输出 16 字节十六进制
  return [a0, b0, c0, d0]
    .map((w) => (w >>> 0).toString(16).padStart(8, '0').match(/../g)!.reverse().join(''))
    .join('')
}

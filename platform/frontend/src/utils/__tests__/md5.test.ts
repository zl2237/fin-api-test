import { describe, expect, it } from 'vitest'
import { md5 } from '../md5'

/** 金标向量来自 Python hashlib（UTF-8 口径，与后端表达式 md5() 一致） */
describe('md5', () => {
  it.each([
    ['', 'd41d8cd98f00b204e9800998ecf8427e'],
    ['abc', '900150983cd24fb0d6963f7d28e17f72'],
    // 后端函数注册表文档同款示例（MainLayout 帮助卡 md5('123456')）
    ['123456', 'e10adc3949ba59abbe56e057f20f883e'],
    ['The quick brown fox jumps over the lazy dog', '9e107d9d372bb6826bd81d3542a419d6'],
    // 多块长输入：跨 64 字节分组与长度拼接
    ['a'.repeat(1000), 'cabe45dcc9ae5b66ba86600cca6b8ba8'],
    // 补位边界：55 字节（0x80+长度恰好同块）、56 字节（长度溢出到新块）、整 64 字节
    ['a'.repeat(55), 'ef1772b6dff9a122358552954ad0df65'],
    ['a'.repeat(56), '3b0c8ac703f828b04c6c197006d17218'],
    ['a'.repeat(64), '014842d480b571495a4a0363793f7367'],
  ])('md5(%j) = %s', (input, expected) => {
    expect(md5(input)).toBe(expected)
  })
})

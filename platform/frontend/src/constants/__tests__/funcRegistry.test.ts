import { describe, expect, it } from 'vitest'
import { FUNC_REGISTRY } from '../funcRegistry'

describe('FUNC_REGISTRY 内置函数注册表', () => {
  it('注册名唯一', () => {
    const names = FUNC_REGISTRY.map((f) => f.name)
    expect(new Set(names).size).toBe(names.length)
  })

  it('timestamp 与 timestamp_ms（加密传输时效字段）均已注册且入参一致', () => {
    const ts = FUNC_REGISTRY.find((f) => f.name === 'timestamp')
    const tsms = FUNC_REGISTRY.find((f) => f.name === 'timestamp_ms')
    expect(ts).toBeDefined()
    expect(tsms).toBeDefined()
    // 两者唯一入参都是 offset（偏移秒数），与后端 functions.py 对齐
    expect(ts!.params.map((p) => p.name)).toEqual(['offset'])
    expect(tsms!.params.map((p) => p.name)).toEqual(['offset'])
    // 毫秒版说明须点明 13 位用途，避免与秒级混用
    expect(tsms!.label).toContain('毫秒')
    expect(tsms!.params[0].placeholder).toContain('13 位')
  })
})

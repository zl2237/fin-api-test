import { describe, it, expect } from 'vitest'
import { toPinyinInitials } from '../pinyin'

describe('toPinyinInitials', () => {
  it('纯中文转首字母', () => {
    expect(toPinyinInitials('创建订单')).toBe('cjdd')
  })

  it('中英混合', () => {
    // 'API管理' → 'API' 转小写 'api' + '管理' → 'gl'
    expect(toPinyinInitials('API管理')).toBe('apigl')
  })

  it('纯英文转小写', () => {
    expect(toPinyinInitials('TestCase')).toBe('testcase')
  })

  it('空字符串返回空', () => {
    expect(toPinyinInitials('')).toBe('')
  })

  it('未收录汉字返回空字符串', () => {
    expect(toPinyinInitials('　')).toBe('　') // 全角空格非中文，原样保留
  })

  it('数字保留', () => {
    expect(toPinyinInitials('订单2024')).toBe('dd2024')
  })

  it('包含分隔符保留', () => {
    expect(toPinyinInitials('创建-订单')).toBe('cj-dd')
  })

  it('常见姓氏', () => {
    expect(toPinyinInitials('张三')).toBe('zs')
    // 王五均在 w 组
    expect(toPinyinInitials('王五')).toBe('ww')
  })
})

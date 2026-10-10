import { describe, it, expect, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useFieldDict } from '../useFieldDict'
import { useAppStore } from '@/stores'

describe('useFieldDict', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('resolveLabel 优先已有 label（含纯空白回退字典）', () => {
    const store = useAppStore()
    store.fieldDictMap = { amount: '金额' }
    const { resolveLabel } = useFieldDict()
    expect(resolveLabel('amount', '自定义')).toBe('自定义')
    expect(resolveLabel('amount', '   ')).toBe('金额')
    expect(resolveLabel('amount')).toBe('金额')
  })

  it('嵌套路径匹配：完整路径优先，其后按后缀（末段 → 末两段 → …）', () => {
    const store = useAppStore()
    store.fieldDictMap = {
      'to_customer.put_amount': '放款金额',
      'order_id': '订单号',
      'customer_no': '客户号',
    }
    const { dictLabel } = useFieldDict()
    expect(dictLabel('to_customer.put_amount')).toBe('放款金额') // 完整命中优先
    expect(dictLabel('payment.to_customer.put_amount')).toBe('放款金额') // 末两段命中
    expect(dictLabel('a.b.order_id')).toBe('订单号') // 末段命中
    expect(dictLabel('to_customer.customer_no')).toBe('客户号') // 末段命中
    expect(dictLabel('to_customer.xxx.yyy')).toBe('') // 纯父级段不参与后缀匹配（与实现一致）
  })

  it('空 key 与未命中返回空串', () => {
    useAppStore().fieldDictMap = { a: 'A' }
    const { dictLabel } = useFieldDict()
    expect(dictLabel('')).toBe('')
    expect(dictLabel('zzz')).toBe('')
  })
})

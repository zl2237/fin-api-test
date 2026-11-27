import { describe, expect, it } from 'vitest'
import {
  cryptoToForm,
  emptyCryptoForm,
  formToCrypto,
  validateCryptoForm,
} from '../cryptoConfig'

describe('cryptoConfig 纯函数', () => {
  it('空配置兜底为默认表单态', () => {
    for (const cfg of [null, undefined, {}]) {
      expect(cryptoToForm(cfg as any)).toEqual(emptyCryptoForm())
    }
  })

  it('payload → 表单：缺省字段补默认值（老数据无该列安全）', () => {
    const f = cryptoToForm({ request: { enabled: true, key: 'customs' }, response: { enabled: true } })
    expect(f.reqEnabled).toBe(true)
    expect(f.reqKey).toBe('customs')
    expect(f.wrapperField).toBe('requestCipher')
    expect(f.segmentSize).toBe(244)
    expect(f.respEnabled).toBe(true)
    expect(f.respMode).toBe('field')
    expect(f.respField).toBe('responseCipher')
  })

  it('表单 → payload：全关返回 null', () => {
    expect(formToCrypto(emptyCryptoForm())).toBeNull()
    const f = emptyCryptoForm()
    f.reqEnabled = true
    f.reqEnabled = false  // 开了又关：等价全关
    expect(formToCrypto(f)).toBeNull()
  })

  it('表单 → payload：请求加密形状与归一化（分段越界夹回、空包裹字段补默认）', () => {
    const f = emptyCryptoForm()
    f.reqEnabled = true
    f.reqKey = ' customs '
    f.wrapperField = '   '
    f.segmentSize = 999
    const cfg = formToCrypto(f)!
    expect(cfg.request).toEqual({
      enabled: true, mode: 'encrypt', key: 'customs',
      wrapper_field: 'requestCipher', segment_size: 245,
    })
    expect(cfg.response).toBeUndefined()

    f.segmentSize = 0
    expect(formToCrypto(f)!.request!.segment_size).toBe(1)
    f.segmentSize = null
    expect(formToCrypto(f)!.request!.segment_size).toBe(244)
  })

  it('表单 → payload：sign 模式形状（data/sign 字段名归一、source_field 留空→undefined）', () => {
    const f = emptyCryptoForm()
    f.reqEnabled = true
    f.reqMode = 'sign'
    f.reqKey = 'yhr'
    f.reqDataField = '  '
    f.reqSignField = 'sig'
    f.reqSourceField = ''
    const cfg = formToCrypto(f)!
    expect(cfg.request).toEqual({
      enabled: true, mode: 'sign', key: 'yhr',
      data_field: 'data', sign_field: 'sig', source_field: undefined,
    })
    // sign 模式不携带加密信封字段
    expect((cfg.request as Record<string, any>).wrapper_field).toBeUndefined()
    expect((cfg.request as Record<string, any>).segment_size).toBeUndefined()
  })

  it('payload → 表单：sign 配置回显（老数据缺 mode 默认 encrypt）', () => {
    const f = cryptoToForm({ request: { enabled: true, mode: 'sign', key: 'yhr',
      data_field: 'payload', sign_field: 'signature', source_field: 'credit_codes' } })
    expect(f.reqMode).toBe('sign')
    expect(f.reqDataField).toBe('payload')
    expect(f.reqSignField).toBe('signature')
    expect(f.reqSourceField).toBe('credit_codes')

    const legacy = cryptoToForm({ request: { enabled: true, key: 'customs' } })
    expect(legacy.reqMode).toBe('encrypt')  // 老数据无 mode → 默认加密信封
  })

  it('表单 → payload：响应密钥留空 → undefined（后端复用请求密钥）', () => {
    const f = emptyCryptoForm()
    f.reqEnabled = true
    f.reqKey = 'customs'
    f.respEnabled = true
    f.respMode = 'body'
    const cfg = formToCrypto(f)!
    expect(cfg.response).toEqual({ enabled: true, key: undefined, mode: 'body', field: 'responseCipher' })
  })

  it('校验：请求加密缺密钥名 / 仅响应解密缺密钥名均拦截，正常配置通过', () => {
    const f = emptyCryptoForm()
    f.reqEnabled = true
    expect(validateCryptoForm(f)).toContain('请求加密')

    const g = emptyCryptoForm()
    g.respEnabled = true
    expect(validateCryptoForm(g)).toContain('响应解密')

    const ok = emptyCryptoForm()
    ok.respEnabled = true
    ok.respKey = 'customs'
    expect(validateCryptoForm(ok)).toBe('')
  })

  it('往返一致：formToCrypto → cryptoToForm 恢复表单态', () => {
    const f = emptyCryptoForm()
    f.reqEnabled = true
    f.reqKey = 'customs'
    f.wrapperField = 'dataCipher'
    f.segmentSize = 128
    f.respEnabled = true
    f.respKey = 'cfca'
    f.respMode = 'body'
    expect(cryptoToForm(formToCrypto(f))).toEqual(f)
  })

  it('往返一致（sign 模式）', () => {
    const f = emptyCryptoForm()
    f.reqEnabled = true
    f.reqMode = 'sign'
    f.reqKey = 'yhr'
    f.reqDataField = 'payload'
    f.reqSignField = 'signature'
    f.reqSourceField = 'credit_codes'
    expect(cryptoToForm(formToCrypto(f))).toEqual(f)
  })
})

/** 接口加密配置（api_definitions.crypto_config）表单态 ↔ payload 互转纯函数。
 *  形状契约与后端 request_sender.py 对齐：
 *  request{enabled,mode(encrypt|sign),key,...} + response{enabled,key,mode(field|body),field}；
 *  密钥材料本身存环境 cipher_config。
 *  encrypt=加密信封（海关 requestCipher：wrapper_field+segment_size）；
 *  sign=参数签名（亿海融：data_field/sign_field/source_field，签名走后端 md5）。 */
import type { CryptoConfig } from '@/api'

export interface CryptoFormState {
  reqEnabled: boolean
  reqMode: 'encrypt' | 'sign'
  reqKey: string
  wrapperField: string
  segmentSize: number | null
  reqDataField: string
  reqSignField: string
  reqSourceField: string
  respEnabled: boolean
  respKey: string
  respMode: 'field' | 'body'
  respField: string
}

export function emptyCryptoForm(): CryptoFormState {
  return {
    reqEnabled: false,
    reqMode: 'encrypt',
    reqKey: '',
    wrapperField: 'requestCipher',
    segmentSize: 244,
    reqDataField: 'data',
    reqSignField: 'sign',
    reqSourceField: '',
    respEnabled: false,
    respKey: '',
    respMode: 'field',
    respField: 'responseCipher',
  }
}

/** payload → 表单（null/缺省一律兜底为默认值，老数据无该列也安全） */
export function cryptoToForm(cfg: CryptoConfig | null | undefined): CryptoFormState {
  const f = emptyCryptoForm()
  if (!cfg) return f
  const req: Record<string, any> = cfg.request || {}
  const resp: Record<string, any> = cfg.response || {}
  f.reqEnabled = !!req.enabled
  f.reqMode = req.mode === 'sign' ? 'sign' : 'encrypt'
  f.reqKey = req.key || ''
  f.wrapperField = req.wrapper_field || 'requestCipher'
  f.segmentSize = req.segment_size ?? 244
  f.reqDataField = req.data_field || 'data'
  f.reqSignField = req.sign_field || 'sign'
  f.reqSourceField = req.source_field || ''
  f.respEnabled = !!resp.enabled
  f.respKey = resp.key || ''
  f.respMode = resp.mode === 'body' ? 'body' : 'field'
  f.respField = resp.field || 'responseCipher'
  return f
}

/** 表单 → payload：两段开关全关 → null（列存 null 语义最干净）；
 *  仅做形状转换（按模式产出各自字段，不交叉携带），开关与名称的配套校验
 *  见 validateCryptoForm */
export function formToCrypto(f: CryptoFormState): CryptoConfig | null {
  if (!f.reqEnabled && !f.respEnabled) return null
  const cfg: CryptoConfig = {}
  if (f.reqEnabled) {
    if (f.reqMode === 'sign') {
      cfg.request = {
        enabled: true,
        mode: 'sign',
        key: f.reqKey.trim(),
        data_field: f.reqDataField.trim() || 'data',
        sign_field: f.reqSignField.trim() || 'sign',
        // 留空 undefined → 后端取整个请求体作为载荷
        source_field: f.reqSourceField.trim() || undefined,
      }
    } else {
      cfg.request = {
        enabled: true,
        mode: 'encrypt',
        key: f.reqKey.trim(),
        wrapper_field: f.wrapperField.trim() || 'requestCipher',
        // null/非数=未填 → 默认 244；显式数值（含 0/负数）→ 夹回 1~245
        // （2048 位参考上限；实际单段上限随密钥位数由后端动态校验）
        segment_size: (() => {
          const n = f.segmentSize
          const v = n == null || !Number.isFinite(n) ? 244 : Math.trunc(n)
          return Math.min(Math.max(v, 1), 245)
        })(),
      }
    }
  }
  if (f.respEnabled) {
    cfg.response = {
      enabled: true,
      // 留空 undefined → 后端复用 request.key（仅响应解密开启时必须显式填写）
      key: f.respKey.trim() || undefined,
      mode: f.respMode,
      field: f.respField.trim() || 'responseCipher',
    }
  }
  return cfg
}

/** 保存前校验：返回错误文案（空串=通过）。
 *  规则镜像后端 send_request 的报错条件，前端先拦一遍少跑一次保存 */
export function validateCryptoForm(f: CryptoFormState): string {
  if (f.reqEnabled && !f.reqKey.trim()) {
    return '请求加密/签名已开启：请填写密钥对名称（须与环境「加密配置」里的名称一致）'
  }
  if (f.respEnabled && !f.respKey.trim() && !(f.reqEnabled && f.reqKey.trim())) {
    return '响应解密已开启：请填写密钥对名称（未单独配置时将复用请求加密的密钥对名称，两者需至少填一个）'
  }
  return ''
}

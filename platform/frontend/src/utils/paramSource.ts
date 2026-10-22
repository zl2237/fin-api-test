/**
 * 参数四来源（ParamSpec）共用判定/解析纯函数。
 * ParamSourceForm（编辑态表单）与 ParamSourceBadge（只读徽标态）原先各自
 * 持有 verbatim 副本，收敛于此保证判定口径永远一致。
 */
import type { ParamSpec } from '@/api'

/** 任意历史值 → ParamSpec 结构判定（非 spec 的旧数据由调用方兜底为 constant） */
export function isParamSpec(v: any): v is ParamSpec {
  return !!v && typeof v === 'object' && !Array.isArray(v)
    && typeof v.source === 'string'
    && ['constant', 'func', 'ref', 'sql'].includes(v.source)
}

/** 常量值 → 文件中心 file_id（数字或纯数字串；否则 null）。fileField 字段的取值解析 */
export function toFileId(v: unknown): number | null {
  if (typeof v === 'number') return v
  if (typeof v === 'string' && /^\d+$/.test(v)) return Number(v)
  return null
}

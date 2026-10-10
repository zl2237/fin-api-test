/** 接口字段路径选项：顶层字段 + array/object 示例值嵌套展开（深度 2），
 *  label 智能挂接字段字典中文名。NodeParamsTable 使用。 */
import { computed } from 'vue'
import type { ApiField } from '@/api'
import { useFieldDict } from '@/composables/useFieldDict'

export interface FieldOption {
  value: string
  label: string
  /** 顶层字段原始定义（嵌套展开项无） */
  field?: ApiField
}

function tryParseJson(s: any): any {
  if (s == null || s === '') return null
  if (typeof s !== 'string') return s
  try {
    return JSON.parse(s)
  } catch {
    return null
  }
}

function inferType(v: any): string {
  if (v === null || v === undefined) return 'null'
  if (Array.isArray(v)) return 'array'
  if (typeof v === 'object') return 'object'
  if (typeof v === 'number') return Number.isInteger(v) ? 'int' : 'number'
  if (typeof v === 'boolean') return 'bool'
  return 'string'
}

export function useApiFieldOptions(fields: () => ApiField[]) {
  const { resolveLabel, dictLabel } = useFieldDict()

  // canonBase 为去掉数组下标的规范路径（supplier.0.order_id → supplier.order_id），
  // 供 dictLabel 按完整路径/末段/父级段智能命中字典中文名
  function collectKeys(obj: any, base: string, canonBase: string, out: FieldOption[], depth = 0): void {
    if (depth > 2) return
    if (Array.isArray(obj)) {
      if (obj.length === 0) return
      obj.forEach((item, idx) => {
        if (item && typeof item === 'object') {
          for (const [k, v] of Object.entries(item)) {
            const childPath = `${base}.${idx}.${k}`
            const childCanon = `${canonBase}.${k}`
            const t = inferType(v)
            const cn = dictLabel(childCanon)
            out.push({ value: childPath, label: cn ? `${childPath}（${cn}）[${t}]` : `${childPath} [${t}]` })
            if (v && typeof v === 'object') collectKeys(v, childPath, childCanon, out, depth + 1)
          }
        }
      })
    } else if (obj && typeof obj === 'object') {
      for (const [k, v] of Object.entries(obj)) {
        const childPath = `${base}.${k}`
        const t = inferType(v)
        const cn = dictLabel(childPath)
        out.push({ value: childPath, label: cn ? `${childPath}（${cn}）[${t}]` : `${childPath} [${t}]` })
        if (v && typeof v === 'object') collectKeys(v, childPath, childPath, out, depth + 1)
      }
    }
  }

  const fieldOptions = computed<FieldOption[]>(() => {
    const opts: FieldOption[] = []
    for (const f of fields()) {
      const cn = resolveLabel(f.key, f.label)
      const label = cn ? `${f.key}（${cn}）[${f.field_type}]` : `${f.key} [${f.field_type}]`
      opts.push({ value: f.key, label, field: f })
      if (f.field_type === 'array' || f.field_type === 'object') {
        const parsed = tryParseJson(f.default_value)
        if (parsed) collectKeys(parsed, f.key, f.key, opts)
      }
    }
    return opts
  })

  /** 按路径前缀匹配顶层字段（file 类型判断等用） */
  const topFieldOf = (path: string): ApiField | undefined =>
    fields().find((f) => f.key === path)

  return { fieldOptions, topFieldOf }
}

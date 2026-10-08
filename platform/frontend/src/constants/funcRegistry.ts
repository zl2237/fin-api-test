/** 内置函数注册表：与后端 app/engine/functions.py FUNCTIONS 对齐（唯一维护点）。
 *  来源2（func）下拉数据源；params 供入参表单渲染（kind 可切 const/ref）。 */
export interface FuncParamMeta {
  name: string
  label: string
  placeholder?: string
}
export interface FuncMeta {
  name: string
  label: string
  params: FuncParamMeta[]
}

export const FUNC_REGISTRY: FuncMeta[] = [
  { name: 'generate_bl_no', label: '生成提单号', params: [{ name: 'prefix', label: '前缀', placeholder: "默认 'SMOK'" }] },
  { name: 'generate_unique_id', label: '生成唯一 ID', params: [] },
  { name: 'generate_invoice_number', label: '生成发票号', params: [{ name: 'prefix', label: '前缀', placeholder: "默认 'INV'" }] },
  { name: 'now', label: '当前时间', params: [{ name: 'format', label: '格式', placeholder: "如 '%Y-%m-%d %H:%M'，缺省 ISO" }] },
  { name: 'timestamp', label: 'Unix 时间戳(秒)', params: [] },
  { name: 'date_add', label: '日期偏移', params: [
    { name: 'base', label: '基准日期', placeholder: '缺省当前时间；可引用上游日期（如应收汇日期）' },
    { name: 'days', label: '天数', placeholder: '如 7 / -1' },
    { name: 'format', label: '格式', placeholder: "默认 '%Y-%m-%d'" },
  ] },
  { name: 'random_int', label: '随机整数', params: [
    { name: 'min', label: '最小值', placeholder: '默认 0' },
    { name: 'max', label: '最大值', placeholder: '默认 100' },
  ] },
  { name: 'random_string', label: '随机字符串', params: [{ name: 'length', label: '长度', placeholder: '默认 8' }] },
  { name: 'uuid', label: 'UUID', params: [] },
  { name: 'upper', label: '转大写', params: [{ name: 's', label: '字符串', placeholder: 'abc' }] },
  { name: 'lower', label: '转小写', params: [{ name: 's', label: '字符串', placeholder: 'ABC' }] },
  { name: 'md5', label: 'MD5 哈希', params: [{ name: 's', label: '字符串', placeholder: '123456' }] },
]

export function funcMeta(name: string): FuncMeta | undefined {
  return FUNC_REGISTRY.find((f) => f.name === name)
}

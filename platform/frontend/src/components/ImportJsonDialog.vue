<template>
  <el-dialog
    :model-value="visible"
    title="导入请求体（JSON / 表单 / cURL 自动识别）"
    width="min(760px, 92vw)"
    @update:model-value="(v: boolean) => emit('update:visible', v)"
  >
    <el-input
      v-model="importText"
      type="textarea"
      :rows="8"
      placeholder='粘贴该节点新一套数据的请求体：JSON（{"bl_no":"SMOK2026..."}）、表单串（wd=xxx&page=1）、或完整 cURL 命令'
    />
    <div class="import-bar">
      <el-button size="small" type="primary" plain @click="parseImport">解析预览</el-button>
      <span v-if="importFormat" class="import-note">已按{{ formatLabel }}解析</span>
      <span v-if="importArrayBody" class="import-note">顶层数组请求体：按首元素解析，路径对齐元素字段</span>
      <span v-if="importParsed && !importParsed.ok" class="import-err">{{ importParsed.error }}</span>
      <span v-else-if="importParsed?.ok" class="import-sum">
        替换 {{ importReplaceCount }} 个常量字段、新增 {{ importAddCount }} 个未配置字段；跳过 {{ importParsed.rows.length - importReplaceCount - importAddCount }} 个（非常量 / 通配 / 未命中）
      </span>
    </div>
    <el-table v-if="importParsed?.ok" :data="importParsed.rows" size="small" max-height="320">
      <el-table-column prop="path" label="字段路径" min-width="150" show-overflow-tooltip />
      <el-table-column label="旧值" min-width="160" show-overflow-tooltip>
        <template #default="{ row }"><code class="import-val">{{ fmtImportVal(row.old) }}</code></template>
      </el-table-column>
      <el-table-column label="新值" min-width="160" show-overflow-tooltip>
        <template #default="{ row }"><code class="import-val" :class="{ hit: row.hit }">{{ fmtImportVal(row.neu) }}</code></template>
      </el-table-column>
      <el-table-column label="状态" width="150">
        <template #default="{ row }">
          <el-tag v-if="row.hit && row.add" size="small" type="warning">新增</el-tag>
          <el-tag v-else-if="row.hit" size="small" type="success">替换</el-tag>
          <el-tag v-else size="small" type="info">{{ row.note }}</el-tag>
        </template>
      </el-table-column>
    </el-table>
    <template #footer>
      <el-button @click="emit('update:visible', false)">取消</el-button>
      <el-button type="primary" :disabled="!importReplaceCount && !importAddCount" @click="applyImport">应用到草稿</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
/**
 * 导入请求体（DatasetManage 迁出）：JSON / 表单串 / cURL 三格式自动识别
 * （utils/importPayload 解析）。已配置常量字段整组替换；非常量 / 通配路径不动；
 * 导入数据中未配置的字段初始化为常量入参。产出新 body 由父级写入草稿
 * （onDraftChange 通道）。
 */
import { computed, ref } from 'vue'
import type { ParamSpec } from '@/api'
import { parseImportText, type ImportFormat } from '@/utils/importPayload'

const props = defineProps<{
  visible: boolean
  /** 当前节点草稿的 body 参数（读取快照参与解析；apply 时以最新 prop 为底） */
  body: Record<string, ParamSpec>
}>()
const emit = defineEmits<{
  (e: 'update:visible', v: boolean): void
  (e: 'apply', body: Record<string, ParamSpec>, replaced: number, added: number): void
}>()

interface ImportRow {
  path: string
  old: unknown        // 旧常量值（非常量行存来源摘要，新增行为 undefined）
  neu: unknown        // 新值（未命中为 undefined）
  hit: boolean
  add?: boolean       // 未配置字段：应用时新增为 constant
  note?: string
}
const importText = ref('')
const importFormat = ref<ImportFormat | null>(null) // 本次解析识别的格式（提示用）
const importArrayBody = ref(false) // 顶层数组请求体：按首元素解析
const importParsed = ref<null | { ok: boolean; error?: string; rows: ImportRow[] }>(null)
const formatLabel = computed(() => ({ json: ' JSON ', form: '表单', curl: ' cURL ' }[importFormat.value as ImportFormat]))
const importReplaceCount = computed(() =>
  importParsed.value?.ok ? importParsed.value.rows.filter((r) => r.hit && !r.add).length : 0)
const importAddCount = computed(() =>
  importParsed.value?.ok ? importParsed.value.rows.filter((r) => r.hit && r.add).length : 0)

/** 按参数路径（a.b / arr.0.c）从导入 JSON 下钻取值；取不到返回 undefined */
function getByPath(obj: unknown, path: string): unknown {
  let cur: unknown = obj
  for (const seg of path.split('.')) {
    if (cur == null || typeof cur !== 'object') return undefined
    cur = (cur as Record<string, unknown>)[seg]
  }
  return cur
}

/** 展开 JSON 全部叶子路径 → 值（嵌套对象/数组递归下钻，空对象/数组视为叶子）。
 *  标量数组整体作为叶子（["885"] → customer_id 一个参数，值为数组）：
 *  拆成 customer_id.0 只对 array 字段有意义，string 字段会在组装时
 *  被建成 {"0":"885"} 破坏请求（2026-10-12 record 995 回归）；
 *  dict 元素数组照旧按下标拆（select_list.0.xxx 模式） */
function flattenLeaves(obj: unknown, prefix = '', out: Record<string, unknown> = {}): Record<string, unknown> {
  if (obj !== null && typeof obj === 'object' && !Array.isArray(obj) && Object.keys(obj).length) {
    for (const [k, v] of Object.entries(obj)) flattenLeaves(v, prefix ? `${prefix}.${k}` : k, out)
  } else if (Array.isArray(obj) && obj.length && obj.every((v) => v !== null && typeof v === 'object' && !Array.isArray(v))) {
    obj.forEach((v, i) => flattenLeaves(v, `${prefix}.${i}`, out))
  } else {
    out[prefix] = obj
  }
  return out
}

/** 叶子路径是否已被通配参数覆盖（对应段 '*' 或相等，如 lines.*.qty 覆盖 lines.0.qty） */
function matchesWildcard(leaf: string, configured: string): boolean {
  if (!configured.includes('*')) return false
  const a = leaf.split('.')
  const b = configured.split('.')
  return a.length === b.length && b.every((seg, i) => seg === '*' || seg === a[i])
}

/** 路径规范化：去掉数组下标段（0.currency→currency、lines.0.qty→lines.qty）。
 *  数组体接口的入参路径以元素字段为锚（后端按字段骨架组 dict 再包 [body]），
 *  导入叶子路径与已配置路径需做下标无关匹配 */
function canonPath(p: string): string {
  return p.split('.').filter((s) => !/^\d+$/.test(s)).join('.')
}

function parseImport() {
  // 三格式自动识别：JSON / 表单串 / cURL（载荷递归识别），解析细节在 utils/importPayload
  const res = parseImportText(importText.value)
  if ('error' in res) {
    importFormat.value = null
    importParsed.value = { ok: false, error: res.error, rows: [] }
    return
  }
  importFormat.value = res.format
  const data = res.data
  // 顶层数组请求体（如上传应付发票 [{...}]）按首元素解析：入参路径以元素字段为锚，
  // 直接展开会产生 0.currency 这类下标路径，与已配置的 currency 对不上
  importArrayBody.value = Array.isArray(data) && data.length > 0
    && data[0] !== null && typeof data[0] === 'object' && !Array.isArray(data[0])
  const bodyData = importArrayBody.value ? (data as unknown[])[0] : data
  const body = props.body || {}
  const srcLabel: Record<string, string> = { func: '函数', ref: '引用', sql: 'SQL' }
  const leaves = flattenLeaves(bodyData)
  // 规范路径 → 首个命中叶子：配置与数据的数组下标形态不一致时也能对上
  const canonLeaf = new Map<string, string>()
  for (const p of Object.keys(leaves)) {
    const c = canonPath(p)
    if (c && !canonLeaf.has(c)) canonLeaf.set(c, p)
  }
  const rows: ImportRow[] = []
  for (const [path, spec] of Object.entries(body)) {
    if (!spec || spec.source !== 'constant') {
      rows.push({ path, old: srcLabel[spec?.source || ''] || spec?.source, neu: undefined, hit: false, note: '非常量，保持不动' })
      continue
    }
    if (path.includes('*')) {
      rows.push({ path, old: spec.value, neu: undefined, hit: false, note: '通配路径，不参与' })
      continue
    }
    let v = getByPath(bodyData, path)
    if (v === undefined) {
      const lp = canonLeaf.get(canonPath(path))
      if (lp !== undefined) v = leaves[lp]
    }
    if (v === undefined) {
      rows.push({ path, old: spec.value, neu: undefined, hit: false, note: '未命中，保持原值' })
      continue
    }
    rows.push({ path, old: spec.value, neu: v, hit: true })
  }
  // JSON 中存在但未配置的字段：初始化为常量入参（已被通配/已配置路径覆盖的跳过）
  const configured = Object.keys(body)
  const configuredCanon = new Set(configured.map(canonPath).filter(Boolean))
  for (const [path, v] of Object.entries(leaves)) {
    if (!path || configured.includes(path) || configured.some((c) => matchesWildcard(path, c))) continue
    if (configuredCanon.has(canonPath(path))) continue // 下标形态不同但同一字段，上面已按配置路径替换
    rows.push({ path, old: undefined, neu: v, hit: true, add: true, note: '新增' })
  }
  importParsed.value = { ok: true, rows }
}

function applyImport() {
  const parsed = importParsed.value
  if (!parsed?.ok) return
  const body: Record<string, ParamSpec> = { ...(props.body || {}) }
  for (const r of parsed.rows) {
    if (r.hit) body[r.path] = { source: 'constant', value: r.neu }
  }
  emit('apply', body, importReplaceCount.value, importAddCount.value)
  emit('update:visible', false)
}

/** 预览值显示：JSON 序列化截断，undefined 显示占位 */
function fmtImportVal(v: unknown): string {
  if (v === undefined) return '—'
  const s = typeof v === 'object' && v !== null ? JSON.stringify(v) : String(v)
  return s.length > 80 ? s.slice(0, 80) + '…' : s
}
</script>

<style scoped>
.import-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 8px 0;
  flex-wrap: wrap;
}
.import-note {
  font-size: 12px;
  color: var(--el-color-primary);
}
.import-sum {
  font-size: 12px;
  color: var(--app-text-muted);
}
.import-err {
  font-size: 12px;
  color: var(--el-color-danger);
}
.import-val {
  font-size: 12px;
}
.import-val.hit {
  color: var(--el-color-success);
  font-weight: 600;
}
</style>

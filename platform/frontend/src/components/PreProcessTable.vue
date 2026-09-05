<template>
  <div class="cfg-table">
    <el-table :data="modelValue" size="small" border empty-text="暂无预处理，点击「添加」开始配置">
      <el-table-column label="类型" width="140">
        <template #default="{ row }">
          <el-select v-model="row.type" size="small" style="width: 100%" @change="onTypeChange(row)">
            <el-option label="设置字段" value="set_field" />
            <el-option label="新增字段" value="add_field" />
            <el-option label="删除字段" value="delete_field" />
            <el-option label="遍历赋值" value="iterate_set" />
            <el-option label="执行 SQL" value="exec_sql" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column :label="pathLabel" min-width="220">
        <template #default="{ row }">
          <span v-if="row.type === 'exec_sql'" class="muted">—</span>
          <el-select
            v-else
            v-model="row.path"
            size="small"
            filterable
            allow-create
            default-first-option
            :placeholder="pathPlaceholder"
            style="width: 100%"
          >
            <el-option
              v-for="opt in availableFieldOptions(row)"
              :key="opt.value"
              :label="opt.label"
              :value="opt.value"
            />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="字段" width="140" v-if="hasIterate">
        <template #default="{ row }">
          <el-input v-if="row.type === 'iterate_set'" v-model="row.field" size="small" placeholder="unique_id" />
          <span v-else class="muted">—</span>
        </template>
      </el-table-column>
      <el-table-column label="值（支持 ${}）" min-width="240">
        <template #default="{ row }">
          <el-input
            v-if="row.type === 'exec_sql'"
            v-model="row.sql"
            size="small"
            type="textarea"
            :autosize="{ minRows: 2, maxRows: 6 }"
            placeholder="INSERT INTO t_order (bl_no) VALUES (${bl_no}) — ${} 可引用上下文变量"
          />
          <div v-else-if="row.type !== 'delete_field' && isFileField(row.path)" class="file-value-cell">
            <el-input
              :model-value="row.value ? `#${row.value}` : ''"
              size="small"
              readonly
              placeholder="未选择文件"
              class="file-value-input"
            />
            <el-button link type="primary" size="small" @click="openFilePicker(row)">选择</el-button>
          </div>
          <el-input
            v-else-if="row.type !== 'delete_field'"
            v-model="row.value"
            size="small"
            type="textarea"
            :rows="1"
            placeholder="${order_id} 或 ${db.query_value('SELECT ... WHERE id=${id}', field='xxx')}"
          />
          <span v-else class="muted">—</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="70" fixed="right">
        <template #default="{ $index }">
          <el-button link type="danger" size="small" @click="remove($index)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>
    <el-button class="add-btn" size="small" @click="add">+ 添加动作</el-button>

    <!-- 文件选择器 -->
    <FilePicker
      v-model="filePickerVisible"
      :model-file-id="filePickerTarget?.value"
      @select="onFileSelect"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, ref, shallowRef } from 'vue'
import type { ApiField, TestFile } from '@/api'
import { useFieldDict } from '@/composables/useFieldDict'
import FilePicker from '@/components/FilePicker.vue'

const props = defineProps<{ modelValue: any[]; fields?: ApiField[] }>()
const emit = defineEmits<{ (e: 'update:modelValue', v: any[]): void }>()

const fields = computed(() => props.fields || [])
const { resolveLabel, dictLabel } = useFieldDict()

interface FieldOption {
  value: string
  label: string
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

// 从示例值推断字段类型（用于嵌套字段，顶层字段直接用 ApiField.field_type）
function inferType(v: any): string {
  if (v === null || v === undefined) return 'null'
  if (Array.isArray(v)) return 'array'
  if (typeof v === 'object') return 'object'
  if (typeof v === 'number') return Number.isInteger(v) ? 'int' : 'number'
  if (typeof v === 'boolean') return 'bool'
  return 'string'
}

// 展开嵌套字段：label 统一为「路径（字典中文名，如有）[类型]」。
// canonBase 为去掉数组下标的规范路径（如 supplier.0.order_id → supplier.order_id），
// 传入 dictLabel 后可按 完整路径/末段/父级段 智能命中字典，使非顶层字段也能解析中文名。
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
          const lbl = cn ? `${childPath}（${cn}）[${t}]` : `${childPath} [${t}]`
          out.push({ value: childPath, label: lbl })
          if (v && typeof v === 'object') collectKeys(v, childPath, childCanon, out, depth + 1)
        }
      }
    })
  } else if (obj && typeof obj === 'object') {
    for (const [k, v] of Object.entries(obj)) {
      const childPath = `${base}.${k}`
      const t = inferType(v)
      const cn = dictLabel(childPath)
      const lbl = cn ? `${childPath}（${cn}）[${t}]` : `${childPath} [${t}]`
      out.push({ value: childPath, label: lbl })
      if (v && typeof v === 'object') collectKeys(v, childPath, childPath, out, depth + 1)
    }
  }
}

const fieldOptions = computed<FieldOption[]>(() => {
  const opts: FieldOption[] = []
  for (const f of fields.value) {
    // 优先用接口配置的 label，其次查项目字典；末尾追加接口管理配置的字段类型
    const cn = resolveLabel(f.key, f.label)
    const label = cn ? `${f.key}（${cn}）[${f.field_type}]` : `${f.key} [${f.field_type}]`
    opts.push({ value: f.key, label })
    if (f.field_type === 'array' || f.field_type === 'object') {
      const parsed = tryParseJson(f.default_value)
      if (parsed) collectKeys(parsed, f.key, f.key, opts)
    }
  }
  return opts
})

// 当前已使用的字段路径集合（排除空值）
const usedPaths = computed<Set<string>>(() => {
  const s = new Set<string>()
  for (const r of props.modelValue) {
    if (r?.path) s.add(r.path)
  }
  return s
})

// 每行可选字段路径：排除其他行已设置的路径，保留当前行已选值
function availableFieldOptions(row: any): FieldOption[] {
  const current = row?.path
  return fieldOptions.value.filter((opt) => opt.value === current || !usedPaths.value.has(opt.value))
}

const hasIterate = computed(() => props.modelValue.some((r) => r?.type === 'iterate_set'))
const pathLabel = computed(() => (hasIterate.value ? '路径 / 列表路径' : '字段路径'))
const pathPlaceholder = computed(() => (hasIterate.value ? '如 supplier 或 to_customer.put_amount.standard_list' : '如 order_id 或 supplier.0.order_id'))

function add() {
  const next = [...props.modelValue, { type: 'set_field', path: '', value: '' }]
  emit('update:modelValue', next)
}

// 类型切换清理：切到 exec_sql 后 path 不再使用，清空避免残留值占用字段可选集
function onTypeChange(row: any) {
  if (row.type === 'exec_sql') {
    row.path = ''
    if (row.sql == null) row.sql = ''
  }
}

function remove(idx: number) {
  const next = [...props.modelValue]
  next.splice(idx, 1)
  emit('update:modelValue', next)
}

// 判断当前路径是否对应 file 类型字段（仅匹配顶层字段 key）
function isFileField(path: string): boolean {
  if (!path) return false
  return fields.value.some((f) => f.key === path && f.field_type === 'file')
}

// ===== 文件选择器 =====
const filePickerVisible = ref(false)
const filePickerTarget = shallowRef<any>(null)

function openFilePicker(row: any) {
  filePickerTarget.value = row
  filePickerVisible.value = true
}

function onFileSelect(file: TestFile) {
  if (filePickerTarget.value) {
    filePickerTarget.value.value = String(file.id)
  }
  filePickerTarget.value = null
}
</script>

<style scoped>
.add-btn {
  margin-top: 8px;
  width: 100%;
  border-style: dashed;
}
.muted {
  color: var(--app-text-muted);
}
.file-value-cell {
  display: flex;
  align-items: center;
  gap: 4px;
}
.file-value-input {
  flex: 1;
}
</style>

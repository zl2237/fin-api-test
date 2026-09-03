<template>
  <div class="kv-table">
    <el-table :data="rows" size="small" border empty-text="暂无数据，点击「添加」开始配置" :row-class-name="dupRowClass">
      <el-table-column label="Key" min-width="160">
        <template #default="{ row }">
          <el-input v-model="row.key" size="small" :placeholder="keyPlaceholder" :class="{ 'is-error': isDupKey(row.key) }" />
        </template>
      </el-table-column>
      <el-table-column label="Value" min-width="240">
        <template #default="{ row }">
          <el-input
            v-model="row.value"
            size="small"
            :type="valueType === 'textarea' ? 'textarea' : 'text'"
            :rows="valueType === 'textarea' ? 2 : undefined"
            :placeholder="valuePlaceholder"
          />
        </template>
      </el-table-column>
      <el-table-column label="操作" width="70" fixed="right">
        <template #default="{ $index }">
          <el-button link type="danger" size="small" @click="remove($index)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>
    <!-- 重复 key 行内提示（原后行静默覆盖前行，用户无感知） -->
    <div v-if="dupKeys.length" class="dup-warn">
      ⚠ 以下 Key 重复，仅最后一行会生效：{{ dupKeys.join('、') }}
    </div>
    <el-button class="add-btn" size="small" @click="add">+ 添加</el-button>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, computed } from 'vue'

interface KVRow { key: string; value: string }

const props = withDefaults(defineProps<{
  keyPlaceholder?: string
  valuePlaceholder?: string
  valueType?: 'text' | 'textarea'
}>(), {
  keyPlaceholder: '字段名',
  valuePlaceholder: '字段值',
  valueType: 'text',
})

// 重复 key 即时校验：识别出现多次的 key（原后行覆盖前行且无提示）
const dupKeys = computed<string[]>(() => {
  const seen = new Map<string, number>()
  for (const r of rows.value) {
    if (r.key) seen.set(r.key, (seen.get(r.key) ?? 0) + 1)
  }
  return [...seen.entries()].filter(([, n]) => n > 1).map(([k]) => k)
})
function isDupKey(key: string) {
  return !!key && dupKeys.value.includes(key)
}
function dupRowClass({ row }: { row: KVRow }) {
  return isDupKey(row.key) ? 'kv-dup-row' : ''
}

/** 双向绑定：Record <-> 可编辑行（defineModel，Vue 3.4+） */
const model = defineModel<Record<string, any>>({ default: () => ({}) })

// 内部维护 rows 数组，允许存在 key 为空的待编辑行
const rows = ref<KVRow[]>([])
// 防止内部赋值触发的 model 变化又重建 rows（导致循环/丢失正在编辑的空行）
let isInternalChange = false

// 外部 model -> 内部 rows（保留当前未提交的空行，避免用户正在编辑的新行被清空）
watch(model, (obj) => {
  if (isInternalChange) {
    isInternalChange = false
    return
  }
  const newObj = obj || {}
  const validRows = Object.entries(newObj).map(([key, value]) => ({ key, value: String(value ?? '') }))
  // 保留当前 key 为空的行（用户已点添加但还没填 key）
  const emptyRows = rows.value.filter(r => !r.key)
  rows.value = [...validRows, ...emptyRows]
}, { immediate: true, deep: true })

// 内部 rows -> 外部 model（仅同步有效行，过滤掉 key 为空的待编辑行）
watch(rows, () => {
  isInternalChange = true
  const obj: Record<string, any> = {}
  for (const r of rows.value) {
    if (r.key) obj[r.key] = r.value
  }
  model.value = obj
}, { deep: true })

function add() {
  rows.value.push({ key: '', value: '' })
}

function remove(idx: number) {
  rows.value.splice(idx, 1)
}
</script>

<style scoped>
.kv-table {
  width: 100%;
}
.add-btn {
  margin-top: 10px;
  width: 100%;
  border-style: dashed;
}
/* 重复 key 行提示 */
:deep(.kv-dup-row) {
  background: color-mix(in srgb, var(--el-color-warning) 8%, transparent);
}
.dup-warn {
  margin-top: 6px;
  font-size: 12px;
  color: var(--el-color-warning);
  line-height: 1.6;
}
</style>

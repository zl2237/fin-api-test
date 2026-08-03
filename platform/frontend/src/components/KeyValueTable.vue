<template>
  <div class="kv-table">
    <el-table :data="rows" size="small" border>
      <el-table-column label="Key" min-width="160">
        <template #default="{ row }">
          <el-input v-model="row.key" size="small" :placeholder="keyPlaceholder" />
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
    <el-button class="add-btn" size="small" @click="add">+ 添加</el-button>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'

interface KVRow { key: string; value: string }

const props = withDefaults(defineProps<{
  modelValue: Record<string, any>
  keyPlaceholder?: string
  valuePlaceholder?: string
  valueType?: 'text' | 'textarea'
}>(), {
  keyPlaceholder: '字段名',
  valuePlaceholder: '字段值',
  valueType: 'text',
})

const emit = defineEmits<{ (e: 'update:modelValue', v: Record<string, any>): void }>()

// 内部维护 rows 数组，允许存在 key 为空的待编辑行
const rows = ref<KVRow[]>([])
// 防止内部 emit 触发的 modelValue 变化又重建 rows（导致循环/丢失正在编辑的空行）
let isInternalChange = false

// 外部 modelValue -> 内部 rows（保留当前未提交的空行，避免用户正在编辑的新行被清空）
watch(() => props.modelValue, (obj) => {
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

// 内部 rows -> 外部 modelValue（仅同步有效行，过滤掉 key 为空的待编辑行）
watch(rows, () => {
  isInternalChange = true
  const obj: Record<string, any> = {}
  for (const r of rows.value) {
    if (r.key) obj[r.key] = r.value
  }
  emit('update:modelValue', obj)
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
</style>

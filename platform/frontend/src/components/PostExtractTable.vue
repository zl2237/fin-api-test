<template>
  <div class="cfg-table">
    <el-table :data="modelValue" size="small" border>
      <el-table-column label="变量名" width="140">
        <template #default="{ row }">
          <el-input v-model="row.name" size="small" placeholder="order_id" />
        </template>
      </el-table-column>
      <el-table-column label="来源" width="100">
        <template #default="{ row }">
          <el-select v-model="row.source" size="small" style="width: 100%" @change="onSourceChange(row)">
            <el-option label="响应体" value="response" />
            <el-option label="数据库" value="db" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="JSON Path" min-width="200" v-if="hasResponse">
        <template #default="{ row }">
          <el-input
            v-if="row.source === 'response'"
            v-model="row.json_path"
            size="small"
            placeholder="$.data.order_id"
          />
          <span v-else class="muted">—</span>
        </template>
      </el-table-column>
      <el-table-column label="SQL" min-width="220" v-if="hasDb">
        <template #default="{ row }">
          <el-input
            v-if="row.source === 'db'"
            v-model="row.sql"
            size="small"
            type="textarea"
            :rows="1"
            placeholder="SELECT order_id FROM sys_order WHERE bl_no='${bl_no}'"
          />
          <span v-else class="muted">—</span>
        </template>
      </el-table-column>
      <el-table-column label="字段" width="120" v-if="hasDb">
        <template #default="{ row }">
          <el-input
            v-if="row.source === 'db'"
            v-model="row.field"
            size="small"
            placeholder="order_id（可选）"
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
    <el-button class="add-btn" size="small" @click="add">+ 添加提取</el-button>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{ modelValue: any[] }>()
const emit = defineEmits<{ (e: 'update:modelValue', v: any[]): void }>()

const hasResponse = computed(() => props.modelValue.some((r) => r.source === 'response' || !r.source))
const hasDb = computed(() => props.modelValue.some((r) => r.source === 'db'))

function onSourceChange(row: any) {
  // 切换来源时清理无关字段，避免脏数据
  if (row.source === 'db') {
    row.json_path = ''
  } else {
    row.sql = ''
    row.field = ''
  }
}

function add() {
  emit('update:modelValue', [...props.modelValue, { name: '', source: 'response', json_path: '', sql: '', field: '' }])
}
function remove(idx: number) {
  const next = [...props.modelValue]
  next.splice(idx, 1)
  emit('update:modelValue', next)
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
</style>

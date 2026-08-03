<template>
  <div class="cfg-table">
    <el-table :data="modelValue" size="small" border>
      <el-table-column label="类型" width="140">
        <template #default="{ row }">
          <el-select v-model="row.type" size="small" style="width: 100%">
            <el-option label="设置字段" value="set_field" />
            <el-option label="新增字段" value="add_field" />
            <el-option label="删除字段" value="delete_field" />
            <el-option label="遍历赋值" value="iterate_set" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column :label="pathLabel" min-width="180">
        <template #default="{ row }">
          <el-select
            v-model="row.path"
            size="small"
            filterable
            allow-create
            default-first-option
            :placeholder="pathPlaceholder"
            style="width: 100%"
          >
            <el-option
              v-for="f in fields"
              :key="f.key"
              :label="f.label ? `${f.key}（${f.label}）` : f.key"
              :value="f.key"
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
      <el-table-column label="值（支持 ${}）" min-width="200">
        <template #default="{ row }">
          <el-input v-if="row.type !== 'delete_field'" v-model="row.value" size="small" placeholder="${context.order_id}" />
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
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { ApiField } from '@/api'

const props = defineProps<{ modelValue: any[]; fields?: ApiField[] }>()
const emit = defineEmits<{ (e: 'update:modelValue', v: any[]): void }>()

const fields = computed(() => props.fields || [])

const hasIterate = computed(() => props.modelValue.some((r) => r?.type === 'iterate_set'))
const pathLabel = computed(() => (hasIterate.value ? '路径 / 列表路径' : '字段路径'))
const pathPlaceholder = computed(() => (hasIterate.value ? '如 to_customer.put_amount.standard_list' : '如 order_id'))

function add() {
  const next = [...props.modelValue, { type: 'set_field', path: '', value: '' }]
  emit('update:modelValue', next)
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

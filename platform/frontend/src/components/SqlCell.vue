<template>
  <div class="sql-cell">
    <el-input
      :model-value="modelValue"
      size="small"
      type="textarea"
      :autosize="{ minRows: 1, maxRows: 4 }"
      :placeholder="placeholder"
      @update:model-value="(v: string) => emit('update:modelValue', v)"
      @focus="onSqlFocus"
    />
    <SqlRefMenu :groups="refGroups" @insert="onSqlInsert" />
  </div>
</template>

<script setup lang="ts">
/**
 * SQL 单元格：textarea + 引用插入菜单（消费方：PostExtractTable / AssertionTable）。
 * 插入逻辑（光标处插入 {{节点.变量}} 并回焦）收敛在 useSqlInsert。
 */
import SqlRefMenu from '@/components/SqlRefMenu.vue'
import type { RefVarGroup } from '@/components/VarRefSelect.vue'
import { useSqlInsert } from '@/composables/useSqlInsert'

const props = defineProps<{
  modelValue: string
  placeholder?: string
  refGroups?: RefVarGroup[]
}>()
const emit = defineEmits<{ (e: 'update:modelValue', v: string): void }>()

const { onSqlFocus, onSqlInsert } = useSqlInsert(
  (next) => emit('update:modelValue', next),
  () => props.modelValue,
)
</script>

<style scoped>
.sql-cell {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 2px;
}
.sql-cell .el-textarea {
  width: 100%;
}
</style>

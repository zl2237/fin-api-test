<template>
  <div class="cfg-table">
    <el-table :data="modelValue" size="small" border>
      <el-table-column label="断言类型" width="200">
        <template #default="{ row }">
          <el-select v-model="row.type" size="small" style="width: 100%">
            <el-option-group label="响应断言">
              <el-option v-for="o in responseTypes" :key="o.value" :label="o.label" :value="o.value" />
            </el-option-group>
            <el-option-group label="DB 断言">
              <el-option v-for="o in dbTypes" :key="o.value" :label="o.label" :value="o.value" />
            </el-option-group>
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="JSON Path" min-width="160">
        <template #default="{ row }">
          <el-input
            v-if="needsJsonPath(row.type)"
            v-model="row.path"
            size="small"
            placeholder="$.data.status"
          />
          <span v-else class="muted">—</span>
        </template>
      </el-table-column>
      <el-table-column label="SQL" min-width="200">
        <template #default="{ row }">
          <el-input
            v-if="needsSql(row.type)"
            v-model="row.sql"
            size="small"
            type="textarea"
            :rows="1"
            placeholder="SELECT status FROM sys_order WHERE bl_no='${bl_no}'"
          />
          <span v-else class="muted">—</span>
        </template>
      </el-table-column>
      <el-table-column label="DB字段" width="120">
        <template #default="{ row }">
          <el-input
            v-if="needsField(row.type)"
            v-model="row.field"
            size="small"
            placeholder="status"
          />
          <span v-else class="muted">—</span>
        </template>
      </el-table-column>
      <el-table-column label="期望值" min-width="140">
        <template #default="{ row }">
          <el-input
            v-if="needsExpected(row.type)"
            v-model="row.expected"
            size="small"
            :placeholder="expectedPlaceholder(row.type)"
          />
          <span v-else class="muted">—</span>
        </template>
      </el-table-column>
      <el-table-column label="失败消息" min-width="160">
        <template #default="{ row }">
          <el-input v-model="row.message" size="small" placeholder="可选" />
        </template>
      </el-table-column>
      <el-table-column label="操作" width="70" fixed="right">
        <template #default="{ $index }">
          <el-button link type="danger" size="small" @click="remove($index)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>
    <el-button class="add-btn" size="small" @click="add">+ 添加断言</el-button>
  </div>
</template>

<script setup lang="ts">
const props = defineProps<{ modelValue: any[] }>()
const emit = defineEmits<{ (e: 'update:modelValue', v: any[]): void }>()

const responseTypes = [
  { label: 'JSON Path 等于', value: 'json_path_equals' },
  { label: 'JSON Path 不等于', value: 'json_path_not_equals' },
  { label: 'JSON Path 包含', value: 'json_path_contains' },
  { label: 'JSON Path 存在', value: 'json_path_exists' },
  { label: 'JSON Path 非空', value: 'json_path_not_empty' },
  { label: 'JSON Path 匹配正则', value: 'json_path_match_regex' },
  { label: 'JSON Path 类型校验', value: 'json_path_type_equals' },
  { label: 'HTTP 状态码等于', value: 'response_status_equals' },
  { label: '响应时间小于(ms)', value: 'response_time_less_than' },
]
const dbTypes = [
  { label: 'DB 查询字段等于', value: 'db_query_equals' },
  { label: 'DB 查询字段不等于', value: 'db_query_not_equals' },
  { label: 'DB 查询非空', value: 'db_query_not_empty' },
  { label: 'DB 查询行数等于', value: 'db_query_count_equals' },
  { label: 'DB 查询行数大于', value: 'db_query_count_greater_than' },
  { label: 'DB 查询行数小于', value: 'db_query_count_less_than' },
  { label: 'DB值 等于 响应字段', value: 'db_vs_jsonpath_equals' },
  { label: 'DB值 不等于 响应字段', value: 'db_vs_jsonpath_not_equals' },
]

function needsJsonPath(type: string) {
  return type.startsWith('json_path') || type.startsWith('db_vs_jsonpath')
}
function needsSql(type: string) {
  return type.startsWith('db_query') || type.startsWith('db_vs_jsonpath')
}
function needsField(type: string) {
  return ['db_query_equals', 'db_query_not_equals', 'db_vs_jsonpath_equals', 'db_vs_jsonpath_not_equals'].includes(type)
}
function needsExpected(type: string) {
  return !['json_path_exists', 'json_path_not_empty', 'db_query_not_empty', 'db_vs_jsonpath_equals', 'db_vs_jsonpath_not_equals'].includes(type)
}

function expectedPlaceholder(type: string) {
  if (type === 'response_time_less_than') return '毫秒数'
  if (type === 'json_path_match_regex') return '正则表达式 ^\\d+$'
  if (type === 'json_path_type_equals') return 'string / int / bool / array / object'
  if (type.startsWith('db_query_count')) return '数字'
  return '200 / ${context.xxx}'
}

function add() {
  emit('update:modelValue', [...props.modelValue, { type: 'json_path_equals', path: '', sql: '', field: '', expected: '', message: '' }])
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

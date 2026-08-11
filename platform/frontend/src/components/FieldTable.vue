<template>
  <div class="field-table">
    <el-table :data="modelValue" size="small" border empty-text="暂无字段，点击「添加字段」开始配置">
      <el-table-column label="字段路径（支持点号嵌套）" min-width="200">
        <template #default="{ row }">
          <el-input v-model="row.key" size="small" placeholder="order_id / to_customer.put_amount" />
        </template>
      </el-table-column>
      <el-table-column label="中文名" width="150">
        <template #default="{ row }">
          <el-input
            v-model="row.label"
            size="small"
            :placeholder="dictLabel(row.key) || '订单ID'"
          />
          <div v-if="!row.label && dictLabel(row.key)" class="dict-hint">字典: {{ dictLabel(row.key) }}</div>
        </template>
      </el-table-column>
      <el-table-column label="类型" width="110">
        <template #default="{ row }">
          <el-select v-model="row.field_type" size="small" style="width: 100%" @change="onTypeChange(row)">
            <el-option label="string" value="string" />
            <el-option label="int" value="int" />
            <el-option label="bool" value="bool" />
            <el-option label="object" value="object" />
            <el-option label="array" value="array" />
            <el-option label="file" value="file" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="必填" width="60" align="center">
        <template #default="{ row }">
          <el-checkbox v-model="row.required" />
        </template>
      </el-table-column>
      <el-table-column label="默认值（支持 ${}）" min-width="200">
        <template #default="{ row }">
          <div v-if="row.field_type === 'file'" class="file-value-cell">
            <el-input
              :model-value="row.default_value ? `#${row.default_value}` : ''"
              size="small"
              readonly
              placeholder="未选择文件"
              class="file-value-input"
            />
            <el-button link type="primary" size="small" @click="openFilePicker(row)">选择</el-button>
          </div>
          <el-input
            v-else
            v-model="row.default_value"
            size="small"
            :placeholder="row.field_type === 'array' ? 'JSON 数组，如 [{&quot;unique_id&quot;:&quot;&quot;}]' : '${generate_bl_no()}'"
          />
        </template>
      </el-table-column>
      <el-table-column label="备注" min-width="150">
        <template #default="{ row }">
          <el-input v-model="row.remark" size="small" placeholder="可选" />
        </template>
      </el-table-column>
      <el-table-column label="操作" width="70" fixed="right">
        <template #default="{ $index }">
          <el-button link type="danger" size="small" @click="remove($index)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>
    <el-button class="add-btn" size="small" @click="add">+ 添加字段</el-button>

    <!-- 文件选择器 -->
    <FilePicker
      v-model="filePickerVisible"
      :model-file-id="filePickerTarget?.default_value"
      @select="onFileSelect"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, shallowRef } from 'vue'
import type { ApiField, TestFile } from '@/api'
import { useFieldDict } from '@/composables/useFieldDict'
import FilePicker from '@/components/FilePicker.vue'

const props = defineProps<{ modelValue: ApiField[] }>()
const emit = defineEmits<{ (e: 'update:modelValue', v: ApiField[]): void }>()
const { dictLabel } = useFieldDict()

function add() {
  const list = [...props.modelValue]
  list.push({
    key: '',
    label: '',
    field_type: 'string',
    required: false,
    default_value: '',
    remark: '',
    sort_order: list.length,
  })
  emit('update:modelValue', list)
}

function remove(idx: number) {
  const list = [...props.modelValue]
  list.splice(idx, 1)
  // 重新排序
  list.forEach((f, i) => (f.sort_order = i))
  emit('update:modelValue', list)
}

// 切换类型时，若新类型与当前值不匹配则清空 default_value，避免脏数据
function onTypeChange(row: ApiField) {
  if (row.field_type === 'file') {
    // file 类型只接受纯数字 file_id 字符串，否则清空
    if (row.default_value && !/^\d+$/.test(row.default_value)) {
      row.default_value = ''
    }
  } else {
    // 从 file 切回其他类型时，清空 file_id
    if (row.default_value && /^\d+$/.test(row.default_value)) {
      row.default_value = ''
    }
  }
}

// ===== 文件选择器 =====
const filePickerVisible = ref(false)
const filePickerTarget = shallowRef<ApiField | null>(null)

function openFilePicker(row: ApiField) {
  filePickerTarget.value = row
  filePickerVisible.value = true
}

function onFileSelect(file: TestFile) {
  if (filePickerTarget.value) {
    filePickerTarget.value.default_value = String(file.id)
  }
  filePickerTarget.value = null
}
</script>

<style scoped>
.field-table {
  width: 100%;
}
.add-btn {
  margin-top: 10px;
  width: 100%;
  border-style: dashed;
}
.dict-hint {
  font-size: 11px;
  color: var(--app-text-muted);
  margin-top: 2px;
  line-height: 1.2;
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

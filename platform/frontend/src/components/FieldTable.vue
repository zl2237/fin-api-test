<template>
  <div class="field-table">
    <el-input
      v-model="keyword"
      size="small"
      clearable
      class="field-search"
      placeholder="按字段路径/中文名/示例值筛选，如 order_id"
      :prefix-icon="Search"
    />
    <el-table :data="filtered" size="small" border :empty-text="keyword ? `没有匹配「${keyword}」的字段` : '暂无字段，点击「添加字段」开始配置'">
      <el-table-column label="字段路径（支持点号嵌套）" min-width="200">
        <template #default="{ row }">
          <el-input v-model="row.key" size="small" placeholder="order_id / to_customer.put_amount" />
        </template>
      </el-table-column>
      <el-table-column label="中文名" width="150">
        <template #default="{ row }">
          <el-input v-model="row.label" size="small" placeholder="订单ID" />
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
      <el-table-column label="示例值" min-width="200">
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
            :placeholder="row.field_type === 'array' ? 'JSON 数组，如 [{&quot;unique_id&quot;:&quot;&quot;}]' : '仅作录入参考，如 BL2026101001'"
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
    <div v-if="keyword" class="filter-count">匹配 {{ filtered.length }} / {{ modelValue.length }} 个字段（编辑与删除作用于真实行）</div>
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
import { computed, ref, shallowRef } from 'vue'
import { Search } from '@element-plus/icons-vue'
import type { ApiField, TestFile } from '@/api'
import { useFieldDict } from '@/composables/useFieldDict'
import FilePicker from '@/components/FilePicker.vue'

const props = defineProps<{ modelValue: ApiField[] }>()
const emit = defineEmits<{ (e: 'update:modelValue', v: ApiField[]): void }>()
const { dictLabel } = useFieldDict()

// 关键词过滤（不区分大小写；路径/中文名/示例值/备注命中即显示）：
// 只影响展示层，行对象仍是 modelValue 的同一引用，行内编辑直接生效
const keyword = ref('')
const filtered = computed(() => {
  const q = keyword.value.trim().toLowerCase()
  if (!q) return props.modelValue
  return props.modelValue.filter((f) =>
    (f.key || '').toLowerCase().includes(q)
    || (f.label || '').toLowerCase().includes(q)
    || (f.default_value || '').toLowerCase().includes(q)
    || (f.remark || '').toLowerCase().includes(q),
  )
})

function add() {
  const list = [...props.modelValue]
  list.push({
    key: '',
    label: '',
    field_type: 'string',
    required: false,  // 必填概念已取消：字段恒 false，仅兼容后端模型
    default_value: '',
    remark: '',
    sort_order: list.length,
  })
  emit('update:modelValue', list)
}

function remove(idx: number) {
  const list = [...props.modelValue]
  // idx 来自过滤后列表：换算回全量列表的真实下标
  const real = list.indexOf(filtered.value[idx])
  if (real < 0) return
  list.splice(real, 1)
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
.field-search {
  width: 280px;
  margin-bottom: 8px;
}
.filter-count {
  margin-top: 6px;
  font-size: 12px;
  color: var(--app-text-muted);
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

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { WarningFilled } from '@element-plus/icons-vue'
import type { DataSet, TestCase } from '@/api'
import { useFieldDict } from '@/composables/useFieldDict'

/**
 * 数据集执行确认面板（仅多数据集用例弹出）：多选数据集各执行一次（单套数据）。
 * 名下仅一个数据集的用例在 CaseList 直接执行，不经此面板。
 * 确认后 emit('confirm', { datasetIds }) 并自关，执行编排在父视图完成。
 * （编排唯一来源是用例当前配置，无快照过期概念；临时换数据集不改绑定）
 */
const props = defineProps<{
  modelValue: boolean
  /** 当前要执行的用例（绑定数据集的） */
  caseItem: TestCase | null
  /** 该用例名下的数据集（父视图 loadDatasets 的单一数据源，绑定弹窗共用） */
  datasets: DataSet[]
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'confirm', payload: { datasetIds: number[] }): void
}>()

// 字段名统一展示约定（全站一致）：原始 key + 字典中文名（如有，含嵌套路径匹配）
const { dictLabel } = useFieldDict()
function colLabel(key: string) {
  const cn = dictLabel(key)
  return cn ? `${key}（${cn}）` : key
}

const visible = computed({
  get: () => props.modelValue,
  set: (v: boolean) => emit('update:modelValue', v),
})

/** 多选：默认选中绑定的数据集（多场景各执行一次） */
const datasetIds = ref<number[]>([])

watch(() => props.modelValue, (open) => {
  if (open) {
    const bound = props.caseItem?.dataset_id
    datasetIds.value = bound ? [bound] : (props.datasets[0] ? [props.datasets[0].id] : [])
  }
})

const current = computed(() => props.datasets.find((d) => d.id === datasetIds.value[0]))

function confirm() {
  if (!datasetIds.value.length) return
  emit('confirm', { datasetIds: [...datasetIds.value] })
  visible.value = false
}
</script>

<template>
  <el-dialog v-model="visible" :title="`数据集执行：${caseItem?.name || ''}`" width="560px">
    <div class="dd-tip">
      <el-icon style="color: var(--el-color-warning)"><WarningFilled /></el-icon>
      将使用所选的 <b>{{ datasetIds.length }} 个数据集各执行一次</b>（每个数据集单套数据），编排按用例当前配置；临时换数据集不改变用例绑定
    </div>
    <el-select v-model="datasetIds" multiple collapse-tags style="width: 100%; margin-bottom: 10px">
      <el-option
        v-for="d in datasets"
        :key="d.id"
        :label="`${d.name}（${d.columns?.length ?? 0} 个变量值）`"
        :value="d.id"
      />
    </el-select>
    <div v-if="current?.columns?.length" class="var-preview">
      <span v-for="c in current.columns.slice(0, 12)" :key="c.key" class="var-chip">
        {{ colLabel(c.key) }}
      </span>
      <span v-if="current.columns.length > 12" class="var-more">…共 {{ current.columns.length }} 个</span>
    </div>
    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="success" :disabled="!datasetIds.length" @click="confirm">执行</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.dd-tip {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  color: var(--el-text-color-secondary);
  font-size: 13px;
  margin-bottom: 12px;
  line-height: 1.6;
}
.var-preview {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.var-chip {
  font-size: 12px;
  color: var(--app-text-muted);
  background: var(--app-bg);
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius-sm);
  padding: 1px 8px;
}
.var-more {
  font-size: 12px;
  color: var(--app-text-faint);
}
</style>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { WarningFilled } from '@element-plus/icons-vue'
import { datasetApi, type DataSet, type TestCase } from '@/api'
import { useFieldDict } from '@/composables/useFieldDict'

/**
 * 数据驱动执行确认面板：N 行将执行 N 次，可临时换数据集/选行。
 * 自治状态（选行表格、数据集切换、快照过期检测与一键同步）收敛在组件内；
 * 确认后 emit('confirm', { datasetId, rowIds }) 并自关，执行编排由父视图
 * （useExecutionRunner 轮询/favicon/跳转执行记录）完成。
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
  (e: 'confirm', payload: { datasetId: number | null; rowIds: number[] }): void
}>()

// 字段名统一展示约定（全站一致）：原始 key + 字典中文名（如有，含嵌套路径匹配）
const { dictLabel } = useFieldDict()
function colLabel(key: string) {
  const cn = dictLabel(key)
  return cn ? `${key}（${cn}）` : key
}

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const datasetId = ref<number | null>(null)
const rows = ref<any[]>([])
const columns = ref<{ key: string; type?: string }[]>([])
const selectedRows = ref<any[]>([])
const tableRef = ref<any>(null)

// 快照过期检测：执行按快照跑，与用例当前编排不一致时在弹窗内提示并支持一键同步
const drift = ref<{ stale: boolean; nodes: { node_id: string; label: string; changes: string[] }[] } | null>(null)
const resyncing = ref(false)

// 打开时：默认用用例绑定的数据集，应用行/列并全选
watch(() => props.modelValue, async (open) => {
  if (!open) return
  datasetId.value = props.caseItem?.dataset_id ?? null
  applyDataset()
  await nextTick()
  tableRef.value?.toggleAllSelection?.()
})

function applyDataset() {
  const ds = props.datasets.find((d) => d.id === datasetId.value)
  rows.value = (ds?.rows as any[]) || []
  columns.value = (ds?.columns as any[]) || []
  selectedRows.value = rows.value
  checkDrift()
}

async function checkDrift() {
  drift.value = null
  if (!datasetId.value) return
  try {
    drift.value = await datasetApi.drift(datasetId.value)
  } catch {
    // 检测失败不阻断执行流程
  }
}

async function resync() {
  if (!datasetId.value) return
  resyncing.value = true
  try {
    await datasetApi.resync(datasetId.value)
    ElMessage.success('已同步用例当前编排到数据集快照')
    await checkDrift()
  } catch (e: any) {
    ElMessage.error(e.message || '同步失败')
  } finally {
    resyncing.value = false
  }
}

async function onDatasetChange() {
  applyDataset()
  await nextTick()
  tableRef.value?.toggleAllSelection?.()
}

function confirm() {
  if (!selectedRows.value.length) return
  emit('confirm', {
    datasetId: datasetId.value,
    rowIds: selectedRows.value.map((r) => r.id),
  })
  visible.value = false
}
</script>

<template>
  <el-dialog v-model="visible" :title="`数据驱动执行：${caseItem?.name || ''}`" width="640px">
    <div class="dd-tip">
      <el-icon style="color: var(--el-color-warning)"><WarningFilled /></el-icon>
      该用例绑定了数据集，<b>{{ selectedRows.length }} 行数据将执行 {{ selectedRows.length }} 次</b>（并行，并发上限 4）
    </div>
    <!-- 快照过期提示：数据集节点配置快照与用例当前编排不一致（执行按快照跑，先同步再执行） -->
    <el-alert v-if="drift?.stale" type="warning" :closable="false" class="drift-alert">
      <template #title>
        数据集快照已过期：{{ drift.nodes.length }} 个节点编排与用例当前不一致（执行按快照跑）
        <el-button link type="primary" size="small" :loading="resyncing" style="margin-left: 8px" @click="resync">
          一键同步（取用例当前编排）
        </el-button>
      </template>
      <div v-for="n in drift.nodes" :key="n.node_id" class="drift-node">
        <b>{{ n.label }}</b>：{{ n.changes.join('；') }}
      </div>
    </el-alert>
    <el-select v-model="datasetId" style="width: 260px; margin-bottom: 10px" @change="onDatasetChange">
      <el-option v-for="d in datasets" :key="d.id" :label="`${d.name}（${d.rows?.length ?? 0} 行）`" :value="d.id" />
    </el-select>
    <el-table
      ref="tableRef"
      :data="rows"
      size="small"
      max-height="320"
      row-key="id"
      @selection-change="(sel: any[]) => (selectedRows = sel)"
    >
      <el-table-column type="selection" width="42" />
      <el-table-column prop="row_index" label="#" width="50" />
      <el-table-column
        v-for="col in columns"
        :key="col.key"
        :label="colLabel(col.key)"
        min-width="120"
        show-overflow-tooltip
      >
        <template #header>
          <span>{{ colLabel(col.key) }}</span>
          <span v-if="col.type" class="col-type-tag">{{ col.type }}</span>
        </template>
        <template #default="{ row }">{{ row.data?.[col.key] ?? '—' }}</template>
      </el-table-column>
    </el-table>
    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="success" :disabled="!selectedRows.length" @click="confirm">
        执行 {{ selectedRows.length }} 次
      </el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
/* 原 CaseList scoped 样式迁移（bind-tip 同名类在视图侧供绑定弹窗继续使用） */
.col-type-tag {
  margin-left: 6px;
  font-size: 11px;
  color: var(--app-text-muted);
  border: 1px solid var(--el-border-color);
  border-radius: 3px;
  padding: 0 4px;
}
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
.drift-alert {
  margin-bottom: 10px;
}
.drift-node {
  font-size: 12px;
  line-height: 1.8;
}
</style>

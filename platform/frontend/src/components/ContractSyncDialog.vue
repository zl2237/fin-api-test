<template>
  <el-dialog
    :model-value="visible"
    :title="`接口参数与数据集配置有出入`"
    width="min(720px, 92vw)"
    :close-on-click-modal="false"
    @update:model-value="(v: boolean) => emit('update:visible', v)"
  >
    <div v-loading="loading" class="csd">
      <template v-if="result">
        <el-result icon="success" title="同步完成" :sub-title="resultText" />
      </template>
      <template v-else-if="!loading">
        <div class="csd-intro">
          <p>
            「{{ apiName }}」的字段契约与下方 <b>{{ items.length }}</b> 个数据集节点的参数配置存在出入。
            确认后将按接口当前字段同步<b>全部</b>引用数据集：
          </p>
          <ul class="csd-rules">
            <li>缺少的字段 → 按接口示例值补为常量（object/array 按结构拆到叶子路径），可再改为函数/引用/SQL</li>
            <li>契约外参数（常量）→ 移除</li>
            <li class="csd-redline">契约外参数（引用/函数/SQL 动态来源）→ 一律保留不动</li>
          </ul>
        </div>
        <div class="csd-list">
          <div v-for="it in items" :key="`${it.dataset_id}-${it.node_id}`" class="csd-item">
            <div class="csd-head">
              <span class="csd-ds">{{ it.dataset_name }}</span>
              <span class="csd-case">用例：{{ it.case_name }}</span>
              <span class="csd-node">节点：{{ it.node_label }}</span>
            </div>
            <div class="csd-gaps">
              <div v-if="it.gaps.missing?.length" class="cg missing">
                <span class="cg-tag">缺少 {{ it.gaps.missing.length }} 个字段</span>
                <span class="cg-paths">{{ it.gaps.missing.join('、') }}</span>
              </div>
              <div v-for="e in it.gaps.extra || []" :key="e.path" class="cg extra" :class="{ dynamic: e.dynamic }">
                <span class="cg-tag">{{ e.dynamic ? `契约外·${sourceLabel(e.source)}（保留不动）` : '契约外·常量（将移除）' }}</span>
                <span class="cg-paths">{{ e.path }}</span>
              </div>
            </div>
          </div>
        </div>
      </template>
    </div>
    <template #footer>
      <template v-if="result">
        <el-button type="primary" @click="close">完成</el-button>
      </template>
      <template v-else>
        <el-button @click="close">暂不同步</el-button>
        <el-button type="primary" :loading="syncing" :disabled="loading" @click="onSync">同步全部数据集</el-button>
      </template>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
/** 契约同步弹窗：接口字段契约 ↔ 数据集节点参数 出入预览 + 用户许可后全量同步。

两个触发点（2026-10-10 定案 Q4）：接口编辑保存后 / 数据集节点保存后；
红线（Q8）：非 constant 来源（ref/func/sql）参数只标注保留，绝不删改。
*/
import { ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { apiApi, type ContractImpactItem, type ContractSyncResult } from '@/api'

const props = defineProps<{
  visible: boolean
  apiId: number | null
  apiName?: string
}>()
const emit = defineEmits<{
  (e: 'update:visible', v: boolean): void
  (e: 'synced'): void
}>()

const loading = ref(false)
const syncing = ref(false)
const items = ref<ContractImpactItem[]>([])
const result = ref<ContractSyncResult | null>(null)

function sourceLabel(s: string): string {
  return { ref: '引用', func: '函数', sql: 'SQL' }[s] || s
}

watch(() => props.visible, async (v) => {
  if (!v) return
  result.value = null
  items.value = []
  if (!props.apiId) return
  loading.value = true
  try {
    items.value = await apiApi.contractImpact(props.apiId)
    if (!items.value.length) {
      // 打开时已无出入（他处刚同步过）：直接关闭不打扰
      emit('update:visible', false)
    }
  } catch (e: any) {
    ElMessage.error(e.message || '契约影响面查询失败')
    emit('update:visible', false)
  } finally {
    loading.value = false
  }
})

async function onSync() {
  if (!props.apiId) return
  syncing.value = true
  try {
    result.value = await apiApi.contractSync(props.apiId)
    emit('synced')
  } catch (e: any) {
    ElMessage.error(e.message || '同步失败')
  } finally {
    syncing.value = false
  }
}

const resultText = ref('')
watch(result, (r) => {
  if (!r) { resultText.value = ''; return }
  const t = r.total
  resultText.value = `已更新 ${t.nodes} 个数据集节点：补 ${t.added} 个参数、移除 ${t.removed} 个、跳过动态来源 ${t.skipped_dynamic} 个`
})

function close() {
  emit('update:visible', false)
}
</script>

<style scoped>
.csd-intro p {
  margin: 0 0 8px;
  font-size: 13px;
  line-height: 1.6;
}
.csd-rules {
  margin: 0 0 12px;
  padding-left: 18px;
  font-size: 12px;
  color: var(--app-text-muted);
}
.csd-rules li {
  line-height: 1.8;
}
.csd-redline {
  color: var(--el-color-warning);
}
.csd-list {
  max-height: 320px;
  overflow: auto;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.csd-item {
  border: 1px solid var(--app-border);
  border-radius: 5px;
  padding: 8px 10px;
}
.csd-head {
  display: flex;
  gap: 12px;
  align-items: baseline;
  font-size: 13px;
  margin-bottom: 6px;
}
.csd-ds {
  font-weight: 600;
}
.csd-case,
.csd-node {
  font-size: 12px;
  color: var(--app-text-muted);
}
.csd-gaps {
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.cg {
  display: flex;
  gap: 8px;
  align-items: baseline;
  font-size: 12px;
}
.cg-tag {
  flex-shrink: 0;
}
.cg.missing .cg-tag {
  color: var(--el-color-success);
}
.cg.extra .cg-tag {
  color: var(--el-color-danger);
}
.cg.extra.dynamic .cg-tag {
  color: var(--el-color-warning);
}
.cg-paths {
  font-family: var(--app-font-mono, monospace);
  color: var(--app-text-regular, inherit);
  word-break: break-all;
}
</style>

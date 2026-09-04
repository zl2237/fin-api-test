<script setup lang="ts">
import { computed, ref, watch } from 'vue'

/**
 * 批量执行配置弹窗：逐用例设置执行次数 + 并发数。
 * 只做配置 UI——确认后 emit('confirm', { caseIds, counts, concurrency }) 并自关，
 * 执行编排（提交/并发轮询/汇总提示）由父视图完成。
 */
const props = defineProps<{
  modelValue: boolean
  /** 待执行用例展示行（打开时父按勾选快照生成） */
  items: { id: number; name: string }[]
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'confirm', payload: { caseIds: number[]; counts: number[]; concurrency: number }): void
}>()

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const counts = ref<Record<number, number>>({})
const concurrency = ref(4)

// 每次打开重置：每用例次数 1、并发 4（与原视图打开时初始化一致）
watch(() => props.modelValue, (open) => {
  if (!open) return
  const init: Record<number, number> = {}
  props.items.forEach((it) => { init[it.id] = 1 })
  counts.value = init
  concurrency.value = 4
})

// 配置弹窗内的总轮次（每用例次数之和）
const total = computed(() =>
  props.items.reduce((sum, it) => sum + (counts.value[it.id] || 0), 0),
)

function confirm() {
  emit('confirm', {
    caseIds: props.items.map((it) => it.id),
    counts: props.items.map((it) => counts.value[it.id] || 1),
    concurrency: concurrency.value,
  })
  visible.value = false
}
</script>

<template>
  <el-dialog v-model="visible" title="批量执行" width="480px" align-center :close-on-click-modal="false">
    <div class="batch-run-tip">
      为每个用例设置执行次数，并发数 1 = 逐个串行执行（避免并发问题），&gt;1 并行（同环境共享登录）。绑定数据集的用例每轮按数据行展开。
    </div>
    <div class="batch-run-concurrency">
      <span class="batch-run-count-label">并发数</span>
      <el-input-number v-model="concurrency" :min="1" :max="16" size="small" />
      <span class="batch-run-concurrency-hint">{{ concurrency === 1 ? '串行：一个执行完再下一个' : `同时执行 ${concurrency} 个` }}</span>
    </div>
    <div class="batch-run-list">
      <div v-for="it in items" :key="it.id" class="batch-run-row">
        <el-tooltip :content="it.name" placement="top" popper-class="app-tip">
          <span class="batch-run-name">{{ it.name }}</span>
        </el-tooltip>
        <span class="batch-run-count-label">执行次数</span>
        <el-input-number v-model="counts[it.id]" :min="1" :max="9999" size="small" />
      </div>
    </div>
    <template #footer>
      <span class="batch-run-total">共 {{ items.length }} 个用例 / {{ total }} 轮</span>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="success" @click="confirm">开始执行</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
/* 原 CaseList scoped 样式迁移 */
.batch-run-tip {
  font-size: 12px;
  color: var(--app-text-muted);
  margin-bottom: 10px;
  line-height: 1.5;
}
.batch-run-concurrency {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 10px 0;
}
.batch-run-concurrency-hint {
  font-size: 12px;
  color: var(--app-text-muted);
}
.batch-run-list {
  max-height: 300px;
  overflow-y: auto;
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius-sm);
  padding: 4px 12px;
}
.batch-run-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 0;
}
.batch-run-row + .batch-run-row {
  border-top: 1px solid var(--app-border);
}
.batch-run-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
}
.batch-run-count-label {
  font-size: 12px;
  color: var(--app-text-muted);
  white-space: nowrap;
}
.batch-run-total {
  float: left;
  font-size: 12px;
  color: var(--app-text-muted);
  line-height: 32px;
}
</style>

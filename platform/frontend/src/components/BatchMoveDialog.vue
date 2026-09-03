<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import type { GroupTreeNode } from '../composables/useGroupedTable'

/**
 * 批量移动弹窗：目标分组选择 + 移动执行。
 * 移动逻辑经 props.move 注入（成功 resolve 则弹窗自关；失败 throw 则保持打开并统一报错），
 * 成功后的清空勾选/重载列表也在 move 回调内由父视图完成。
 */
const props = withDefaults(defineProps<{
  modelValue: boolean
  /** 待移动条目数（展示「将 N 个xx移动到」） */
  count: number
  /** useGroupTree.treeSelectWithUngrouped（含 id=0 的「未分组」虚拟节点） */
  treeData: GroupTreeNode[]
  /** 执行移动；targetGroupId 为 null 表示移到未分组 */
  move: (targetGroupId: number | null) => Promise<void>
  itemWord?: string
}>(), { itemWord: '条目' })

const emit = defineEmits<{ (e: 'update:modelValue', v: boolean): void }>()

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const target = ref<number | null>(null)
const loading = ref(false)
const treeProps = { label: 'label', children: 'children' }

// 每次打开重置目标选择
watch(() => props.modelValue, (v) => {
  if (v) target.value = null
})

async function confirm() {
  if (target.value === null) {
    ElMessage.warning('请选择目标分组')
    return
  }
  loading.value = true
  try {
    // id=0 是「未分组」虚拟节点 → null
    await props.move(target.value === 0 ? null : target.value)
    visible.value = false
  } catch (e: any) {
    ElMessage.error(e.message || '批量移动失败')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <el-dialog v-model="visible" title="批量移动到分组" width="420px" align-center :close-on-click-modal="false">
    <div style="margin-bottom: 12px; color: var(--app-text-muted);">
      将 {{ count }} 个{{ itemWord }}移动到：
    </div>
    <el-tree-select
      v-model="target"
      :data="treeData"
      node-key="id"
      :props="treeProps"
      placeholder="选择目标分组 / 输入搜索"
      clearable
      filterable
      check-strictly
      style="width: 100%"
    />
    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" :loading="loading" @click="confirm">确定移动</el-button>
    </template>
  </el-dialog>
</template>

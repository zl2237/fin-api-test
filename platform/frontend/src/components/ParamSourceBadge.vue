<template>
  <div class="psb-wrap">
    <el-popover
      placement="bottom"
      :width="420"
      trigger="click"
      :persistent="false"
      popper-class="psb-popover"
    >
      <template #reference>
        <div class="psb" :class="{ 'psb-empty': isEmpty }" title="点击配置取值来源">
          <el-tag :type="tagType" size="small" disable-transitions class="psb-tag">{{ tagLabel }}</el-tag>
          <span class="psb-summary" v-html="summary" />
        </div>
      </template>
      <ParamSourceForm
        :model-value="modelValue"
        :ref-groups="refGroups"
        :ban-sql="banSql"
        :placeholder="placeholder"
        :file-field="fileField"
        @update:model-value="(v) => emit('update:modelValue', v)"
        @open-picker="filePickerVisible = true"
      />
    </el-popover>
    <!-- 文件选择器挂在徽标层（popover 组件树之外）：放 popover 内容里时，点击
         弹窗会被判定 popover 外部点击 → popover 关闭连累弹窗被销毁、选择丢失 -->
    <FilePicker
      v-if="fileField"
      v-model="filePickerVisible"
      :model-file-id="fileIdNum"
      @select="onFileSelect"
    />
  </div>
</template>

<script setup lang="ts">
/** 表格内联四来源编辑：来源徽标 + 摘要，点击弹层完整编辑（ParamSourceForm）。 */
import { computed, ref } from 'vue'
import type { ParamSpec, TestFile } from '@/api'
import FilePicker from './FilePicker.vue'
import ParamSourceForm from './ParamSourceForm.vue'
import type { RefVarGroup } from './VarRefSelect.vue'
import { funcMeta } from '@/constants/funcRegistry'
import { isParamSpec, toFileId } from '@/utils/paramSource'

const props = withDefaults(defineProps<{
  modelValue: any
  refGroups?: RefVarGroup[]
  banSql?: boolean
  placeholder?: string
  /** 字段类型为 file：常量摘要显示「文件#ID」，编辑表单提供文件选择器 */
  fileField?: boolean
}>(), {
  refGroups: () => [],
  banSql: false,
  placeholder: '输入常量值',
  fileField: false,
})
const emit = defineEmits<{ (e: 'update:modelValue', v: ParamSpec): void }>()

const isSpec = isParamSpec

const spec = computed<ParamSpec>(() => {
  if (isSpec(props.modelValue)) return props.modelValue
  return { source: 'constant', value: props.modelValue }
})

const tagType = computed(() =>
  ({ constant: 'info', ref: 'success', func: 'warning', sql: 'danger' })[spec.value.source] || 'info')
const tagLabel = computed(() =>
  ({ constant: '常量', ref: '引用', func: '函数', sql: 'SQL' })[spec.value.source] || spec.value.source)

function esc(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

// 常量容器（整组对象/数组，单行可达几十 KB）的 stringify 摘要缓存：
// value 引用不变（未编辑）时重渲染免重算——200 行表的全表重渲染热点
const summaryCache = new WeakMap<object, string>()

function containerSummary(v: object): string {
  let s = summaryCache.get(v)
  if (s === undefined) {
    s = JSON.stringify(v) ?? ''
    summaryCache.set(v, s)
  }
  return s
}

/** 引用摘要显示节点中文名（node_id 形如 node_178xxxx 可读性差）；
 * refGroups 查不到时回退 node_id（跨页面引用等场景） */
const refLabelCache = computed(() => {
  const m: Record<string, string> = {}
  for (const g of props.refGroups || []) {
    for (const it of g.items || []) {
      if (it.node_id && !(it.node_id in m)) m[it.node_id] = it.node_label || it.node_id
    }
  }
  return m
})

const summary = computed(() => {
  const s = spec.value
  const MAX = 42
  const cut = (t: string) => (t.length > MAX ? esc(t.slice(0, MAX)) + '<i>…</i>' : esc(t))
  if (s.source === 'constant') {
    const v = s.value
    if (v === '' || v === null || v === undefined) return '<span class="psb-dim">（空）</span>'
    if (props.fileField) return `<span class="psb-dim">文件</span><b>#${cut(String(v))}</b>`
    if (typeof v === 'object') {
      return cut(containerSummary(v))
    }
    return cut(String(v))
  }
  if (s.source === 'ref') {
    const arr = s.as_array ? ' <span class="psb-dim">[包数组]</span>' : ''
    const who = refLabelCache.value[s.node_id || ''] || s.node_id || '?'
    return `<b>${cut(who)}<span class="psb-dim">.</span>${cut(s.var_path || '?')}</b>${arr}`
  }
  if (s.source === 'func') {
    const m = funcMeta(s.func || '')
    return `<b>${m?.label || s.func || '?'}</b> <span class="psb-dim">(${(s.args || [])
      .map((a) => (a.kind === 'ref' ? `${a.name}=ref` : `${a.name}=${String(a.value ?? '')}`)).join(', ')})</span>`
  }
  if (s.source === 'sql') {
    const col = s.column ? ` → ${esc(s.column)}` : ''
    return `<b>SQL</b>${col} <span class="psb-dim">${cut((s.sql || '').replace(/\s+/g, ' '))}</span>`
  }
  return ''
})

const isEmpty = computed(() => {
  const s = spec.value
  if (s.source === 'constant') return s.value === '' || s.value === null || s.value === undefined
  return false
})

// ===== 文件字段：文件中心选择器（弹层外持有，选中后以 constant file_id 提交） =====
const filePickerVisible = ref(false)
const fileIdNum = computed(() =>
  spec.value.source === 'constant' ? toFileId(spec.value.value) : null)
function onFileSelect(f: TestFile) {
  emit('update:modelValue', { source: 'constant', value: String(f.id) })
}
</script>

<style scoped>
.psb-wrap {
  display: flex;
  align-items: center;
  min-width: 0;
}
.psb {
  display: flex;
  flex: 1;
  min-width: 0;
  align-items: center;
  gap: 6px;
  min-height: 24px;
  padding: 2px 6px;
  border: 1px solid var(--app-border);
  border-radius: 5px;
  cursor: pointer;
  background: var(--app-bg, #fff);
  overflow: hidden;
}
.psb:hover {
  border-color: var(--app-primary);
}
.psb-empty {
  border-style: dashed;
}
.psb-tag {
  flex-shrink: 0;
}
.psb-summary {
  flex: 1;
  min-width: 0;
  font-size: 12px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  line-height: 1.4;
}
</style>
<style>
.psb-popover .psb-dim {
  color: var(--app-text-muted);
  font-style: normal;
  font-size: 12px;
}
</style>

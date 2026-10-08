<template>
  <el-select
    :model-value="encoded"
    filterable
    :placeholder="placeholder"
    :size="size"
    style="width: 100%"
    @update:model-value="onPick"
  >
    <template v-if="!matched && modelValue?.node_id && modelValue?.var_path">
      <!-- 当前值不在可选组（如 __suite__ 白名单运行期注入）：保留回显防止显示空白 -->
      <el-option :value="encoded" :label="rawLabel">
        <span class="dim">{{ rawLabel }}</span>
        <span class="dim-tag">（保存于配置，本页不可选）</span>
      </el-option>
    </template>
    <el-option-group
      v-for="grp in groups"
      :key="grp.key"
      :label="grp.label"
    >
      <template v-for="item in grp.items" :key="item.node_id">
        <el-option
          v-for="v in item.vars"
          :key="item.node_id + '.' + v.path"
          :value="encode(item.node_id, v.path)"
          :label="`${item.node_label} · ${v.path}`"
        >
          <span class="node-tag">{{ item.node_label }}</span>
          <span>{{ v.path }}</span>
          <span v-if="v.label" class="dim">（{{ v.label }}）</span>
        </el-option>
      </template>
    </el-option-group>
  </el-select>
</template>

<script setup lang="ts">
/** 四来源引用选择器（来源3）：分组下拉选「节点.变量」，
 *  禁止手输 —— 数据源由父级（CaseDesigner 上游产出/数据集/套件）组装。 */
import { computed } from 'vue'

export interface RefVarItem {
  node_id: string
  node_label: string
  vars: { path: string; label?: string }[]
}
export interface RefVarGroup {
  key: string
  label: string
  items: RefVarItem[]
}

const props = withDefaults(defineProps<{
  modelValue: { node_id?: string; var_path?: string } | null | undefined
  groups: RefVarGroup[]
  placeholder?: string
  size?: 'small' | 'default'
}>(), {
  placeholder: '选择上游节点变量',
  size: 'small',
})
const emit = defineEmits<{
  (e: 'update:modelValue', v: { node_id: string; var_path: string }): void
}>()

const SEP = '\u0001'
const encode = (node: string, path: string) => `${node}${SEP}${path}`

const encoded = computed(() => {
  const m = props.modelValue
  return m?.node_id && m?.var_path ? encode(m.node_id, m.var_path) : ''
})

const matched = computed(() => {
  const m = props.modelValue
  if (!m?.node_id || !m?.var_path) return true
  return props.groups.some((g) => g.items.some(
    (it) => it.node_id === m.node_id && it.vars.some((v) => v.path === m.var_path),
  ))
})

const rawLabel = computed(() => {
  const m = props.modelValue
  return m?.node_id && m?.var_path ? `${m.node_id}.${m.var_path}` : ''
})

function onPick(v: string) {
  const [node_id, var_path] = v.split(SEP)
  if (node_id && var_path) emit('update:modelValue', { node_id, var_path })
}
</script>

<style scoped>
.dim {
  color: var(--app-text-muted);
  font-size: 12px;
}
.dim-tag {
  color: var(--app-warning, #e6a23c);
  font-size: 12px;
  margin-left: 4px;
}
.node-tag {
  background: var(--app-hover);
  border-radius: 3px;
  padding: 0 5px;
  margin-right: 6px;
  font-size: 12px;
}
</style>

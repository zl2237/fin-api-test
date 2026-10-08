<template>
  <el-select
    :model-value="encoded"
    filterable
    remote
    :remote-method="onSearch"
    :placeholder="placeholder"
    :size="size"
    style="width: 100%"
    @update:model-value="onPick"
    @visible-change="(v: boolean) => v && onSearch('')"
  >
    <template v-if="!matched && modelValue?.node_id && modelValue?.var_path">
      <!-- 当前值不在可选组（如 __suite__ 白名单运行期注入）：保留回显防止显示空白 -->
      <el-option :value="encoded" :label="rawLabel">
        <span class="dim">{{ rawLabel }}</span>
        <span class="dim-tag">（保存于配置，本页不可选）</span>
      </el-option>
    </template>
    <el-option-group
      v-for="grp in shownGroups"
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
    <el-option v-if="shownCount < totalCount" disabled value="__more__" label="__more__">
      <span class="dim-tag">已显示前 {{ shownCount }} 条（共 {{ totalCount }}），输入关键字缩小范围</span>
    </el-option>
  </el-select>
</template>

<script setup lang="ts">
/** 四来源引用选择器（来源3）：分组下拉选「节点.变量」，
 *  禁止手输 —— 数据源由父级（CaseDesigner 上游产出/数据集/套件）组装。
 *  变量可达数千（前序节点全部入参+提取），el-select 全量渲染 option 会卡——
 *  remote 搜索模式自管过滤 + 截断渲染，当前选中项被截断时单独置顶保回显。 */
import { computed, ref } from 'vue'

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

// ===== remote 搜索 + 截断渲染 =====
const keyword = ref('')
function onSearch(q: string) {
  keyword.value = q
}

/** 单次渲染 option 上限：超出靠搜索定位 */
const LIMIT = 200

const filteredGroups = computed<RefVarGroup[]>(() => {
  const q = keyword.value.trim().toLowerCase()
  if (!q) return props.groups
  return props.groups
    .map((g) => ({
      ...g,
      items: g.items
        .map((it) => ({
          ...it,
          vars: it.vars.filter(
            (v) =>
              v.path.toLowerCase().includes(q) ||
              it.node_label.toLowerCase().includes(q) ||
              (v.label || '').toLowerCase().includes(q),
          ),
        }))
        .filter((it) => it.vars.length),
    }))
    .filter((g) => g.items.length)
})

const totalCount = computed(() =>
  filteredGroups.value.reduce((n, g) => n + g.items.reduce((m, it) => m + it.vars.length, 0), 0))

/** 截断至 LIMIT 条；当前选中项被截掉时从全量中补回置顶，保证 el-select 回显正常 */
const shownGroups = computed<RefVarGroup[]>(() => {
  const out: RefVarGroup[] = []
  let count = 0
  for (const g of filteredGroups.value) {
    if (count >= LIMIT) break
    const items: RefVarItem[] = []
    for (const it of g.items) {
      if (count >= LIMIT) break
      const take = it.vars.slice(0, LIMIT - count)
      count += take.length
      items.push({ ...it, vars: take })
    }
    if (items.length) out.push({ ...g, items })
  }
  const m = props.modelValue
  if (m?.node_id && m?.var_path && matched.value) {
    const included = out.some((g) => g.items.some(
      (it) => it.node_id === m.node_id && it.vars.some((v) => v.path === m.var_path),
    ))
    if (!included) {
      for (const g of props.groups) {
        const it = g.items.find((x) => x.node_id === m.node_id)
        const v = it?.vars.find((x) => x.path === m.var_path)
        if (it && v) {
          out.unshift({ key: '__cur__', label: '当前选中', items: [{ node_id: it.node_id, node_label: it.node_label, vars: [v] }] })
          break
        }
      }
    }
  }
  return out
})

const shownCount = computed(() =>
  shownGroups.value.reduce((n, g) => n + g.items.reduce((m, it) => m + it.vars.length, 0), 0))

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

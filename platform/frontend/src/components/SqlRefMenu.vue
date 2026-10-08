<template>
  <el-popover
    v-if="groups && groups.length"
    trigger="click"
    placement="bottom-end"
    :width="360"
    :persistent="false"
    popper-class="srm-popper"
  >
    <template #reference>
      <span class="srm-link" title="插入 {{节点.变量}} 引用到 SQL 末尾">+ 插入引用</span>
    </template>

    <div class="srm-body">
      <el-input
        v-model="keyword"
        size="small"
        clearable
        placeholder="搜索节点 / 变量名"
        class="srm-search"
      >
        <template #prefix><el-icon><Search /></el-icon></template>
      </el-input>
      <!-- 滚动收敛在弹层内部列表：滚动不触发外部 click-outside，下拉不再被异常关闭；
           渲染截断至 LIMIT 条，变量数千时打开不卡，靠关键字缩小范围 -->
      <div class="srm-list">
        <template v-for="row in visibleRows" :key="row.key">
          <div v-if="row.kind === 'title'" class="srm-title">{{ row.label }}</div>
          <div
            v-else
            class="srm-item"
            :title="`{{${row.node_id}.${row.path}}}`"
            @click="onPick(row.node_id!, row.path!)"
          >
            <span class="srm-node">{{ row.node_label }}</span>
            <span class="srm-dim">.</span>
            <span class="srm-var">{{ row.path }}</span>
            <span v-if="row.vlabel" class="srm-dim">（{{ row.vlabel }}）</span>
          </div>
        </template>
        <div v-if="!totalVars" class="srm-empty">无匹配变量</div>
        <div v-else-if="shownVars < totalVars" class="srm-more">
          已显示前 {{ shownVars }} 条（共 {{ totalVars }}），输入关键字缩小范围
        </div>
      </div>
    </div>
  </el-popover>
</template>

<script setup lang="ts">
/** {{节点.变量}} 引用插入弹层：后置提取 / DB 断言 SQL 旁复用。
 *  旧版 el-dropdown 在弹层内滚动几百个变量时会被判定外部点击而异常关闭，
 *  且无搜索——改为自管弹层：顶部搜索框双向过滤 + 内部列表滚动。
 *  变量可达数千（前序节点全部入参+提取），DOM 全量渲染会卡——摊平为行数组后截断渲染。 */
import { computed, ref } from 'vue'
import { Search } from '@element-plus/icons-vue'
import type { RefVarGroup } from './VarRefSelect.vue'

const props = defineProps<{ groups?: RefVarGroup[] }>()
const emit = defineEmits<{ (e: 'insert', text: string): void }>()

const keyword = ref('')

/** 单次渲染上限：超出部分靠搜索定位 */
const LIMIT = 120

type Row =
  | { kind: 'title'; key: string; label: string }
  | { kind: 'var'; key: string; node_id: string; node_label: string; path: string; vlabel?: string }

const allRows = computed<Row[]>(() => {
  const q = keyword.value.trim().toLowerCase()
  const rows: Row[] = []
  for (const g of props.groups || []) {
    const items = g.items
      .map((it) => ({
        ...it,
        vars: q
          ? it.vars.filter(
              (v) =>
                v.path.toLowerCase().includes(q) ||
                (it.node_label || '').toLowerCase().includes(q) ||
                (v.label || '').toLowerCase().includes(q),
            )
          : it.vars,
      }))
      .filter((it) => it.vars.length)
    if (!items.length) continue
    rows.push({ kind: 'title', key: `t:${g.key}`, label: g.label })
    for (const it of items)
      for (const v of it.vars)
        rows.push({
          kind: 'var',
          key: `${g.key}:${it.node_id}:${v.path}`,
          node_id: it.node_id,
          node_label: it.node_label,
          path: v.path,
          vlabel: v.label,
        })
  }
  return rows
})

const visibleRows = computed(() => allRows.value.slice(0, LIMIT))
const totalVars = computed(() => allRows.value.reduce((n, r) => (r.kind === 'var' ? n + 1 : n), 0))
const shownVars = computed(() => visibleRows.value.reduce((n, r) => (r.kind === 'var' ? n + 1 : n), 0))

function onPick(node_id: string, path: string) {
  emit('insert', `{{${node_id}.${path}}}`)
  keyword.value = ''
}
</script>

<style scoped>
.srm-link {
  font-size: 12px;
  color: var(--el-color-primary);
  cursor: pointer;
  white-space: nowrap;
}
.srm-link:hover {
  opacity: 0.8;
}
</style>
<style>
.srm-popper .srm-body {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.srm-popper .srm-list {
  max-height: 300px;
  overflow-y: auto;
}
.srm-popper .srm-title {
  padding: 4px 4px 2px;
  font-size: 12px;
  color: var(--app-text-muted, #909399);
}
.srm-popper .srm-item {
  display: flex;
  align-items: center;
  gap: 2px;
  padding: 4px 6px;
  font-size: 12px;
  border-radius: 4px;
  cursor: pointer;
  min-width: 0;
}
.srm-popper .srm-item:hover {
  background: var(--app-hover, #f5f7fa);
}
.srm-popper .srm-node {
  flex-shrink: 0;
  color: var(--app-text-muted, #909399);
}
.srm-popper .srm-var {
  font-family: var(--app-font-mono, monospace);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.srm-popper .srm-dim {
  color: var(--app-text-muted, #909399);
  font-size: 12px;
  flex-shrink: 0;
}
.srm-popper .srm-empty {
  padding: 12px 0;
  text-align: center;
  font-size: 12px;
  color: var(--app-text-faint, #c0c4cc);
}
.srm-popper .srm-more {
  padding: 6px 0 4px;
  text-align: center;
  font-size: 12px;
  color: var(--app-text-faint, #c0c4cc);
}
</style>

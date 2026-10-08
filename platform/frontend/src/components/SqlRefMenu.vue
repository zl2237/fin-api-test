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
      <!-- 滚动收敛在弹层内部列表：滚动不触发外部 click-outside，下拉不再被异常关闭 -->
      <div class="srm-list">
        <template v-for="g in filtered" :key="g.key">
          <div class="srm-title">{{ g.label }}</div>
          <template v-for="item in g.items" :key="g.key + ':' + item.node_id">
            <div
              v-for="v in item.vars"
              :key="g.key + ':' + item.node_id + ':' + v.path"
              class="srm-item"
              :title="`{{${item.node_id}.${v.path}}}`"
              @click="onPick(item, v)"
            >
              <span class="srm-node">{{ item.node_label }}</span>
              <span class="srm-dim">.</span>
              <span class="srm-var">{{ v.path }}</span>
              <span v-if="v.label" class="srm-dim">（{{ v.label }}）</span>
            </div>
          </template>
        </template>
        <div v-if="!filtered.length" class="srm-empty">无匹配变量</div>
      </div>
    </div>
  </el-popover>
</template>

<script setup lang="ts">
/** {{节点.变量}} 引用插入弹层：后置提取 / DB 断言 SQL 旁复用。
 *  旧版 el-dropdown 在弹层内滚动几百个变量时会被判定外部点击而异常关闭，
 *  且无搜索——改为自管弹层：顶部搜索框双向过滤 + 内部列表滚动。 */
import { computed, ref } from 'vue'
import { Search } from '@element-plus/icons-vue'
import type { RefVarGroup } from './VarRefSelect.vue'

const props = defineProps<{ groups?: RefVarGroup[] }>()
const emit = defineEmits<{ (e: 'insert', text: string): void }>()

const keyword = ref('')

const filtered = computed(() => {
  const q = keyword.value.trim().toLowerCase()
  if (!q) return props.groups || []
  return (props.groups || [])
    .map((g) => ({
      ...g,
      items: g.items
        .map((it) => ({
          ...it,
          vars: it.vars.filter(
            (v) =>
              v.path.toLowerCase().includes(q) ||
              (it.node_label || '').toLowerCase().includes(q) ||
              (v.label || '').toLowerCase().includes(q),
          ),
        }))
        .filter((it) => it.vars.length),
    }))
    .filter((g) => g.items.length)
})

function onPick(item: { node_id: string }, v: { path: string }) {
  emit('insert', `{{${item.node_id}.${v.path}}}`)
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
</style>

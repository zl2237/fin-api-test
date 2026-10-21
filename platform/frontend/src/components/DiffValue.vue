<template>
  <span v-if="side === 'expected'" class="diff-inline" :class="{ 'has-mark': expectedHasMark }">
    <template v-for="(s, i) in expectedSegs" :key="i">
      <span v-if="s.kind === 'del'" class="diff-del">{{ s.text }}</span>
      <template v-else>{{ s.text }}</template>
    </template>
  </span>
  <span v-else-if="side === 'actual'" class="diff-inline" :class="{ 'has-mark': actualHasMark }">
    <template v-for="(s, i) in actualSegs" :key="i">
      <span v-if="s.kind === 'add'" class="diff-add">{{ s.text }}</span>
      <template v-else>{{ s.text }}</template>
    </template>
  </span>
  <div v-else class="diff-block">
    <div class="diff-line">
      <span class="diff-key diff-key-exp">期望</span>
      <code class="diff-text">
        <template v-for="(s, i) in expectedSegs" :key="i">
          <span v-if="s.kind === 'del'" class="diff-del">{{ s.text }}</span>
          <template v-else>{{ s.text }}</template>
        </template>
      </code>
    </div>
    <div class="diff-line">
      <span class="diff-key diff-key-act">实际</span>
      <code class="diff-text">
        <template v-for="(s, i) in actualSegs" :key="i">
          <span v-if="s.kind === 'add'" class="diff-add">{{ s.text }}</span>
          <template v-else>{{ s.text }}</template>
        </template>
      </code>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { textDiff } from '@/utils/textDiff'

/**
 * 断言期望/实际值差异渲染：
 * - side='expected' | 'actual'：行内单侧（报告表格单元格用，del 划线红 / add 高亮绿）
 * - side='both'（默认）：双行对照块（值查看弹窗用，期望行 + 实际行）
 * diff 计算是纯函数，两侧传同一对值即可分别渲染各自侧。
 */
const props = withDefaults(defineProps<{
  expected: string | null | undefined
  actual: string | null | undefined
  side?: 'expected' | 'actual' | 'both'
}>(), {
  side: 'both',
})

function toStr(v: string | null | undefined): string {
  return v == null ? '' : String(v)
}

const diff = computed(() => textDiff(toStr(props.expected), toStr(props.actual)))
const expectedSegs = computed(() => diff.value.expected)
const actualSegs = computed(() => diff.value.actual)
const expectedHasMark = computed(() => expectedSegs.value.some(s => s.kind === 'del'))
const actualHasMark = computed(() => actualSegs.value.some(s => s.kind === 'add'))
</script>

<style scoped>
/* 行内模式：继承宿主单元格的 mono 字号，仅给差异片段上底色 */
.diff-inline {
  white-space: pre-wrap;
  word-break: break-all;
}
.diff-del {
  background: var(--app-danger-bg);
  color: var(--app-danger-text);
  text-decoration: line-through;
  text-decoration-thickness: 1px;
  border-radius: 2px;
  padding: 0 1px;
}
.diff-add {
  background: var(--app-success-bg);
  color: var(--app-success-text);
  border-radius: 2px;
  padding: 0 1px;
}

/* 双行对照模式（弹窗）：mono 双行，键标签用状态色小签 */
.diff-block {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.diff-line {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  min-width: 0;
}
.diff-key {
  flex-shrink: 0;
  font-size: 12px;
  font-weight: 600;
  line-height: 20px;
  padding: 0 6px;
  border-radius: var(--app-radius-sm);
}
.diff-key-exp {
  color: var(--app-danger-text);
  background: var(--app-danger-bg);
}
.diff-key-act {
  color: var(--app-success-text);
  background: var(--app-success-bg);
}
.diff-text {
  flex: 1;
  min-width: 0;
  margin: 0;
  font-size: 12px;
  line-height: 20px;
  white-space: pre-wrap;
  word-break: break-all;
  color: var(--app-text);
}
</style>

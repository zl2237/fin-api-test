<template>
  <button
    type="button"
    class="copy-btn"
    :class="{ 'is-ok': copied }"
    :title="copied ? '已复制' : title"
    :aria-label="title"
    @click.stop="onCopy"
  >
    <!-- 复制 icon → 对勾按笔画顺序绘制（DrawCheck）：成功反馈就地呈现，不再弹 toast/弹窗 -->
    <DrawCheck v-if="copied" :size="size" />
    <el-icon v-else :size="size">
      <CopyDocument />
    </el-icon>
  </button>
</template>

<script setup lang="ts">
import { ElMessage } from 'element-plus'
import { CopyDocument } from '@element-plus/icons-vue'
import { writeClipboard } from '@/utils/clipboard'
import DrawCheck from './DrawCheck.vue'
import { useTransientFlag } from '@/composables/useTransientFlag'

const props = withDefaults(
  defineProps<{
    /** 复制内容：对象/数组按 2 空格缩进 JSON 序列化，其余转字符串；空值点击静默忽略 */
    value: unknown
    /** 悬浮提示文案（复制成功瞬间切换为「已复制」） */
    title?: string
    /** icon 尺寸（px），与所在单元格字号匹配 */
    size?: number
  }>(),
  { title: '复制', size: 13 },
)

/** 对勾总停留时长：笔画绘制 ~0.46s + 完整对勾停留 ~1s，看清反馈又不打断连续复制 */
const { active: copied, trigger: markCopied } = useTransientFlag(1500)

async function onCopy() {
  const v = props.value
  const text = v != null && typeof v === 'object' ? JSON.stringify(v, null, 2) : String(v ?? '')
  if (!text) return
  if (!(await writeClipboard(text))) {
    ElMessage.error('复制失败，请手动选择复制')
    return
  }
  markCopied()
}
</script>

<style scoped>
.copy-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  padding: 2px;
  border: none;
  background: transparent;
  cursor: pointer;
  border-radius: var(--app-radius-xs, 4px);
  color: var(--app-text-faint);
  vertical-align: middle;
  transition: color 0.15s ease;
}
.copy-btn:hover {
  color: var(--el-color-primary);
}
/* 成功反馈期：对勾着成功色，指针事件保留（连续点击无害） */
.copy-btn.is-ok {
  color: var(--app-success-text);
}
</style>

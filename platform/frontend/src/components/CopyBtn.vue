<template>
  <button
    type="button"
    class="copy-btn"
    :class="{ 'is-ok': copied }"
    :title="copied ? '已复制' : title"
    :aria-label="title"
    @click.stop="onCopy"
  >
    <!-- 复制 icon → 对勾 icon 短暂切换：成功反馈就地呈现，不再弹 toast/弹窗 -->
    <el-icon :size="size">
      <CircleCheckFilled v-if="copied" />
      <CopyDocument v-else />
    </el-icon>
  </button>
</template>

<script setup lang="ts">
import { onUnmounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { CircleCheckFilled, CopyDocument } from '@element-plus/icons-vue'
import { writeClipboard } from '@/utils/clipboard'

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

/** 对勾停留时长：看清反馈又不打断连续复制多条 */
const CHECK_MS = 1200
const copied = ref(false)
let timer: ReturnType<typeof setTimeout> | null = null

async function onCopy() {
  const v = props.value
  const text = v != null && typeof v === 'object' ? JSON.stringify(v, null, 2) : String(v ?? '')
  if (!text) return
  if (!(await writeClipboard(text))) {
    ElMessage.error('复制失败，请手动选择复制')
    return
  }
  copied.value = true
  if (timer) clearTimeout(timer)
  timer = setTimeout(() => {
    copied.value = false
    timer = null
  }, CHECK_MS)
}

onUnmounted(() => {
  if (timer) clearTimeout(timer)
})
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

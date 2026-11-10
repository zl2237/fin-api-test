<template>
  <button
    type="button"
    class="copy-btn"
    :class="{ 'is-ok': copied }"
    :title="copied ? '已复制' : title"
    :aria-label="title"
    @click.stop="onCopy"
  >
    <!-- 复制 icon → 对勾按笔画顺序绘制（圆环先落笔、勾随后收笔）：成功反馈就地呈现，不再弹 toast/弹窗 -->
    <span v-if="copied" class="check-draw" :style="{ width: `${size}px`, height: `${size}px` }">
      <svg viewBox="0 0 14 14" fill="none" aria-hidden="true">
        <circle class="ck-circle" cx="7" cy="7" r="5.75" pathLength="100" />
        <path class="ck-check" d="M4.1 7.3 L6.2 9.3 L9.9 5.2" pathLength="100" />
      </svg>
    </span>
    <el-icon v-else :size="size">
      <CopyDocument />
    </el-icon>
  </button>
</template>

<script setup lang="ts">
import { onUnmounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { CopyDocument } from '@element-plus/icons-vue'
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

/** 对勾总停留时长：笔画绘制 ~0.46s + 完整对勾停留 ~1s，看清反馈又不打断连续复制 */
const CHECK_MS = 1500
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

/* 对勾描边绘制：pathLength=100 归一化长度，dash 从满偏移收到 0 即「沿笔画写出」 */
.check-draw {
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
.check-draw svg {
  display: block;
  width: 100%;
  height: 100%;
}
.ck-circle,
.ck-check {
  stroke: currentColor;
  stroke-width: 1.6;
  stroke-linecap: round;
  stroke-linejoin: round;
  stroke-dasharray: 100;
  stroke-dashoffset: 100;
}
/* 笔画顺序：圆环先画完，对勾再落笔（短重叠衔接自然） */
.ck-circle {
  animation: ck-stroke 0.28s ease-out forwards;
}
.ck-check {
  animation: ck-stroke 0.22s ease-out 0.24s forwards;
}
@keyframes ck-stroke {
  to {
    stroke-dashoffset: 0;
  }
}
/* 减弱动效偏好：跳过绘制过程直接呈现完整对勾 */
@media (prefers-reduced-motion: reduce) {
  .ck-circle,
  .ck-check {
    animation: none;
    stroke-dashoffset: 0;
  }
}
</style>

<template>
  <span class="check-draw" :style="{ width: `${size}px`, height: `${size}px` }">
    <svg viewBox="0 0 14 14" fill="none" aria-hidden="true">
      <circle class="ck-circle" cx="7" cy="7" r="5.75" pathLength="100" />
      <path class="ck-check" d="M4.1 7.3 L6.2 9.3 L9.9 5.2" pathLength="100" />
    </svg>
  </span>
</template>

<script setup lang="ts">
/** 按笔画顺序绘制的对勾：圆环先落笔画完、勾随后收笔（描边动画）。
 *  挂载即播放一次；配合 v-if 使用，条件重新满足即重挂重放。
 *  颜色随 currentColor，由使用方（按钮/图标位）着色。 */
withDefaults(defineProps<{ size?: number }>(), { size: 13 })
</script>

<style scoped>
/* 描边绘制：pathLength=100 归一化长度，dash 从满偏移收到 0 即「沿笔画写出」 */
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

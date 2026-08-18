<template>
  <div class="req-progress" :class="{ 'is-visible': progressState.visible }">
    <div class="req-progress-bar" :class="{ 'is-done': progressState.percent >= 100 }" :style="{ width: progressState.percent + '%' }">
      <!-- 完成时一道高光从左掠过 -->
      <span class="req-progress-peg" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { progressState } from '@/utils/requestProgress'
</script>

<style scoped>
.req-progress {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  height: 2px;
  z-index: 9999;
  pointer-events: none;
  opacity: 0;
  transition: opacity 0.2s ease;
}
.req-progress.is-visible {
  opacity: 1;
}
.req-progress-bar {
  position: relative;
  height: 100%;
  background: linear-gradient(90deg, #409eff, #67c23a);
  box-shadow: 0 0 8px rgba(64, 158, 255, 0.6);
  transition: width 0.2s ease;
  border-radius: 0 2px 2px 0;
  overflow: hidden;
}
/* 完成光泽：高光块平时停在左侧外，is-done 时从左向右扫过一次 */
.req-progress-peg {
  position: absolute;
  top: 0;
  left: -40%;
  width: 40%;
  height: 100%;
  background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.85), transparent);
  transform: skewX(-20deg);
}
.req-progress-bar.is-done .req-progress-peg {
  animation: peg-sweep 0.4s ease-out 1;
}
@keyframes peg-sweep {
  from { left: -40%; }
  to { left: 110%; }
}
@media (prefers-reduced-motion: reduce) {
  .req-progress-bar.is-done .req-progress-peg {
    animation: none;
  }
}
</style>

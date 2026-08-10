<template>
  <div class="req-progress" :class="{ 'is-visible': progressState.visible }">
    <div class="req-progress-bar" :style="{ width: progressState.percent + '%' }" />
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
  height: 100%;
  background: linear-gradient(90deg, #409eff, #67c23a);
  box-shadow: 0 0 8px rgba(64, 158, 255, 0.6);
  transition: width 0.2s ease;
  border-radius: 0 2px 2px 0;
}
</style>

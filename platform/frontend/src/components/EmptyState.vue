<template>
  <div class="empty-state" :style="{ '--es-size': size + 'px' }">
    <svg
      class="empty-state-illust"
      :width="size"
      :height="size"
      viewBox="0 0 120 120"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
    >
      <defs>
        <linearGradient :id="gradId" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stop-color="#409eff" stop-opacity="0.9" />
          <stop offset="100%" stop-color="#2b7fd6" stop-opacity="0.7" />
        </linearGradient>
        <linearGradient :id="gradId + '-soft'" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="#409eff" stop-opacity="0.15" />
          <stop offset="100%" stop-color="#409eff" stop-opacity="0.03" />
        </linearGradient>
      </defs>
      <!-- 底部光晕 -->
      <ellipse cx="60" cy="100" rx="38" ry="6" :fill="`url(#${gradId}-soft)`" />
      <!-- 文件夹后片 -->
      <path
        d="M24 38 Q24 32 30 32 L48 32 L54 40 L90 40 Q96 40 96 46 L96 86 Q96 92 90 92 L30 92 Q24 92 24 86 Z"
        :fill="`url(#${gradId}-soft)`"
        :stroke="`url(#${gradId})`"
        stroke-width="2"
        stroke-linejoin="round"
      />
      <!-- 文件夹前片（打开状态，略低） -->
      <path
        d="M24 50 Q24 45 29 45 L95 45 L100 45 Q102 45 101 47 L96 88 Q95 92 90 92 L30 92 Q24 92 24 86 Z"
        fill="var(--app-card, #fff)"
        :stroke="`url(#${gradId})`"
        stroke-width="2"
        stroke-linejoin="round"
      />
      <!-- 虚线表示「空」 -->
      <line x1="42" y1="62" x2="78" y2="62" stroke="#409eff" stroke-width="1.5" stroke-dasharray="3 4" stroke-linecap="round" opacity="0.5" />
      <line x1="48" y1="72" x2="72" y2="72" stroke="#409eff" stroke-width="1.5" stroke-dasharray="3 4" stroke-linecap="round" opacity="0.35" />
      <!-- 右上角小圆点装饰 -->
      <circle cx="92" cy="28" r="3" fill="#67c23a" opacity="0.8" />
      <circle cx="100" cy="34" r="2" fill="#409eff" opacity="0.5" />
    </svg>
    <p v-if="description" class="empty-state-desc">{{ description }}</p>
    <div v-if="$slots.default" class="empty-state-actions">
      <slot />
    </div>
  </div>
</template>

<script setup lang="ts">
import { useId } from 'vue'

const props = withDefaults(defineProps<{
  description?: string
  imageSize?: number
}>(), {
  description: '',
  imageSize: 60,
})

const size = props.imageSize
// 唯一 ID 防止多实例渐变冲突
const gradId = 'es-' + useId()
</script>

<style scoped>
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 24px 12px;
  gap: 8px;
}
.empty-state-illust {
  flex-shrink: 0;
  /* 轻微浮动动画，增加生气 */
  animation: es-float 3s ease-in-out infinite;
}
@keyframes es-float {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-3px); }
}
.empty-state-desc {
  margin: 0;
  font-size: 13px;
  color: var(--app-text-muted);
  text-align: center;
}
.empty-state-actions {
  display: flex;
  gap: 8px;
  margin-top: 4px;
}
@media (prefers-reduced-motion: reduce) {
  .empty-state-illust {
    animation: none;
  }
}
</style>

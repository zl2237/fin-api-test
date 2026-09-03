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
          <stop offset="0%" class="es-grad-main" stop-opacity="0.9" />
          <stop offset="100%" class="es-grad-deep" stop-opacity="0.7" />
        </linearGradient>
        <linearGradient :id="gradId + '-soft'" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" class="es-grad-main" stop-opacity="0.15" />
          <stop offset="100%" class="es-grad-main" stop-opacity="0.03" />
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
        class="es-fill-card"
        :stroke="`url(#${gradId})`"
        stroke-width="2"
        stroke-linejoin="round"
      />
      <!-- 虚线表示「空」 -->
      <line x1="42" y1="62" x2="78" y2="62" class="es-stroke-primary" stroke-width="1.5" stroke-dasharray="3 4" stroke-linecap="round" opacity="0.5" />
      <line x1="48" y1="72" x2="72" y2="72" class="es-stroke-primary" stroke-width="1.5" stroke-dasharray="3 4" stroke-linecap="round" opacity="0.35" />
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
  /* 静态呈现：空态在工具页高频出现，不做入场演出 */
}
.empty-state-illust {
  flex-shrink: 0;
}
.empty-state-desc {
  margin: 0;
  font-size: 13px;
  color: var(--app-text-muted);
  text-align: center;
}
/* 插画取色统一走设计 token：SVG 呈现属性不支持 var()/color-mix()，颜色经 CSS 类注入，浅色/深色主题自适应 */
.es-grad-main {
  stop-color: var(--app-primary);
}
/* 主色深一档（渐变收尾站）：无独立深色 token，由主色派生，深浅主题均可用 */
.es-grad-deep {
  stop-color: color-mix(in srgb, var(--app-primary) 85%, black);
}
.es-stroke-primary {
  stroke: var(--app-primary);
}
/* 文件夹前片：实底卡色，遮住后片渐变形成层次 */
.es-fill-card {
  fill: var(--app-card-solid);
}
.empty-state-actions {
  display: flex;
  gap: 8px;
  margin-top: 4px;
}
</style>

<template>
  <span class="env-badge" :class="'tone-' + tone" :title="toneTitle">
    <span class="env-dot" />
    <span class="env-name">{{ name || (id != null ? `#${id}` : '—') }}</span>
  </span>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { envTone, type EnvTone } from '@/utils/envTone'

const props = defineProps<{
  name?: string | null
  id?: number | null
}>()

const tone = computed<EnvTone>(() => envTone(props.name))

const TONE_TITLE: Record<EnvTone, string> = {
  test: '测试环境',
  pre: '预发环境',
  prod: '生产环境（高风险）',
  unknown: '',
}
const toneTitle = computed(() => {
  const t = TONE_TITLE[tone.value]
  return t && props.name ? `${props.name} · ${t}` : props.name || ''
})
</script>

<style scoped>
/* 环境色点徽章：色点 + 环境名（纯文字，不做 tag 底——与状态 tag 拉开视觉层次） */
.env-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}
.env-dot {
  flex-shrink: 0;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--app-text-faint);
}
.tone-test .env-dot {
  background: var(--app-env-test);
}
.tone-pre .env-dot {
  background: var(--app-env-pre);
}
/* prod：实心红点 + 外圈警示环，高风险一眼可辨 */
.tone-prod .env-dot {
  position: relative;
  background: var(--app-env-prod);
}
.tone-prod .env-dot::after {
  content: '';
  position: absolute;
  inset: -3px;
  border-radius: 50%;
  border: 1px solid color-mix(in srgb, var(--app-env-prod) 45%, transparent);
}
.env-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.tone-prod .env-name {
  color: var(--app-danger-text);
  font-weight: 500;
}
</style>

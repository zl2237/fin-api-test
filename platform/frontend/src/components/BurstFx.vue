<template>
  <!-- 粒子迸发（提示词 4「点赞炸一下」的克制版）：一次性庆祝动效，无业务语义 -->
  <span v-if="bursting" class="burst-fx" aria-hidden="true">
    <i
      v-for="p in particles"
      :key="p.id"
      class="burst-dot"
      :style="{
        '--burst-angle': p.angle + 'deg',
        '--burst-dist': p.dist + 'px',
        '--burst-size': p.size + 'px',
        '--burst-delay': p.delay + 'ms',
        '--burst-color': p.color,
        animationDuration: p.duration + 'ms',
      }"
    />
  </span>
</template>

<script setup lang="ts">
/**
 * 粒子迸发效果：active 置 true 时以锚点为中心迸发一圈小圆点，单次播放后自动停止。
 *
 * - 纯展示组件：挂在徽章/图标旁（绝对定位铺满父级），不参与布局
 * - 随机角度/距离/大小/时长：每次迸发形态略有差异，避免机械感
 * - prefers-reduced-motion 时不渲染任何内容
 * - 重复触发：父级将 active 置 false 再置 true（本组件不做防抖，防重由调用方负责）
 */
import { ref, watch, onUnmounted } from 'vue'

const props = defineProps<{ active: boolean }>()

interface Particle {
  id: number
  angle: number
  dist: number
  size: number
  delay: number
  duration: number
  color: string
}

const bursting = ref(false)
const particles = ref<Particle[]>([])
let resetTimer: ReturnType<typeof setTimeout> | null = null

function prefersReducedMotion(): boolean {
  return typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

function buildParticles(): Particle[] {
  // 配色跟随平台语义色（成功场景的主色 + 两个邻近色阶），不引入新色相
  const colors = ['var(--app-primary)', 'var(--app-success)', 'currentColor']
  return Array.from({ length: 12 }, (_, i) => ({
    id: i,
    angle: i * 30 + Math.random() * 18, // 均匀撒 12 个方向 + 少量抖动
    dist: 26 + Math.random() * 22,
    size: 3 + Math.random() * 3,
    delay: Math.random() * 60,
    duration: 480 + Math.random() * 200,
    color: colors[i % colors.length],
  }))
}

watch(
  () => props.active,
  (on) => {
    if (resetTimer) {
      clearTimeout(resetTimer)
      resetTimer = null
    }
    if (!on || prefersReducedMotion()) {
      bursting.value = false
      particles.value = []
      return
    }
    particles.value = buildParticles()
    bursting.value = true
    // 最长动画（duration 上限 + delay 上限）后自清理
    resetTimer = setTimeout(() => {
      bursting.value = false
      particles.value = []
    }, 760)
  },
)

onUnmounted(() => {
  if (resetTimer) clearTimeout(resetTimer)
})
</script>

<style scoped>
.burst-fx {
  position: absolute;
  inset: 0;
  pointer-events: none;
  /* 锚点：迸发中心为父元素中心 */
  display: grid;
  place-items: center;
}
.burst-dot {
  position: absolute;
  width: var(--burst-size);
  height: var(--burst-size);
  border-radius: 50%;
  background: var(--burst-color);
  opacity: 0;
  animation: burst-fly cubic-bezier(0.16, 0.84, 0.44, 1) both;
  animation-delay: var(--burst-delay);
}
@keyframes burst-fly {
  0% {
    opacity: 1;
    transform: rotate(var(--burst-angle)) translateY(0) scale(1);
  }
  100% {
    opacity: 0;
    transform: rotate(var(--burst-angle)) translateY(calc(var(--burst-dist) * -1)) scale(0.4);
  }
}
@media (prefers-reduced-motion: reduce) {
  .burst-fx {
    display: none;
  }
}
</style>

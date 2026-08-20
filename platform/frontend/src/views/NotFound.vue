<template>
  <div class="nf-page">
    <main class="nf-card">
      <!-- 断链 DAG：品牌符号的 404 变体——编排还在，这条连线断了 -->
      <svg
        class="nf-illust"
        width="220"
        height="96"
        viewBox="0 0 220 96"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        role="img"
        aria-label="断开的用例编排连线"
      >
        <!-- 左侧：正常的两步编排 -->
        <rect
          x="10"
          y="38"
          width="26"
          height="18"
          rx="5"
          class="nf-fill-solid"
        />
        <rect
          x="82"
          y="12"
          width="26"
          height="18"
          rx="5"
          class="nf-fill-solid"
        />
        <rect
          x="82"
          y="66"
          width="26"
          height="18"
          rx="5"
          class="nf-fill-solid"
        />
        <path
          d="M36 47 C 56 47, 60 24, 82 21"
          class="nf-stroke"
          stroke-width="1.6"
        />
        <path
          d="M36 47 C 56 47, 60 78, 82 75"
          class="nf-stroke"
          stroke-width="1.6"
        />
        <!-- 右侧：到不了的目标（虚线空心） -->
        <rect
          x="184"
          y="39"
          width="26"
          height="18"
          rx="5"
          class="nf-stroke-dash"
          stroke-width="1.6"
          stroke-dasharray="4 4"
        />
        <!-- 断开的连线：两端戛然而止 -->
        <path
          d="M108 21 C 140 21, 150 30, 160 36"
          class="nf-stroke"
          stroke-width="1.6"
        />
        <path
          d="M108 75 C 140 75, 150 66, 160 60"
          class="nf-stroke"
          stroke-width="1.6"
        />
        <!-- 断口标记 -->
        <line
          x1="164"
          y1="42"
          x2="172"
          y2="54"
          class="nf-stroke-break"
          stroke-width="1.8"
          stroke-linecap="round"
        />
      </svg>
      <h1 class="nf-code">404</h1>
      <p class="nf-desc">页面不存在或已被移除</p>
      <div class="nf-actions">
        <el-button type="primary" @click="goHome">返回首页</el-button>
        <el-button @click="goBack">返回上一页</el-button>
      </div>
    </main>
  </div>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'

const router = useRouter()

function goHome() {
  router.push('/home')
}
function goBack() {
  // 无历史记录时回退等价于原地不动，兜底去首页
  if (window.history.state?.back) {
    router.back()
  } else {
    router.push('/home')
  }
}
</script>

<style scoped>
.nf-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--app-bg);
  padding: 24px;
}
.nf-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  padding: 48px 56px;
  background: var(--app-card-solid);
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius-lg);
  box-shadow: var(--app-shadow-sm);
  animation: nf-enter 0.45s cubic-bezier(0.25, 0.8, 0.25, 1) both;
}
@keyframes nf-enter {
  from {
    opacity: 0;
    transform: translateY(10px);
  }
  to {
    opacity: 1;
    transform: none;
  }
}
.nf-illust {
  margin-bottom: 8px;
}
.nf-code {
  margin: 0;
  font-size: 34px;
  font-weight: 700;
  letter-spacing: 0.02em;
  color: var(--app-text);
}
.nf-desc {
  margin: 0 0 16px;
  font-size: 13px;
  color: var(--app-text-muted);
}
.nf-actions {
  display: flex;
  gap: 8px;
}
/* SVG 取色经 CSS 类注入，深浅主题自适应（同 EmptyState 方案） */
.nf-fill-solid {
  fill: var(--app-primary);
}
.nf-stroke {
  stroke: var(--app-primary);
  opacity: 0.55;
}
.nf-stroke-dash {
  stroke: var(--app-text-faint);
}
.nf-stroke-break {
  stroke: var(--app-warn-accent);
}
@media (prefers-reduced-motion: reduce) {
  .nf-card {
    animation: none;
  }
}
</style>

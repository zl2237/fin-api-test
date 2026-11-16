<template>
  <div class="tool-page">
    <el-card shadow="never" class="main-card">
      <template #header>
        <div class="card-head">
          <router-link to="/tools" class="back-link" aria-label="返回工具箱">
            <el-icon><ArrowLeft /></el-icon>
          </router-link>
          <span class="title">{{ title }}</span>
          <span class="sub">{{ sub }}</span>
        </div>
      </template>
      <slot />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ArrowLeft } from '@element-plus/icons-vue'

defineProps<{ title: string; sub?: string }>()
</script>

<style scoped>
.tool-page {
  padding: 16px;
  height: 100%;
  overflow: auto;
  background: var(--app-bg);
}
.main-card {
  max-width: 1100px;
  margin: 0 auto;
}
.card-head {
  display: flex;
  align-items: baseline;
  gap: 8px;
  flex-wrap: wrap;
}
/* 返回链接与基线对齐的图标竖直居中 */
.back-link {
  align-self: center;
  display: inline-flex;
  padding: 3px;
  border-radius: var(--app-radius-sm);
  color: var(--app-text-muted);
  transition: color 0.15s ease, background 0.15s ease;
}
.back-link:hover,
.back-link:focus-visible {
  color: var(--app-primary);
  background: color-mix(in srgb, var(--app-primary) 10%, transparent);
  outline: none;
}
.card-head .title {
  font-size: 15px;
  font-weight: 600;
  color: var(--app-text);
}
.card-head .sub {
  font-size: 12px;
  color: var(--app-text-muted);
}
</style>

<template>
  <div class="toolbox">
    <el-card shadow="never" class="main-card">
      <template #header>
        <div class="card-head">
          <span class="title">工具箱</span>
          <span class="sub">无状态小工具收口于此；资源管理（项目/环境/字典等）在「系统管理」</span>
        </div>
      </template>
      <div class="tool-grid">
        <div
          v-for="t in TOOLS"
          :key="t.path"
          class="tool-card"
          role="link"
          :tabindex="0"
          @click="router.push(t.path)"
          @keydown.enter="router.push(t.path)"
        >
          <div class="tool-icon">
            <el-icon :size="22"><component :is="t.icon" /></el-icon>
          </div>
          <div class="tool-main">
            <div class="tool-name">{{ t.name }}</div>
            <div class="tool-desc">{{ t.desc }}</div>
          </div>
          <el-icon class="tool-arrow"><ArrowRight /></el-icon>
        </div>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'
import { ArrowRight } from '@element-plus/icons-vue'
import { TOOLS } from '@/constants/tools'

const router = useRouter()
</script>

<style scoped>
.toolbox {
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
  gap: 10px;
  flex-wrap: wrap;
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
.tool-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 12px;
}
.tool-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 16px;
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius-sm);
  cursor: pointer;
  transition: border-color 0.18s ease, background 0.18s ease, box-shadow 0.18s ease;
}
.tool-card:hover,
.tool-card:focus-visible {
  border-color: var(--app-primary);
  background: color-mix(in srgb, var(--app-primary) 4%, transparent);
  outline: none;
}
.tool-card:focus-visible {
  box-shadow: inset 0 0 0 2px color-mix(in srgb, var(--app-primary) 45%, transparent);
}
.tool-icon {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 42px;
  height: 42px;
  border-radius: var(--app-radius-sm);
  color: var(--app-primary);
  background: color-mix(in srgb, var(--app-primary) 10%, transparent);
}
.tool-main {
  flex: 1;
  min-width: 0;
}
.tool-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--app-text);
}
.tool-desc {
  margin-top: 3px;
  font-size: 12px;
  color: var(--app-text-muted);
  line-height: 1.5;
  /* 两行截断：长描述不撑爆卡片 */
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.tool-arrow {
  flex-shrink: 0;
  color: var(--app-text-faint);
  transition: transform 0.18s ease, color 0.18s ease;
}
.tool-card:hover .tool-arrow {
  transform: translateX(3px);
  color: var(--app-primary);
}
@media (prefers-reduced-motion: reduce) {
  .tool-arrow,
  .tool-card {
    transition: none;
  }
}
</style>

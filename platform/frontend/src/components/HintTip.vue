<template>
  <!-- 静态说明文案统一收口（2026-11-05 干爽行动）：界面上只留一个问号，hover 浮层看内容；
       状态类警示（错误结果/删除确认等）不适用本组件，仍直接陈列 -->
  <el-tooltip :content="content" placement="top" :show-after="150" popper-class="app-tip">
    <el-icon class="hint-tip-icon"><QuestionFilled /></el-icon>
  </el-tooltip>
</template>

<script setup lang="ts">
import { QuestionFilled } from '@element-plus/icons-vue'

defineProps<{ content: string }>()
</script>

<style scoped>
.hint-tip-icon {
  margin-left: 4px;
  font-size: 14px;
  color: var(--app-text-muted, #909399);
  cursor: help;
  vertical-align: -2px;
  flex-shrink: 0;
}
</style>

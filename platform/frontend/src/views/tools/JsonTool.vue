<template>
  <ToolPage title="JSON 格式化">
    <div class="json-toolbar">
      <el-radio-group v-model="mode" size="small">
        <el-radio-button value="format">格式化</el-radio-button>
        <el-radio-button value="minify">压缩</el-radio-button>
      </el-radio-group>
      <el-select v-model="indent" size="small" style="width: 96px" :disabled="mode !== 'format'">
        <el-option label="2 空格" :value="2" />
        <el-option label="4 空格" :value="4" />
        <el-option label="Tab" :value="'\t'" />
      </el-select>
      <el-checkbox v-model="sortKeys" size="small">键排序</el-checkbox>
      <div class="grow" />
      <el-button size="small" type="primary" @click="run">转换</el-button>
      <el-button size="small" @click="onClear">清空</el-button>
    </div>
    <div class="io-grid">
      <div class="io-col">
        <div class="io-title">输入<CopyBtn v-if="input" :value="input" /></div>
        <el-input v-model="input" type="textarea" :rows="14" class="mono-input" spellcheck="false"
                  placeholder='{"batchNo":"CUS-B-1000","items":[{"bizNo":"BIZ-1"}]}' />
      </div>
      <div class="io-col">
        <div class="io-title">输出<CopyBtn v-if="result?.ok" :value="result.output" /></div>
        <el-alert v-if="result && !result.ok" type="error" :closable="false" show-icon class="io-error"
                  :title="result.error" />
        <pre v-else-if="result?.ok" class="mono-pre">{{ result.output || '（空结果：null / "" 等）' }}</pre>
        <EmptyState v-else description="输入 JSON 后点「转换」" :image-size="50" />
      </div>
    </div>
  </ToolPage>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import ToolPage from './ToolPage.vue'
import CopyBtn from '@/components/CopyBtn.vue'
import EmptyState from '@/components/EmptyState.vue'
import { transformJson, type JsonResult } from '@/utils/jsonTools'

const input = ref('')
const mode = ref<'format' | 'minify'>('format')
const indent = ref<number | string>(2)
const sortKeys = ref(false)
const result = ref<JsonResult | null>(null)

function run() {
  result.value = transformJson(input.value, {
    indent: mode.value === 'minify' ? 0 : (indent.value as number),
    sortKeys: sortKeys.value,
  })
  if (result.value.ok) ElMessage.success('转换成功')
}

function onClear() {
  input.value = ''
  result.value = null
}
</script>

<style scoped>
.json-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}
.grow { flex: 1; }
.io-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
}
@media (max-width: 860px) {
  .io-grid { grid-template-columns: 1fr; }
}
.io-col {
  min-width: 0;
}
.io-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 600;
  color: var(--app-text);
  margin-bottom: 6px;
}
.io-error {
  margin-top: 4px;
}
.mono-input :deep(.el-textarea__inner) {
  font-family: var(--app-font-mono, Consolas, monospace);
  font-size: 12px;
  line-height: 1.6;
}
.mono-pre {
  height: 322px;
  margin: 0;
  padding: 10px 12px;
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius-sm);
  background: var(--app-bg);
  font-size: 12px;
  font-family: var(--app-font-mono, Consolas, monospace);
  line-height: 1.6;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-all;
}
</style>

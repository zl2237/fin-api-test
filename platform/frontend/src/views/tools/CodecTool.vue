<template>
  <ToolPage title="编解码">
    <el-tabs v-model="tab">
      <el-tab-pane label="URL" name="url">
        <div class="codec-row">
          <div class="codec-col">
            <div class="io-title">原文<CopyBtn v-if="urlRaw" :value="urlRaw" /></div>
            <el-input v-model="urlRaw" type="textarea" :rows="9" class="mono-input" spellcheck="false"
                      placeholder="https://example.com/搜索?q= customs 报文" />
          </div>
          <div class="codec-actions">
            <el-button type="primary" @click="onUrlEncode">编码 →</el-button>
            <el-button @click="onUrlDecode">← 解码</el-button>
          </div>
          <div class="codec-col">
            <div class="io-title">结果<CopyBtn v-if="urlOut" :value="urlOut" /></div>
            <el-alert v-if="urlErr" type="error" :closable="false" show-icon :title="urlErr" />
            <el-input v-else :model-value="urlOut" type="textarea" :rows="9" class="mono-input" readonly />
          </div>
        </div>
      </el-tab-pane>

      <el-tab-pane label="Base64" name="b64">
        <div class="codec-row">
          <div class="codec-col">
            <div class="io-title">原文<CopyBtn v-if="b64Raw" :value="b64Raw" /></div>
            <el-input v-model="b64Raw" type="textarea" :rows="9" class="mono-input" spellcheck="false"
                      placeholder="任意文本（UTF-8）" />
          </div>
          <div class="codec-actions">
            <el-checkbox v-model="urlSafe" size="small">URL-safe（- _ 无填充）</el-checkbox>
            <el-button type="primary" @click="onB64Encode">编码 →</el-button>
            <el-button @click="onB64Decode">← 解码</el-button>
          </div>
          <div class="codec-col">
            <div class="io-title">结果<CopyBtn v-if="b64Out" :value="b64Out" /></div>
            <el-alert v-if="b64Err" type="error" :closable="false" show-icon :title="b64Err" />
            <el-input v-else :model-value="b64Out" type="textarea" :rows="9" class="mono-input" readonly />
          </div>
        </div>
      </el-tab-pane>
    </el-tabs>
  </ToolPage>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import ToolPage from './ToolPage.vue'
import CopyBtn from '@/components/CopyBtn.vue'
import { base64Decode, base64Encode, urlDecode, urlEncode } from '@/utils/codecTools'

const tab = ref<'url' | 'b64'>('url')

const urlRaw = ref('')
const urlOut = ref('')
const urlErr = ref('')
function onUrlEncode() {
  urlErr.value = ''
  urlOut.value = urlEncode(urlRaw.value)
}
function onUrlDecode() {
  urlErr.value = ''
  try {
    urlOut.value = urlDecode(urlRaw.value)
  } catch (e: any) {
    urlOut.value = ''
    urlErr.value = e.message
  }
}

const b64Raw = ref('')
const b64Out = ref('')
const b64Err = ref('')
const urlSafe = ref(false)
function onB64Encode() {
  b64Err.value = ''
  b64Out.value = base64Encode(b64Raw.value, urlSafe.value)
}
function onB64Decode() {
  b64Err.value = ''
  try {
    b64Out.value = base64Decode(b64Raw.value, urlSafe.value)
  } catch (e: any) {
    b64Out.value = ''
    b64Err.value = e.message
  }
}
</script>

<style scoped>
.codec-row {
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  gap: 14px;
  align-items: start;
}
@media (max-width: 860px) {
  .codec-row { grid-template-columns: 1fr; }
}
.codec-col { min-width: 0; }
.codec-actions {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  justify-content: center;
  gap: 10px;
  min-width: 150px;
  padding-top: 26px;
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
.mono-input :deep(.el-textarea__inner) {
  font-family: var(--app-font-mono, Consolas, monospace);
  font-size: 12px;
  line-height: 1.6;
}
</style>

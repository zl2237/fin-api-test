<template>
  <ToolPage title="哈希计算" sub="MD5 / SHA-1 / SHA-256 / SHA-512，输入即算（UTF-8 口径与后端 md5() 一致）">
    <el-input
      v-model="text"
      type="textarea"
      :rows="6"
      class="mono-input"
      spellcheck="false"
      placeholder="输入任意文本，四种哈希即时计算"
    />
    <div class="hash-toolbar">
      <el-checkbox v-model="upper" size="small">大写输出</el-checkbox>
      <span v-if="!subtleOk" class="sha-warn">当前环境不支持 WebCrypto（需 HTTPS 或 localhost），仅 MD5 可用</span>
    </div>
    <div v-for="row in rows" :key="row.algo" class="out-row">
      <el-tag size="small" effect="plain" class="algo-tag">{{ row.algo }}</el-tag>
      <span class="out-value mono" :class="{ 'is-empty': !row.value }">{{ row.value || '—' }}</span>
      <CopyBtn v-if="row.value" :value="row.value" />
    </div>
  </ToolPage>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import ToolPage from './ToolPage.vue'
import CopyBtn from '@/components/CopyBtn.vue'
import { md5 } from '@/utils/md5'

const text = ref('')
const upper = ref(false)
const sha = ref<Record<string, string>>({})
const subtleOk = typeof crypto !== 'undefined' && !!crypto.subtle

const rows = computed(() => {
  const pick = (v?: string) => (!v ? '' : upper.value ? v.toUpperCase() : v)
  return [
    { algo: 'MD5', value: pick(text.value ? md5(text.value) : '') },
    { algo: 'SHA-1', value: pick(sha.value['SHA-1']) },
    { algo: 'SHA-256', value: pick(sha.value['SHA-256']) },
    { algo: 'SHA-512', value: pick(sha.value['SHA-512']) },
  ]
})

// SHA 系列异步计算：防抖 300ms，避免长文本每键一次
let timer: number | undefined
watch(text, (v) => {
  window.clearTimeout(timer)
  if (!subtleOk || !v) {
    sha.value = {}
    return
  }
  timer = window.setTimeout(async () => {
    const data = new TextEncoder().encode(v)
    const out: Record<string, string> = {}
    for (const algo of ['SHA-1', 'SHA-256', 'SHA-512'] as const) {
      try {
        const buf = await crypto.subtle.digest(algo, data)
        out[algo] = [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, '0')).join('')
      } catch { /* 单算法失败留空，不打断其余 */ }
    }
    sha.value = out
  }, 300)
})
</script>

<style scoped>
.mono-input :deep(.el-textarea__inner) {
  font-family: var(--app-font-mono, Consolas, monospace);
  font-size: 12px;
  line-height: 1.6;
}
.hash-toolbar {
  display: flex;
  align-items: center;
  gap: 14px;
  margin: 10px 0 4px;
}
.sha-warn {
  font-size: 12px;
  color: var(--app-warn-text);
}
.out-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 0;
  border-bottom: 1px dashed var(--app-border);
}
.out-row:last-child { border-bottom: none; }
.algo-tag {
  flex-shrink: 0;
  width: 78px;
  justify-content: center;
  font-family: var(--app-font-mono, Consolas, monospace);
}
.out-value {
  flex: 1;
  min-width: 0;
  font-size: 12px;
  color: var(--app-text);
  word-break: break-all;
}
.out-value.is-empty { color: var(--app-text-faint); }
.mono { font-family: var(--app-font-mono, Consolas, monospace); }
</style>

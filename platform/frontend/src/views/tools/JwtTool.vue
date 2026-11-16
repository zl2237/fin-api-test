<template>
  <ToolPage title="JWT 解码" sub="仅解码，不校验签名">
    <el-input
      v-model="token"
      type="textarea"
      :rows="5"
      class="mono-input"
      spellcheck="false"
      placeholder="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0In0.签名段"
    />
    <el-alert v-if="error" type="error" :closable="false" show-icon :title="error" class="jwt-error" />
    <template v-if="decoded">
      <div class="jwt-grid">
        <div class="jwt-col">
          <div class="io-title">Header<CopyBtn :value="headerText" /></div>
          <pre class="mono-pre">{{ headerText }}</pre>
        </div>
        <div class="jwt-col">
          <div class="io-title">Payload<CopyBtn :value="payloadText" /></div>
          <pre class="mono-pre">{{ payloadText }}</pre>
        </div>
      </div>
      <div v-if="timeClaims.length" class="claims-card">
        <div class="io-title">时间声明</div>
        <el-table :data="timeClaims" size="small" border>
          <el-table-column prop="claim" label="声明" width="90" />
          <el-table-column prop="value" label="原始值" width="140" />
          <el-table-column label="可读时间">
            <template #default="{ row }">
              <span class="mono">{{ row.human }}</span>
              <el-tag v-if="row.tag" size="small" :type="row.tag" effect="light" style="margin-left: 8px">{{ row.tagText }}</el-tag>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </template>
    <EmptyState v-else-if="!error" description="粘贴 JWT 后自动解码" :image-size="50" />
  </ToolPage>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import ToolPage from './ToolPage.vue'
import CopyBtn from '@/components/CopyBtn.vue'
import EmptyState from '@/components/EmptyState.vue'
import { claimMs, decodeJwt } from '@/utils/jwtTools'
import { fmtLocal, fmtRelative } from '@/utils/timeTools'

const token = ref('')
const error = ref('')

watch(token, (v) => {
  error.value = ''
  if (!v.trim()) return
  try {
    decoded.value = decodeJwt(v)
  } catch (e: any) {
    decoded.value = null
    error.value = e.message
  }
})

const decoded = ref<ReturnType<typeof decodeJwt> | null>(null)
const headerText = computed(() =>
  decoded.value ? JSON.stringify(decoded.value.header, null, 2) : '')
const payloadText = computed(() =>
  decoded.value ? JSON.stringify(decoded.value.payload, null, 2) : '')

const timeClaims = computed(() => {
  const p = decoded.value?.payload || {}
  const now = Date.now()
  return (['exp', 'iat', 'nbf'] as const)
    .filter((k) => k in p)
    .map((k) => {
      const ms = claimMs(p[k])
      if (ms == null) return { claim: k, value: String(p[k]), human: '（非数字秒值）', tag: '' as any, tagText: '' }
      let tag: any = ''
      let tagText = ''
      if (k === 'exp') {
        tag = ms < now ? 'danger' : 'success'
        tagText = ms < now ? '已过期' : '有效'
      }
      return { claim: k, value: String(p[k]), human: `${fmtLocal(ms)}（${fmtRelative(ms, now)}）`, tag, tagText }
    })
})
</script>

<style scoped>
.mono-input :deep(.el-textarea__inner) {
  font-family: var(--app-font-mono, Consolas, monospace);
  font-size: 12px;
  line-height: 1.6;
}
.jwt-error { margin-top: 10px; }
.jwt-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
  margin-top: 12px;
}
@media (max-width: 860px) {
  .jwt-grid { grid-template-columns: 1fr; }
}
.jwt-col { min-width: 0; }
.io-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 600;
  color: var(--app-text);
  margin-bottom: 6px;
}
.mono-pre {
  margin: 0;
  padding: 10px 12px;
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius-sm);
  background: var(--app-bg);
  font-size: 12px;
  font-family: var(--app-font-mono, Consolas, monospace);
  line-height: 1.6;
  max-height: 260px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-all;
}
.claims-card {
  margin-top: 14px;
}
.mono { font-family: var(--app-font-mono, Consolas, monospace); }
</style>

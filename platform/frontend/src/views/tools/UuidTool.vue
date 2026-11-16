<template>
  <ToolPage title="UUID 生成" sub="v4 随机 UUID 批量生成（crypto 随机源）">
    <div class="uuid-toolbar">
      <span class="lbl">数量</span>
      <el-input-number v-model="count" :min="1" :max="200" size="small" />
      <el-checkbox v-model="noDash" size="small">去横杠</el-checkbox>
      <el-checkbox v-model="upper" size="small">大写</el-checkbox>
      <div class="grow" />
      <el-button type="primary" size="small" @click="generate">生成</el-button>
      <el-button size="small" @click="output = []">清空</el-button>
    </div>
    <div class="out-head" v-if="output.length">
      <span class="muted">{{ output.length }} 个</span>
      <CopyBtn :value="output.join('\n')" />
    </div>
    <pre v-if="output.length" class="mono-pre">{{ output.join('\n') }}</pre>
    <EmptyState v-else description="点「生成」批量产出 UUID" :image-size="50" />
  </ToolPage>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import ToolPage from './ToolPage.vue'
import CopyBtn from '@/components/CopyBtn.vue'
import EmptyState from '@/components/EmptyState.vue'

const count = ref(10)
const noDash = ref(false)
const upper = ref(false)
const output = ref<string[]>([])

function randomUuid(): string {
  // 优先原生 randomUUID；旧环境用 getRandomValues 手拼 v4（版本位 0100、变体位 10）
  if (typeof crypto !== 'undefined' && crypto.randomUUID) return crypto.randomUUID()
  const b = new Uint8Array(16)
  crypto.getRandomValues(b)
  b[6] = (b[6] & 0x0f) | 0x40
  b[8] = (b[8] & 0x3f) | 0x80
  const hex = [...b].map((x) => x.toString(16).padStart(2, '0')).join('')
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`
}

function generate() {
  const list = Array.from({ length: count.value }, () => {
    let u = randomUuid()
    if (noDash.value) u = u.replace(/-/g, '')
    return upper.value ? u.toUpperCase() : u
  })
  output.value = list
}
</script>

<style scoped>
.uuid-toolbar {
  display: flex;
  align-items: center;
  gap: 14px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}
.uuid-toolbar .lbl {
  font-size: 13px;
  color: var(--app-text-muted);
}
.grow { flex: 1; }
.out-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
}
.muted {
  font-size: 12px;
  color: var(--app-text-muted);
}
.mono-pre {
  margin: 0;
  padding: 10px 12px;
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius-sm);
  background: var(--app-bg);
  font-size: 12px;
  font-family: var(--app-font-mono, Consolas, monospace);
  line-height: 1.8;
  max-height: 420px;
  overflow: auto;
}
</style>

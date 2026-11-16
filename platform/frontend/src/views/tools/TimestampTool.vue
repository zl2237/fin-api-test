<template>
  <ToolPage title="时间戳转换">
    <!-- 当前时间：常驻参照 -->
    <div class="now-row">
      <div class="now-item">
        <div class="now-label">当前时间</div>
        <div class="now-value mono">{{ nowLocal }}（{{ nowWeekday }}）</div>
      </div>
      <div class="now-item">
        <div class="now-label">Unix 秒</div>
        <div class="now-value mono">{{ nowSec }}</div>
        <CopyBtn :value="String(nowSec)" />
      </div>
      <div class="now-item">
        <div class="now-label">Unix 毫秒</div>
        <div class="now-value mono">{{ nowMs }}</div>
        <CopyBtn :value="String(nowMs)" />
      </div>
    </div>

    <div class="two-col">
      <!-- 时间戳 → 日期 -->
      <div class="col-card">
        <div class="col-title">时间戳 → 日期时间</div>
        <el-input v-model="tsInput" class="mono-input" placeholder="如 1763260800 / 1763260800000" clearable />
        <template v-if="tsParsed.ok && tsParsed.ms != null">
          <el-alert class="unit-tip" type="info" :closable="false" show-icon
                    :title="`识别为 ${tsParsed.unit === 'us' ? '微秒' : tsParsed.unit === 'ms' ? '毫秒' : '秒'}`" />
          <div v-for="row in tsRows" :key="row.label" class="out-row">
            <span class="out-label">{{ row.label }}</span>
            <span class="out-value mono">{{ row.value }}</span>
            <CopyBtn :value="row.value" />
          </div>
        </template>
        <el-alert v-else-if="tsInput" type="warning" :closable="false" show-icon :title="tsParsed.reason || '无法解析'" />
      </div>

      <!-- 日期 → 时间戳 -->
      <div class="col-card">
        <div class="col-title">日期时间 → 时间戳</div>
        <el-input v-model="dateInput" class="mono-input" placeholder="2026-11-16 10:30:00（本地时区）" clearable />
        <template v-if="dateParsed.ok && dateParsed.ms != null">
          <div v-for="row in dateRows" :key="row.label" class="out-row">
            <span class="out-label">{{ row.label }}</span>
            <span class="out-value mono">{{ row.value }}</span>
            <CopyBtn :value="row.value" />
          </div>
        </template>
        <el-alert v-else-if="dateInput" type="warning" :closable="false" show-icon :title="dateParsed.reason || '无法解析'" />
      </div>
    </div>
  </ToolPage>
</template>

<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, ref } from 'vue'
import ToolPage from './ToolPage.vue'
import CopyBtn from '@/components/CopyBtn.vue'
import { fmtIso, fmtLocal, fmtRelative, fmtUtc, fmtWeekday, parseDateInput, parseTimestamp } from '@/utils/timeTools'

const nowMs = ref(Date.now())
let timer: number | undefined
onMounted(() => { timer = window.setInterval(() => { nowMs.value = Date.now() }, 1000) })
onBeforeUnmount(() => window.clearInterval(timer))

const nowLocal = computed(() => fmtLocal(nowMs.value))
const nowWeekday = computed(() => fmtWeekday(nowMs.value))
const nowSec = computed(() => Math.floor(nowMs.value / 1000))

const tsInput = ref('')
const tsParsed = computed(() => parseTimestamp(tsInput.value))
const tsRows = computed(() => {
  const ms = tsParsed.value.ms!
  return [
    { label: '本地时间', value: `${fmtLocal(ms)}（${fmtWeekday(ms)}）` },
    { label: 'UTC', value: fmtUtc(ms) },
    { label: 'ISO 8601', value: fmtIso(ms) },
    { label: '相对当前', value: fmtRelative(ms, nowMs.value) },
  ]
})

const dateInput = ref('')
const dateParsed = computed(() => parseDateInput(dateInput.value))
const dateRows = computed(() => {
  const ms = dateParsed.value.ms!
  return [
    { label: 'Unix 秒', value: String(Math.floor(ms / 1000)) },
    { label: 'Unix 毫秒', value: String(ms) },
    { label: '本地时间', value: `${fmtLocal(ms)}（${fmtWeekday(ms)}）` },
    { label: 'ISO 8601', value: fmtIso(ms) },
  ]
})
</script>

<style scoped>
.now-row {
  display: flex;
  align-items: flex-end;
  gap: 28px;
  flex-wrap: wrap;
  padding: 12px 16px;
  margin-bottom: 14px;
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius-sm);
  background: color-mix(in srgb, var(--app-primary) 4%, var(--app-card));
}
.now-item {
  display: flex;
  align-items: center;
  gap: 8px;
}
.now-label {
  font-size: 12px;
  color: var(--app-text-muted);
}
.now-value {
  font-size: 13px;
  color: var(--app-text);
  font-weight: 600;
}
.mono {
  font-family: var(--app-font-mono, Consolas, monospace);
}
.two-col {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(340px, 1fr));
  gap: 14px;
}
.col-card {
  padding: 14px 16px;
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius-sm);
}
.col-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--app-text);
  margin-bottom: 10px;
}
.unit-tip {
  margin-top: 10px;
}
.out-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 10px;
}
.out-label {
  flex-shrink: 0;
  width: 76px;
  font-size: 12px;
  color: var(--app-text-muted);
}
.out-value {
  flex: 1;
  min-width: 0;
  font-size: 13px;
  color: var(--app-text);
  word-break: break-all;
}
.mono-input :deep(.el-input__inner) {
  font-family: var(--app-font-mono, Consolas, monospace);
}
</style>

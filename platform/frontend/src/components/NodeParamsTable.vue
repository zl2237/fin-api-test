<template>
  <div class="npt">
    <div class="npt-section">
      <div class="npt-head">
        <span class="npt-title">请求体参数（body）</span>
        <span class="npt-sub">未配置字段按类型发空值占位；数组字段支持 <code>list.*.字段</code> 通配取值</span>
        <el-input
          v-model="bodyKeyword"
          size="small"
          clearable
          class="npt-search"
          placeholder="按路径/值筛选，如 order_id"
          :prefix-icon="Search"
        />
      </div>

      <!-- 虚拟滚动列表：入参上百行时只渲染可视区（el-table 全量渲染 200+ 行
           是节点内滚动/切换卡顿的主源之一），行高固定 40px -->
      <div class="vt">
        <div class="vt-head">
          <div class="vt-c1">字段路径</div>
          <div class="vt-c2">取值来源</div>
          <div class="vt-c3">操作</div>
        </div>
        <div
          ref="bodyScrollEl"
          class="vt-scroll"
          :style="{ maxHeight: BODY_VIEW_H + 'px' }"
          @scroll.passive="onBodyScroll"
        >
          <div v-if="shownBodyRows.length" class="vt-spacer" :style="{ height: shownBodyRows.length * ROW_H + 'px' }">
            <div
              v-for="idx in visibleBodyIdxs"
              :key="idx"
              class="vt-row"
              :style="{ top: idx * ROW_H + 'px' }"
            >
              <div class="vt-c1">
                <el-autocomplete
                  v-model="shownBodyRows[idx].path"
                  size="small"
                  :fetch-suggestions="(qs: string, cb: any) => fetchFieldSuggestions(qs, cb, idx)"
                  placeholder="如 order_id / supplier.0.order_id / list.*.unique_id"
                  style="width: 100%"
                >
                  <template #default="{ item }">
                    <div class="sug">
                      <span class="sug-path">{{ item.value }}</span>
                      <span v-if="item.label" class="sug-cn">{{ item.label }}</span>
                    </div>
                  </template>
                </el-autocomplete>
              </div>
              <div class="vt-c2">
                <ParamSourceBadge
                  :model-value="shownBodyRows[idx].spec"
                  :ref-groups="refGroups"
                  :file-field="fieldTypeMap[shownBodyRows[idx].path] === 'file'"
                  @update:model-value="(v) => (shownBodyRows[idx].spec = v)"
                />
              </div>
              <div class="vt-c3">
                <el-button link type="danger" size="small" @click="removeRow('body', idx)">删除</el-button>
              </div>
            </div>
          </div>
          <div v-else class="vt-empty">
            {{ bodyKeyword ? `没有匹配「${bodyKeyword}」的 body 参数` : (lockBodyAdd ? '暂无 body 参数；未配置字段执行时按空值占位发送' : '暂无 body 参数，点击下方添加') }}
          </div>
        </div>
      </div>
      <!-- 封死手动添加（2026-10-10 定案 Q5）：参数路径唯一契约源是接口字段，
           新增/删除字段在接口管理维护，保存时可一键同步到数据集；
           headers 不在接口字段契约内，保留自由添加 -->
      <el-button v-if="!lockBodyAdd" class="npt-add" size="small" @click="addRow('body')">+ 添加 body 参数</el-button>
      <div v-else class="npt-lock">body 参数以「接口管理」的字段契约为唯一来源：新增字段请在接口编辑页维护，保存后可一键同步到数据集</div>
    </div>

    <div class="npt-section">
      <div class="npt-head">
        <span class="npt-title">请求头参数（headers）</span>
        <span class="npt-sub">节点参数压过环境公共头与接口模板头</span>
        <el-input
          v-model="headerKeyword"
          size="small"
          clearable
          class="npt-search"
          placeholder="按 Header 名/值筛选"
          :prefix-icon="Search"
        />
      </div>

      <div class="vt">
        <div class="vt-head">
          <div class="vt-c1">Header 名</div>
          <div class="vt-c2">取值来源</div>
          <div class="vt-c3">操作</div>
        </div>
        <div class="vt-scroll">
          <div v-if="shownHeaderRows.length" class="vt-rows">
            <div v-for="(row, i) in shownHeaderRows" :key="i" class="vt-row static">
              <div class="vt-c1">
                <el-input v-model="row.path" size="small" placeholder="如 X-Token" />
              </div>
              <div class="vt-c2">
                <ParamSourceBadge
                  :model-value="row.spec"
                  :ref-groups="refGroups"
                  @update:model-value="(v) => (row.spec = v)"
                />
              </div>
              <div class="vt-c3">
                <el-button link type="danger" size="small" @click="removeRow('headers', i)">删除</el-button>
              </div>
            </div>
          </div>
          <div v-else class="vt-empty">{{ headerKeyword ? `没有匹配「${headerKeyword}」的 header 参数` : '暂无 header 参数' }}</div>
        </div>
      </div>
      <el-button class="npt-add" size="small" @click="addRow('headers')">+ 添加 header 参数</el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
/** 节点入参来源表：params.body / params.headers 两分区，行 = 字段路径 × 四来源 spec。

性能要点（200+ 行/节点实测教训，2026-09-30）：
- body 行虚拟滚动：只渲染可视区 ± 缓冲行（el-table 全量渲染 + 每行 el-select
  常驻 options 是滚动/切换卡顿主源）
- 字段路径用 el-autocomplete：建议项下拉打开时才渲染 DOM
- 行编辑 commit 防抖 + 组件卸载前 flush
- 回环防护用 toRaw 解代理比对：父级把 emit 的对象存进 reactive 再传回时
  props.modelValue 是 Proxy，直接 === lastEmitted 恒不成立 → 全表每 200ms
  重建一轮（振铃环）→ 新增空 path 行被重建吞掉、输入焦点漂移、持续卡顿
- syncFromModel 引起的行为变化不触发 commit（挂载/切 tab 不产生假脏标记）
*/
import { computed, onBeforeUnmount, ref, toRaw, watch } from 'vue'
import { Search } from '@element-plus/icons-vue'
import type { ApiField, NodeParams, ParamSpec } from '@/api'
import { useApiFieldOptions } from '@/composables/useApiFieldOptions'
import ParamSourceBadge from './ParamSourceBadge.vue'
import type { RefVarGroup } from './VarRefSelect.vue'

const props = defineProps<{
  modelValue: NodeParams | null | undefined
  fields?: ApiField[]
  refGroups?: RefVarGroup[]
  lockBodyAdd?: boolean
}>()
const emit = defineEmits<{ (e: 'update:modelValue', v: NodeParams): void }>()

const { fieldOptions } = useApiFieldOptions(() => props.fields || [])

/** 字段路径 → 字段类型（file 类型行启用文件选择器编辑） */
const fieldTypeMap = computed(() => {
  const m: Record<string, string> = {}
  for (const f of props.fields || []) if (f.key) m[f.key] = f.field_type
  return m
})

/** 路径建议（下拉打开时才调用/渲染）：前缀与中文名双向匹配；
 *  排除其他行已配置的路径——同一字段仅可搜索并添加一次 */
function fetchFieldSuggestions(qs: string, cb: (items: { value: string }[]) => void, curIdx?: number) {
  const q = (qs || '').trim().toLowerCase()
  const used = new Set<string>()
  bodyRows.value.forEach((r, i) => {
    if (i !== curIdx && r.path.trim()) used.add(r.path.trim())
  })
  const all = fieldOptions.value
    .filter((o) => !used.has(o.value))
    .map((o) => ({ value: o.value, label: o.label }))
  cb(q ? all.filter((o) => o.value.toLowerCase().includes(q) || (o.label || '').toLowerCase().includes(q)) : all)
}

interface ParamRow { path: string; spec: ParamSpec }
const bodyRows = ref<ParamRow[]>([])
const headerRows = ref<ParamRow[]>([])

// ---- 关键词过滤（不区分大小写；路径或取值 spec 文本命中即显示）----
// 过滤只影响展示层：行对象仍是 bodyRows/headerRows 的同一引用，
// 行内编辑/删除/commit 全部作用于全量数据
const bodyKeyword = ref('')
const headerKeyword = ref('')

function matchRow(r: ParamRow, q: string): boolean {
  return r.path.toLowerCase().includes(q)
    || JSON.stringify(r.spec).toLowerCase().includes(q)
}

const shownBodyRows = computed(() => {
  const q = bodyKeyword.value.trim().toLowerCase()
  return q ? bodyRows.value.filter((r) => matchRow(r, q)) : bodyRows.value
})
const shownHeaderRows = computed(() => {
  const q = headerKeyword.value.trim().toLowerCase()
  return q ? headerRows.value.filter((r) => matchRow(r, q)) : headerRows.value
})

// 过滤词变化后列表变短，滚动位置复位到顶部（否则虚拟切片悬空在空白区）
watch([bodyKeyword, headerKeyword], () => {
  bodyScrollTop.value = 0
  if (bodyScrollEl.value) bodyScrollEl.value.scrollTop = 0
})

// ---- 虚拟滚动（body 区）----
const ROW_H = 40        // 行高（el-input small 24px + 上下 padding）
const BODY_VIEW_H = 480 // 可视区高度
const BUFFER = 6
const bodyScrollEl = ref<HTMLElement | null>(null)
const bodyScrollTop = ref(0)

function onBodyScroll(e: Event) {
  bodyScrollTop.value = (e.target as HTMLElement).scrollTop
}

/** 可视区 ± 缓冲的绝对行下标切片（基于过滤后列表） */
const visibleBodyIdxs = computed<number[]>(() => {
  const total = shownBodyRows.value.length
  if (!total) return []
  const start = Math.max(0, Math.floor(bodyScrollTop.value / ROW_H) - BUFFER)
  const end = Math.min(total, Math.ceil((bodyScrollTop.value + BODY_VIEW_H) / ROW_H) + BUFFER)
  const out: number[] = []
  for (let i = start; i < end; i++) out.push(i)
  return out
})

// ---- 模型 ↔ 行同步（防回环 + 防假脏）----
// lastEmitted：commit 产物原对象。父组件把它存进 reactive 再传回时包成 Proxy，
// 比对必须 toRaw 解代理——否则 syncFromModel 全表重建行（振铃环/丢空行/掉焦点）
let lastEmitted: NodeParams | null = null
let syncing = false // syncFromModel 引起的行变化不是用户编辑，不触发 commit

function syncFromModel() {
  if (toRaw(props.modelValue) === lastEmitted) return  // 自己刚 emit 的回声，行已是最新
  const p = props.modelValue || {}
  syncing = true
  try {
    bodyRows.value = Object.entries(p.body || {}).map(([path, spec]) => ({ path, spec: spec as ParamSpec }))
    headerRows.value = Object.entries(p.headers || {}).map(([path, spec]) => ({ path, spec: spec as ParamSpec }))
  } finally {
    // syncing 的消费在 watch 回调（同 tick 的 pre-flush），此处同步复位会丢标记，
    // 用微任务兜底：行重建触发的 watch 回调先到则消费；无回调（行等价）则复位
    Promise.resolve().then(() => { syncing = false })
  }
}
watch(
  () => props.modelValue,
  () => syncFromModel(),
  { immediate: true },
)

function commit() {
  const next: NodeParams = {}
  const body: Record<string, ParamSpec> = {}
  for (const r of bodyRows.value) {
    if (r.path.trim() && !body[r.path.trim()]) body[r.path.trim()] = r.spec
  }
  const headers: Record<string, ParamSpec> = {}
  for (const r of headerRows.value) {
    if (r.path.trim() && !headers[r.path.trim()]) headers[r.path.trim()] = r.spec
  }
  if (Object.keys(body).length) next.body = body
  if (Object.keys(headers).length) next.headers = headers
  lastEmitted = next
  emit('update:modelValue', next)
}

// 行内变更（路径输入/spec 编辑）防抖收拢：每击键全量重建+emit 会触发
// 父级重渲染 → 全表徽标重渲染，200 行表必卡
let commitTimer: ReturnType<typeof setTimeout> | null = null
function scheduleCommit() {
  if (commitTimer != null) return
  commitTimer = setTimeout(() => {
    commitTimer = null
    commit()
  }, 200)
}
watch([bodyRows, headerRows], () => {
  if (syncing) return // sync 重建非用户编辑：不 commit（不置脏、不起振铃环）
  scheduleCommit()
}, { deep: true })

// 卸载（切 tab 面板销毁）前 flush 待提交编辑，防止丢失最后一段输入
onBeforeUnmount(() => {
  if (commitTimer != null) {
    clearTimeout(commitTimer)
    commitTimer = null
    commit()
  }
})

function addRow(scope: 'body' | 'headers') {
  const rows = scope === 'body' ? bodyRows : headerRows
  rows.value.push({ path: '', spec: { source: 'constant', value: '' } })
  // 新行滚进可视区（上百行时追加在尾部，避免「加了看不见」）
  if (scope === 'body' && bodyScrollEl.value) {
    requestAnimationFrame(() => {
      if (bodyScrollEl.value) {
        bodyScrollEl.value.scrollTop = Math.max(0, rows.value.length * ROW_H - BODY_VIEW_H + ROW_H)
      }
    })
  }
}
function removeRow(scope: 'body' | 'headers', idx: number) {
  // body 区 idx 来自过滤后列表：先换算回全量列表的真实下标
  if (scope === 'body') {
    const real = bodyRows.value.indexOf(shownBodyRows.value[idx])
    if (real >= 0) bodyRows.value.splice(real, 1)
    return
  }
  const realH = headerRows.value.indexOf(shownHeaderRows.value[idx])
  if (realH >= 0) headerRows.value.splice(realH, 1)
}
</script>

<style scoped>
.npt {
  display: flex;
  flex-direction: column;
  gap: 18px;
}
.npt-head {
  display: flex;
  align-items: baseline;
  gap: 10px;
  margin-bottom: 6px;
}
.npt-search {
  width: 220px;
  flex-shrink: 0;
  margin-left: auto;
}
.npt-title {
  font-weight: 600;
  font-size: 13px;
}
.npt-sub {
  font-size: 12px;
  color: var(--app-text-muted);
}
.npt-add {
  margin-top: 8px;
  width: 100%;
  border-style: dashed;
}
.npt-lock {
  margin-top: 8px;
  padding: 5px 10px;
  border: 1px dashed var(--app-border);
  border-radius: 5px;
  font-size: 12px;
  color: var(--app-text-faint);
  text-align: center;
}
/* 轻量表格（替代 el-table：虚拟滚动 + 无每行 select 常驻 options） */
.vt {
  border: 1px solid var(--app-border);
  border-radius: 5px;
  overflow: hidden;
  background: var(--app-card, #fff);
}
.vt-head {
  display: grid;
  grid-template-columns: minmax(200px, 1fr) minmax(220px, 1.5fr) 56px;
  align-items: center;
  padding: 0 8px;
  height: 32px;
  background: var(--app-hover);
  font-size: 12px;
  font-weight: 600;
  color: var(--app-text-muted);
}
.vt-scroll {
  overflow: auto;
}
.vt-spacer {
  position: relative;
}
.vt-row {
  position: absolute;
  left: 0;
  right: 0;
  display: grid;
  grid-template-columns: minmax(200px, 1fr) minmax(220px, 1.5fr) 56px;
  align-items: center;
  gap: 8px;
  height: 40px;
  padding: 0 8px;
  border-top: 1px solid var(--app-border);
  background: var(--app-card, #fff);
}
.vt-rows .vt-row.static {
  position: relative;
}
.vt-empty {
  padding: 14px 0;
  text-align: center;
  font-size: 12px;
  color: var(--app-text-faint);
}
.vt-c3 {
  text-align: center;
}
/* 路径建议项：路径 + 字典中文名 */
.sug {
  display: flex;
  align-items: center;
  gap: 8px;
  justify-content: space-between;
}
.sug-path {
  font-family: var(--app-font-mono, monospace);
  font-size: 12px;
}
.sug-cn {
  color: var(--app-text-faint);
  font-size: 12px;
  flex-shrink: 0;
}
</style>

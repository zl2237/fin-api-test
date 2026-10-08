<template>
  <div class="psf">
    <div class="psf-src-row">
      <el-radio-group :model-value="source" size="small" @update:model-value="onSourceChange">
        <el-radio-button value="constant">常量</el-radio-button>
        <el-radio-button value="ref">引用</el-radio-button>
        <el-radio-button value="func">函数</el-radio-button>
        <el-radio-button v-if="!banSql" value="sql">SQL</el-radio-button>
      </el-radio-group>
      <el-tooltip v-if="source === 'ref' || source === 'func'" content='解析值包成单元素数组（如接口要求 ["值"] 形态）' placement="top">
        <span class="psf-arr">
          <el-switch :model-value="!!spec.as_array" size="small" @update:model-value="(v: any) => patch({ as_array: !!v })" />
          <span class="psf-arr-label">数组包裹</span>
        </span>
      </el-tooltip>
    </div>

    <!-- 来源1：手动常量。对象/数组值 JSON 文本编辑（数组内可嵌 {source:...} spec，运行时递归求值） -->
    <template v-if="source === 'constant'">
      <!-- 文件字段：文件中心选择器（常量值 = file_id），选中文件比手输 ID 直观 -->
      <div v-if="fileField" class="psf-file">
        <div class="psf-file-cur">
          <span v-if="fileInfo" :title="fileInfo.name" class="psf-file-name">{{ fileInfo.name }}</span>
          <span v-else-if="fileInfoMissing" class="psf-file-miss">文件 #{{ spec.value }} 已不存在，请重新选择</span>
          <span v-else-if="hasFileValue" class="psf-file-name">文件 #{{ spec.value }}</span>
          <span v-else class="psf-hint">未选择文件</span>
          <el-button size="small" type="primary" @click="emit('open-picker')">
            {{ hasFileValue ? '更换文件' : '选择文件' }}
          </el-button>
        </div>
      </div>
      <el-input
        v-if="isPlainValue"
        v-model="textValue"
        size="small"
        :autosize="{ minRows: 1, maxRows: 4 }"
        type="textarea"
        :placeholder="fileField ? '或直接填文件ID' : (placeholder || '输入常量值')"
        @change="commitConstantText"
      />
      <template v-else>
        <el-input
          v-model="textValue"
          size="small"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 10 }"
          placeholder='JSON 值，如 [{"user_id":"60"}]'
          @change="commitConstantText"
        />
        <p class="psf-hint">对象/数组常量：合法 JSON 保存；数组元素可放 <code>{"source":"ref",...}</code> 引用（运行时逐元素求值）</p>
      </template>
    </template>

    <!-- 来源3：上游变量引用（下拉，禁手输） -->
    <VarRefSelect
      v-else-if="source === 'ref'"
      :model-value="{ node_id: spec.node_id, var_path: spec.var_path }"
      :groups="refGroups"
      @update:model-value="(v) => patch(v)"
    />

    <!-- 来源2：内置函数（下拉选函数，入参可为常量或引用） -->
    <template v-else-if="source === 'func'">
      <el-select
        :model-value="spec.func"
        size="small"
        filterable
        placeholder="选择函数"
        style="width: 100%"
        @update:model-value="onFuncChange"
      >
        <el-option v-for="f in FUNC_REGISTRY" :key="f.name" :value="f.name" :label="`${f.label}（${f.name}）`" />
      </el-select>
      <div v-if="activeParams.length" class="psf-args">
        <div v-for="p in activeParams" :key="p.name" class="psf-arg-row">
          <span class="psf-arg-name">{{ p.label || p.name }}</span>
          <el-radio-group :model-value="argOf(p.name).kind" size="small" @update:model-value="(k: any) => setArgKind(p.name, k)">
            <el-radio-button value="const">常量</el-radio-button>
            <el-radio-button value="ref">引用</el-radio-button>
          </el-radio-group>
          <div class="psf-arg-ctrl">
            <el-input
              v-if="argOf(p.name).kind !== 'ref'"
              :model-value="argOf(p.name).value ?? ''"
              size="small"
              :placeholder="p.placeholder"
              @update:model-value="(v: string) => patchArg(p.name, { value: v })"
            />
            <VarRefSelect
              v-else
              :model-value="{ node_id: argOf(p.name).node_id, var_path: argOf(p.name).var_path }"
              :groups="refGroups"
              :placeholder="`选择变量作 ${p.name} 入参`"
              @update:model-value="(v) => patchArg(p.name, v)"
            />
          </div>
        </div>
      </div>
    </template>

    <!-- 来源4：参数级标量 SQL（前 3 类参数解析完后执行；{{节点.变量}} 引用已产出值） -->
    <template v-else-if="source === 'sql' && !banSql">
      <el-input
        :model-value="spec.sql"
        size="small"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 6 }"
        placeholder="SELECT order_id FROM sys_order WHERE bl_no = {{n_create.bl_no}}"
        @update:model-value="(v: string) => patch({ sql: v })"
      />
      <div class="psf-sql-extra">
        <span class="psf-arg-name">结果列</span>
        <el-input
          :model-value="spec.column"
          size="small"
          placeholder="缺省取首行首列"
          style="width: 180px"
          @update:model-value="(v: string) => patch({ column: v })"
        />
      </div>
      <p class="psf-hint">SQL 在其余参数解析完成后执行，结果注册为 <code>本节点.参数路径</code> 供下游引用</p>
    </template>
  </div>
</template>

<script setup lang="ts">
/** 四来源参数完整表单：constant/func/ref/sql 单选编辑。
 *  modelValue 兼容三类输入——spec dict / 裸字面量（规范化为 constant）/ 容器内嵌 spec（JSON 文本编辑）。 */
import { computed, ref, watch } from 'vue'
import type { ParamSpec, TestFile } from '@/api'
import { fileApi } from '@/api'
import { FUNC_REGISTRY, funcMeta } from '@/constants/funcRegistry'
import VarRefSelect from './VarRefSelect.vue'
import type { RefVarGroup } from './VarRefSelect.vue'

const props = withDefaults(defineProps<{
  modelValue: any
  refGroups?: RefVarGroup[]
  banSql?: boolean
  placeholder?: string
  /** 字段类型为 file：常量分支提供文件中心选择器（值 = file_id） */
  fileField?: boolean
}>(), {
  refGroups: () => [],
  banSql: false,
  placeholder: '',
  fileField: false,
})
const emit = defineEmits<{
  (e: 'update:modelValue', v: ParamSpec): void
  /** 文件字段：请求打开文件中心选择器（FilePicker 由外层持有，避免被 popover 关闭连累） */
  (e: 'open-picker'): void
}>()

const isSpec = (v: any): v is ParamSpec =>
  !!v && typeof v === 'object' && !Array.isArray(v)
  && typeof v.source === 'string' && ['constant', 'func', 'ref', 'sql'].includes(v.source)

const spec = computed<ParamSpec>(() => {
  if (isSpec(props.modelValue)) return props.modelValue
  return { source: 'constant', value: props.modelValue }
})
const source = computed(() => (props.banSql && spec.value.source === 'sql' ? 'constant' : spec.value.source))

function emitSpec(next: ParamSpec) {
  emit('update:modelValue', next)
}
function patch(part: Partial<ParamSpec>) {
  emitSpec({ ...spec.value, ...part })
}
function onSourceChange(src: string) {
  if (src === spec.value.source) return
  // 切换来源重建 spec，不携带旧来源字段（防脏数据进保存校验）
  const next: ParamSpec = { source: src as ParamSpec['source'] }
  if (src === 'constant') next.value = ''
  if (src === 'ref') Object.assign(next, { node_id: '', var_path: '' })
  if (src === 'func') next.func = FUNC_REGISTRY[0].name
  if (src === 'sql') next.sql = ''
  emitSpec(next)
}

// ===== constant 编辑 =====
const isPlainValue = computed(() => {
  const v = spec.value.value
  return v === null || v === undefined || typeof v !== 'object'
})

// ===== 文件字段（fileField）：常量值 = 文件中心 file_id =====
const fileInfo = ref<TestFile | null>(null)
const fileInfoMissing = ref(false)
const hasFileValue = computed(() =>
  source.value === 'constant' && spec.value.value !== '' && spec.value.value != null)
const fileIdNum = computed(() => {
  const v = spec.value.value
  if (typeof v === 'number') return v
  if (typeof v === 'string' && /^\d+$/.test(v)) return Number(v)
  return null
})
// 组件随 popover 打开才挂载：此处只发一次单查请求，文件名回显
watch(() => [props.modelValue, source.value, props.fileField] as const, async () => {
  fileInfo.value = null
  fileInfoMissing.value = false
  if (!props.fileField || source.value !== 'constant') return
  const id = fileIdNum.value
  if (!id) return
  try {
    fileInfo.value = await fileApi.get(id)
  } catch {
    fileInfoMissing.value = true
  }
}, { immediate: true })

const textValue = ref('')
watch(
  () => [props.modelValue, source.value] as const,
  () => {
    if (source.value !== 'constant') return
    const v = spec.value.value
    if (v === null || v === undefined) textValue.value = ''
    else if (typeof v === 'object') textValue.value = JSON.stringify(v, null, 2)
    else textValue.value = String(v)
  },
  { immediate: true },
)
function commitConstantText(text: string) {
  const s = (text ?? '').trim()
  if (!s) {
    patch({ value: '' })
    return
  }
  if (s.startsWith('[') || s.startsWith('{')) {
    try {
      patch({ value: JSON.parse(s) })
    } catch {
      // 非法 JSON 原样保留为字符串，保存校验兜底提示
      patch({ value: s })
    }
    return
  }
  // 数字/布尔自动转类型，其余按字符串（与旧字面量行为一致）
  if (/^-?\d+(\.\d+)?$/.test(s)) patch({ value: Number(s) })
  else if (s === 'true' || s === 'false') patch({ value: s === 'true' })
  else patch({ value: s })
}

// ===== func 参数 =====
const activeParams = computed(() => funcMeta(spec.value.func || '')?.params || [])
function argOf(name: string) {
  return (spec.value.args || []).find((a) => a && a.name === name) || { name, kind: 'const' as const, value: '' }
}
function onFuncChange(fn: string) {
  patch({ func: fn, args: [] })
}
function patchArg(name: string, part: Record<string, any>) {
  const args = [...(spec.value.args || []).filter((a) => a && a.name !== name)]
  args.push({ ...argOf(name), ...part, name })
  patch({ args })
}
function setArgKind(name: string, kind: 'const' | 'ref') {
  if (argOf(name).kind === kind) return
  if (kind === 'ref') patchArg(name, { kind, value: undefined, node_id: '', var_path: '' })
  else patchArg(name, { kind, node_id: undefined, var_path: undefined, value: '' })
}
</script>

<style scoped>
.psf {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.psf-src-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.psf-arr {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.psf-arr-label {
  font-size: 12px;
  color: var(--app-text-muted);
}
.psf-hint {
  margin: 0;
  font-size: 12px;
  color: var(--app-text-muted);
  line-height: 1.5;
}
.psf-hint code {
  background: var(--app-hover);
  padding: 0 4px;
  border-radius: 3px;
}
.psf-args {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 8px;
  border: 1px dashed var(--app-border);
  border-radius: 6px;
}
.psf-arg-row {
  display: grid;
  grid-template-columns: 64px auto 1fr;
  align-items: center;
  gap: 8px;
}
.psf-arg-name {
  font-size: 12px;
  color: var(--app-text-muted);
}
.psf-arg-ctrl {
  min-width: 0;
}
.psf-sql-extra {
  display: flex;
  align-items: center;
  gap: 8px;
}
.psf-file {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.psf-file-cur {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 4px 8px;
  border: 1px dashed var(--app-border);
  border-radius: 5px;
  background: var(--app-hover);
}
.psf-file-name {
  font-size: 12px;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.psf-file-miss {
  font-size: 12px;
  color: var(--el-color-danger);
}
</style>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { caseApi, caseGroupApi, type CaseGroup, type TestCase } from '@/api'
import { buildGroupTree } from '@/composables/useGroupTree'
import { useAppStore } from '@/stores'

/**
 * 方案「添加成员」弹窗：项目 → 按分组勾选 + 名称搜索，一次可加多个用例。
 * 只做选择 UI——确认后 emit('confirm', cases) 并自关，成员行构造由父视图完成。
 * 已在方案中的用例勾选禁用防重复。
 */
const props = defineProps<{
  modelValue: boolean
  /** 已是成员的用例 id（勾选禁用） */
  excludeCaseIds: number[]
  /** 打开时默认选中的项目 */
  defaultProjectId: number | null
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'confirm', cases: TestCase[]): void
}>()

const visible = computed({
  get: () => props.modelValue,
  set: (v: boolean) => emit('update:modelValue', v),
})

const store = useAppStore()
const projectId = ref<number | null>(null)
const keyword = ref('')
const cases = ref<TestCase[]>([])
const groups = ref<CaseGroup[]>([])
const loading = ref(false)
const loadError = ref('')
const selected = ref<number[]>([])

/** 分组 id → 路径标签（层级拍平为「父 / 子」），顺序跟随分组树 */
const groupPaths = computed(() => {
  const out = new Map<number, string>()
  const walk = (nodes: ReturnType<typeof buildGroupTree>, prefix: string) => {
    for (const n of nodes) {
      const label = prefix ? `${prefix} / ${n.label}` : n.label
      out.set(n.id, label)
      walk(n.children, label)
    }
  }
  walk(buildGroupTree(groups.value), '')
  return out
})

interface GroupBlock { key: string; label: string; cases: TestCase[] }
/** 命中搜索的用例按分组归块；分组顺序取树序，未分组殿后（同旧内联树口径） */
const blocks = computed<GroupBlock[]>(() => {
  const kw = keyword.value.trim().toLowerCase()
  const hit = (c: TestCase) => !kw || c.name.toLowerCase().includes(kw)
  const byGroup = (gid: number | null) =>
    cases.value.filter((c) => (c.group_id ?? null) === gid && hit(c))
  const out: GroupBlock[] = []
  for (const [gid, label] of groupPaths.value) {
    const list = byGroup(gid)
    if (list.length) out.push({ key: `g${gid}`, label, cases: list })
  }
  const ungrouped = byGroup(null)
  if (ungrouped.length) out.push({ key: 'g0', label: '未分组', cases: ungrouped })
  return out
})

const excluded = computed(() => new Set(props.excludeCaseIds))

async function loadCases() {
  if (!projectId.value) { cases.value = []; groups.value = []; return }
  loading.value = true
  loadError.value = ''
  try {
    const [cs, gs] = await Promise.all([
      caseApi.list(projectId.value),
      caseGroupApi.list(projectId.value).catch(() => [] as CaseGroup[]),
    ])
    cases.value = cs
    groups.value = gs
  } catch (e: any) {
    loadError.value = e?.message || '加载用例失败'
    cases.value = []
    groups.value = []
  } finally {
    loading.value = false
  }
}

watch(() => props.modelValue, (open) => {
  if (!open) return
  selected.value = []
  keyword.value = ''
  if (projectId.value == null) projectId.value = props.defaultProjectId
  loadCases()
})

function onProjectChange() {
  selected.value = []
  loadCases()
}

function confirm() {
  const picked = cases.value.filter((c) => selected.value.includes(c.id))
  if (!picked.length) return
  emit('confirm', picked)
  visible.value = false
}
</script>

<template>
  <el-dialog
    v-model="visible"
    title="添加方案成员"
    width="min(680px, 92vw)"
    align-center
    :close-on-click-modal="false"
  >
    <div class="pa-bar">
      <el-select v-model="projectId" style="width: 190px" placeholder="选择项目" filterable @change="onProjectChange">
        <el-option v-for="p in store.projects" :key="p.id" :label="p.name" :value="p.id" />
      </el-select>
      <el-input v-model="keyword" placeholder="搜索用例名称" clearable style="flex: 1" />
    </div>

    <div v-loading="loading" class="pa-body">
      <div v-if="loadError" class="app-load-error">
        <span>{{ loadError }}</span>
        <el-button size="small" @click="loadCases">重试</el-button>
      </div>
      <template v-else>
        <el-checkbox-group v-model="selected" class="pa-list">
          <template v-for="b in blocks" :key="b.key">
            <div class="pa-group">
              {{ b.label }}<span class="pa-group-count">{{ b.cases.length }}</span>
            </div>
            <el-checkbox
              v-for="c in b.cases"
              :key="c.id"
              :value="c.id"
              :disabled="excluded.has(c.id)"
              class="pa-case"
            >
              <span class="pa-case-name" :title="c.name">{{ c.name }}</span>
              <span class="pa-case-nodes">{{ c.dag_config?.nodes?.length || 0 }} 节点</span>
              <span v-if="excluded.has(c.id)" class="pa-case-dup">已在方案</span>
            </el-checkbox>
          </template>
        </el-checkbox-group>
        <div v-if="!blocks.length" class="pa-empty">
          {{ projectId == null ? '先选择项目' : keyword ? '没有匹配的用例' : '该项目暂无用例' }}
        </div>
      </template>
    </div>

    <template #footer>
      <span class="pa-count">已选 {{ selected.length }} 个</span>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" :disabled="!selected.length" @click="confirm">
        添加所选{{ selected.length ? ` ${selected.length} 个` : '' }}
      </el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.pa-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}
.pa-body {
  min-height: 220px;
}
.pa-list {
  display: block;
  max-height: 340px;
  overflow-y: auto;
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius-sm);
  padding: 4px 12px;
}
.pa-group {
  font-size: 12px;
  color: var(--app-text-muted);
  padding: 8px 0 2px;
}
.pa-group + .pa-group { border-top: none; }
.pa-group-count {
  margin-left: 6px;
  color: var(--app-text-faint);
}
.pa-case {
  width: 100%;
  height: 30px;
}
.pa-case-name {
  max-width: 330px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  vertical-align: middle;
  display: inline-block;
}
.pa-case-nodes {
  margin-left: 8px;
  font-size: 12px;
  color: var(--app-text-faint);
}
.pa-case-dup {
  margin-left: 8px;
  font-size: 12px;
  color: var(--el-color-warning);
}
.pa-empty {
  padding: 40px 0;
  text-align: center;
  font-size: 13px;
  color: var(--app-text-faint);
}
.pa-count {
  float: left;
  font-size: 12px;
  color: var(--app-text-muted);
  line-height: 32px;
}
</style>

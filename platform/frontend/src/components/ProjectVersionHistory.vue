<template>
  <el-dialog
    v-model="visible"
    title="项目版本管理"
    width="1000px"
    align-center
    :close-on-click-modal="false"
    @open="loadVersions"
  >
    <div class="pv-toolbar">
      <span class="pv-hint">手动保存项目快照（含全部接口+用例，不含环境），可随时回滚或对比。</span>
      <el-button type="primary" @click="onOpenCreate">保存新版本</el-button>
    </div>

    <el-table v-loading="loading" :data="versions" border size="small" row-key="id" max-height="420">
      <el-table-column label="版本" width="70">
        <template #default="{ row }">
          <span class="pv-ver">v{{ row.version_no }}</span>
        </template>
      </el-table-column>
      <el-table-column label="基准" width="60" align="center">
        <template #default="{ row }">
          <el-button size="small" :type="baseId === row.id ? 'primary' : 'default'" circle @click="baseId = row.id">
            <el-icon v-if="baseId === row.id"><Check /></el-icon>
          </el-button>
        </template>
      </el-table-column>
      <el-table-column label="对比" width="60" align="center">
        <template #default="{ row }">
          <el-button size="small" :type="targetId === row.id ? 'primary' : 'default'" circle @click="targetId = row.id">
            <el-icon v-if="targetId === row.id"><Check /></el-icon>
          </el-button>
        </template>
      </el-table-column>
      <el-table-column label="名称" prop="name" show-overflow-tooltip min-width="140" />
      <el-table-column label="说明" prop="description" show-overflow-tooltip min-width="140">
        <template #default="{ row }">
          <span v-if="row.description">{{ row.description }}</span>
          <span v-else class="pv-muted">—</span>
        </template>
      </el-table-column>
      <el-table-column label="创建人" width="100">
        <template #default="{ row }">{{ row.created_by_name || '—' }}</template>
      </el-table-column>
      <el-table-column label="时间" width="160">
        <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="120" fixed="right">
        <template #default="{ row }">
          <el-button link type="warning" @click="onRollback(row)">回滚</el-button>
          <el-button link type="danger" @click="onDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="pv-diff-tip" v-if="baseId && targetId && baseId !== targetId">
      将对比 <b>v{{ baseVerNo }}</b> 与 <b>v{{ targetVerNo }}</b>
    </div>
    <div class="pv-diff-tip pv-muted" v-else-if="versions.length >= 2">
      提示：点击「基准」「对比」列选择两个版本进行对比，默认已选最新两个版本。
    </div>

    <template #footer>
      <el-button
        type="primary"
        :disabled="!baseId || !targetId || baseId === targetId"
        :loading="diffLoading"
        @click="onDiff"
      >
        对比选中版本
      </el-button>
      <el-button @click="visible = false">关闭</el-button>
    </template>
  </el-dialog>

  <!-- 创建快照弹窗 -->
  <el-dialog
    v-model="createVisible"
    title="保存新版本"
    width="480px"
    align-center
    :close-on-click-modal="false"
    append-to-body
  >
    <el-form :model="createForm" label-width="80px">
      <el-form-item label="版本名称" required>
        <el-input v-model="createForm.name" placeholder="如 v1.0 / 冒烟基线" maxlength="100" show-word-limit />
      </el-form-item>
      <el-form-item label="说明">
        <el-input v-model="createForm.description" type="textarea" :rows="3" placeholder="本次版本的变更说明（可选）" maxlength="500" show-word-limit />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="createVisible = false">取消</el-button>
      <el-button type="primary" :loading="creating" @click="onCreate">保存</el-button>
    </template>
  </el-dialog>

  <!-- Diff 对比弹窗 -->
  <el-dialog
    v-model="diffVisible"
    title="版本对比"
    width="960px"
    align-center
    :close-on-click-modal="false"
    append-to-body
    class="pv-diff-dialog"
  >
    <div v-if="diffData" class="pv-diff-wrap">
      <div class="pv-diff-header">
        <el-tag type="info">基准 v{{ diffData.base.version_no }} · {{ diffData.base.name }}</el-tag>
        <el-icon class="pv-diff-arrow"><Right /></el-icon>
        <el-tag type="success">对比 v{{ diffData.target.version_no }} · {{ diffData.target.name }}</el-tag>
        <span class="pv-diff-summary">{{ diffSummary }}</span>
      </div>
      <div v-if="diffEmpty" class="pv-diff-empty">两个版本内容完全一致，无差异。</div>
      <el-collapse v-else v-model="activeDiffSections" class="pv-diff-collapse">
        <el-collapse-item
          v-for="sec in diffSections"
          :key="sec.key"
          :name="sec.key"
          :title="`${sec.label}（新增 ${sec.data.added.length} / 删除 ${sec.data.removed.length} / 修改 ${sec.data.modified.length}）`"
        >
          <div v-if="sec.data.added.length + sec.data.removed.length + sec.data.modified.length === 0" class="pv-muted pv-sub-empty">
            无变化
          </div>
          <div v-else class="pv-diff-list">
            <div v-for="item in sec.data.added" :key="'a-'+sec.key+item.key" class="pv-diff-row add">
              <span class="pv-diff-sign">+</span>
              <span class="pv-diff-key">{{ item.key }}</span>
            </div>
            <div v-for="item in sec.data.removed" :key="'r-'+sec.key+item.key" class="pv-diff-row del">
              <span class="pv-diff-sign">-</span>
              <span class="pv-diff-key">{{ item.key }}</span>
            </div>
            <div v-for="item in sec.data.modified" :key="'m-'+sec.key+item.key" class="pv-diff-row mod">
              <span class="pv-diff-sign">~</span>
              <span class="pv-diff-key">{{ item.key }}</span>
              <el-button link type="primary" size="small" @click="onShowFieldDiff(sec.key, item)">查看详情</el-button>
            </div>
          </div>
        </el-collapse-item>
      </el-collapse>
    </div>
    <template #footer>
      <el-button @click="diffVisible = false">关闭</el-button>
    </template>
  </el-dialog>

  <!-- 字段级 Diff 弹窗 -->
  <el-dialog
    v-model="fieldDiffVisible"
    :title="fieldDiffTitle"
    width="860px"
    align-center
    :close-on-click-modal="false"
    append-to-body
    class="pv-diff-dialog"
  >
    <div v-if="fieldDiffLines.length" class="pv-diff-body">
      <div v-for="(line, idx) in fieldDiffLines" :key="idx" :class="['pv-diff-line', line.type]">
        <span class="pv-diff-prefix">{{ line.type === 'add' ? '+' : line.type === 'del' ? '-' : ' ' }}</span>
        <span class="pv-diff-text">{{ line.text || ' ' }}</span>
      </div>
    </div>
    <div v-else class="pv-diff-empty">无差异</div>
    <template #footer>
      <el-button @click="fieldDiffVisible = false">关闭</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Check, Right } from '@element-plus/icons-vue'
import {
  projectVersionApi,
  type ProjectVersionListItem,
  type ProjectVersionDiff,
  type CollectionDiff,
} from '@/api'
import { formatTime } from '@/utils/format'

const props = defineProps<{ projectId: number | null }>()
const emit = defineEmits<{
  rollback: []
}>()

/** 弹窗显隐：defineModel 双向绑定（Vue 3.4+，替代手写 modelValue + computed get/set 样板） */
const visible = defineModel<boolean>({ default: false })

const versions = ref<ProjectVersionListItem[]>([])
const loading = ref(false)
const baseId = ref<number | null>(null)
const targetId = ref<number | null>(null)

const baseVerNo = computed(() => versions.value.find(v => v.id === baseId.value)?.version_no)
const targetVerNo = computed(() => versions.value.find(v => v.id === targetId.value)?.version_no)

async function loadVersions() {
  if (!props.projectId) return
  loading.value = true
  baseId.value = null
  targetId.value = null
  try {
    versions.value = await projectVersionApi.list(props.projectId)
    if (versions.value.length >= 2) {
      targetId.value = versions.value[0].id
      baseId.value = versions.value[1].id
    }
  } catch (e: any) {
    ElMessage.error(e.message || '加载版本列表失败')
  } finally {
    loading.value = false
  }
}

// ============ 创建快照 ============
const createVisible = ref(false)
const creating = ref(false)
const createForm = ref({ name: '', description: '' })

function onOpenCreate() {
  const nextNo = versions.value.length ? versions.value[0].version_no + 1 : 1
  createForm.value = { name: `v${nextNo}.0`, description: '' }
  createVisible.value = true
}

async function onCreate() {
  if (!createForm.value.name.trim()) {
    ElMessage.warning('请输入版本名称')
    return
  }
  if (!props.projectId) return
  creating.value = true
  try {
    await projectVersionApi.create(props.projectId, {
      name: createForm.value.name.trim(),
      description: createForm.value.description.trim() || undefined,
    })
    ElMessage.success('已保存新版本')
    createVisible.value = false
    await loadVersions()
  } catch (e: any) {
    ElMessage.error(e.message || '保存失败')
  } finally {
    creating.value = false
  }
}

// ============ 回滚 ============
async function onRollback(row: ProjectVersionListItem) {
  try {
    await ElMessageBox.confirm(
      `确认回滚到版本「v${row.version_no}（${row.name}）」？\n\n此操作会删除当前所有接口和用例，用快照数据重建。回滚前会自动保存一个「回滚前快照」以确保可恢复`,
      '提示',
      { type: 'warning', confirmButtonText: '回滚', cancelButtonText: '取消' }
    )
  } catch {
    return
  }
  try {
    const res = await projectVersionApi.rollback(row.id)
    ElMessage.success(res.message)
    emit('rollback')
    visible.value = false
  } catch (e: any) {
    ElMessage.error(e.message || '回滚失败')
  }
}

// ============ 删除 ============
async function onDelete(row: ProjectVersionListItem) {
  try {
    await ElMessageBox.confirm(
      `确认删除版本「v${row.version_no}（${row.name}）」？此操作不可恢复`,
      '提示',
      { type: 'warning' }
    )
  } catch {
    return
  }
  try {
    await projectVersionApi.remove(row.id)
    ElMessage.success('已删除')
    if (baseId.value === row.id) baseId.value = null
    if (targetId.value === row.id) targetId.value = null
    await loadVersions()
  } catch (e: any) {
    ElMessage.error(e.message || '删除失败')
  }
}

// ============ Diff 对比 ============
const diffVisible = ref(false)
const diffLoading = ref(false)
const diffData = ref<ProjectVersionDiff | null>(null)
const activeDiffSections = ref<string[]>([])

const DIFF_LABELS: Record<string, string> = {
  api_groups: '接口分组',
  case_groups: '用例分组',
  apis: '接口',
  cases: '用例',
}

const diffSections = computed(() => {
  if (!diffData.value) return []
  return (Object.keys(DIFF_LABELS)).map(key => ({
    key,
    label: DIFF_LABELS[key],
    data: (diffData.value!.diff as any)[key] as CollectionDiff,
  }))
})

const diffEmpty = computed(() => {
  if (!diffData.value) return true
  return diffSections.value.every(s => s.data.added.length + s.data.removed.length + s.data.modified.length === 0)
})

const diffSummary = computed(() => {
  if (!diffData.value) return ''
  let added = 0, removed = 0, modified = 0
  for (const s of diffSections.value) {
    added += s.data.added.length
    removed += s.data.removed.length
    modified += s.data.modified.length
  }
  return `共 ${added + removed + modified} 处变化（+${added} / -${removed} / ~${modified}）`
})

async function onDiff() {
  if (!baseId.value || !targetId.value || baseId.value === targetId.value) return
  diffLoading.value = true
  try {
    diffData.value = await projectVersionApi.diff(baseId.value, targetId.value)
    // 默认展开有变化的分组
    activeDiffSections.value = diffSections.value
      .filter(s => s.data.added.length + s.data.removed.length + s.data.modified.length > 0)
      .map(s => s.key)
    diffVisible.value = true
  } catch (e: any) {
    ElMessage.error(e.message || '对比失败')
  } finally {
    diffLoading.value = false
  }
}

// ============ 字段级 Diff ============
const fieldDiffVisible = ref(false)
const fieldDiffTitle = ref('')
const fieldDiffLines = ref<{ type: 'same' | 'add' | 'del'; text: string }[]>([])

function diffTextLines(a: any, b: any): { type: 'same' | 'add' | 'del'; text: string }[] {
  const la = JSON.stringify(a, null, 2).split('\n')
  const lb = JSON.stringify(b, null, 2).split('\n')
  const m = la.length, n = lb.length
  const dp: number[][] = Array.from({ length: m + 1 }, () => new Array(n + 1).fill(0))
  for (let i = m - 1; i >= 0; i--) {
    for (let j = n - 1; j >= 0; j--) {
      if (la[i] === lb[j]) dp[i][j] = dp[i + 1][j + 1] + 1
      else dp[i][j] = Math.max(dp[i + 1][j], dp[i][j + 1])
    }
  }
  const res: { type: 'same' | 'add' | 'del'; text: string }[] = []
  let i = 0, j = 0
  while (i < m && j < n) {
    if (la[i] === lb[j]) { res.push({ type: 'same', text: la[i] }); i++; j++ }
    else if (dp[i + 1][j] >= dp[i][j + 1]) { res.push({ type: 'del', text: la[i] }); i++ }
    else { res.push({ type: 'add', text: lb[j] }); j++ }
  }
  while (i < m) { res.push({ type: 'del', text: la[i] }); i++ }
  while (j < n) { res.push({ type: 'add', text: lb[j] }); j++ }
  return res
}

function onShowFieldDiff(sectionKey: string, item: { key: string; base: any; target: any }) {
  fieldDiffTitle.value = `${DIFF_LABELS[sectionKey]} · ${item.key} · 字段对比`
  fieldDiffLines.value = diffTextLines(item.base, item.target)
  fieldDiffVisible.value = true
}
</script>

<!-- 非 scoped：el-dialog teleport 到 body，scoped 样式会失效；类名统一 pv- 前缀避免全局污染 -->
<style>
.pv-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}
.pv-hint {
  font-size: 13px;
  color: var(--app-text-muted);
}
.pv-ver {
  font-weight: 600;
  color: var(--app-primary);
}
.pv-muted {
  color: var(--app-text-faint);
}
.pv-diff-tip {
  margin-top: 10px;
  font-size: 13px;
  color: var(--app-text-muted);
}
.pv-diff-tip b {
  color: var(--app-primary);
}

.pv-diff-wrap {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.pv-diff-header {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.pv-diff-arrow {
  color: var(--app-text-muted);
}
.pv-diff-summary {
  margin-left: auto;
  font-size: 13px;
  color: var(--app-text-muted);
}
.pv-diff-empty,
.pv-sub-empty {
  padding: 16px;
  text-align: center;
  color: var(--app-text-muted);
}
.pv-diff-collapse .el-collapse-item__header {
  font-weight: 500;
}
.pv-diff-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.pv-diff-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 13px;
}
.pv-diff-row.add {
  background: var(--app-success-bg);
  color: var(--app-success-text);
}
.pv-diff-row.del {
  background: var(--app-danger-bg);
  color: var(--app-danger-text);
}
.pv-diff-row.mod {
  background: var(--app-warn-bg);
  color: var(--app-warn-text);
}
.pv-diff-sign {
  font-weight: 700;
  width: 14px;
}
.pv-diff-key {
  flex: 1;
}

.pv-diff-body {
  background: var(--app-hover);
  border-radius: var(--app-radius-sm);
  font-family: 'JetBrains Mono', Consolas, Monaco, monospace;
  font-size: 12px;
  line-height: 1.6;
  overflow-x: auto;
  max-height: 56vh;
  overflow-y: auto;
}
.pv-diff-line {
  display: flex;
  white-space: pre;
}
.pv-diff-prefix {
  flex: 0 0 22px;
  text-align: center;
  user-select: none;
  color: var(--app-text-faint);
}
.pv-diff-line.del {
  background: var(--app-danger-bg);
}
.pv-diff-line.del .pv-diff-prefix {
  color: var(--app-danger-text);
}
.pv-diff-line.add {
  background: var(--app-success-bg);
}
.pv-diff-line.add .pv-diff-prefix {
  color: var(--app-success-text);
}
.pv-diff-text {
  flex: 1;
}

/* ===== 版本对比弹窗：固定在视口内，header/footer 固定，body 内部滚动（参考 help-dialog） ===== */
.pv-diff-dialog.el-dialog {
  margin-top: 0 !important;
  margin-bottom: 0;
  max-height: 86vh;
  display: flex;
  flex-direction: column;
}
.pv-diff-dialog .el-dialog__header {
  flex-shrink: 0;
  margin-right: 0;
}
.pv-diff-dialog .el-dialog__body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding-right: 18px;
}
.pv-diff-dialog .el-dialog__footer {
  flex-shrink: 0;
}
.pv-diff-dialog .el-dialog__body::-webkit-scrollbar {
  width: 8px;
}
.pv-diff-dialog .el-dialog__body::-webkit-scrollbar-track {
  background: transparent;
}
.pv-diff-dialog .el-dialog__body::-webkit-scrollbar-thumb {
  background: var(--app-border);
  border-radius: 4px;
}
.pv-diff-dialog .el-dialog__body::-webkit-scrollbar-thumb:hover {
  background: var(--app-text-muted);
}
</style>

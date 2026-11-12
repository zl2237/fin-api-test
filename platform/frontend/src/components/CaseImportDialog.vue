<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { UploadFilled } from '@element-plus/icons-vue'
import { caseApi, type CaseImportResult, type Environment } from '../api'
import type { GroupTreeNode } from '../composables/useGroupedTable'

/**
 * 用例导入弹窗：两段式——先「预演」（dry_run 接口复用/新建统计，不落库），
 * 核对无误后选分组/环境「确认导入」。载荷来自平台「导出 JSON 全量」（v2 迁移包），
 * 支持上传 .json 文件或直接粘贴文本；v1 旧文件后端会明确拒绝。
 * （与 fin-ui-test 同构，裁剪了 UI 元素/动作资产统计。）
 *
 * 大包性能：上传文件的内容只存内存（fileText），绝不灌进 textarea（多 MB 文本
 * 进受控输入会冻结页面）；预演的警告/用例明细列表限高滚动 + 明细分页，
 * 弹窗体整体 max-height 兜底，用例再多也不会撑出视口。
 */
const props = defineProps<{
  modelValue: boolean
  projectId: number
  /** useGroupTree.treeSelectWithUngrouped（含 id=0 的「未分组」虚拟节点） */
  treeData: GroupTreeNode[]
  envs: Environment[]
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'imported'): void
}>()

const visible = computed({
  get: () => props.modelValue,
  set: (v: boolean) => emit('update:modelValue', v),
})

// 步骤态：choose 选载荷 → preview 预演结果（可确认）
type Step = 'choose' | 'preview'
const step = ref<Step>('choose')
const pastedText = ref('')
const fileText = ref('')
const fileName = ref('')
const payload = ref<Record<string, any> | null>(null)
const previewing = ref(false)
const importing = ref(false)
const preview = ref<CaseImportResult | null>(null)
const targetGroup = ref<number | null>(null)
const targetEnv = ref<number | null>(null)
const treeProps = { label: 'label', children: 'children' }

// 有效载荷文本：上传文件优先，退回粘贴内容
const rawText = computed(() => fileText.value || pastedText.value)

watch(() => props.modelValue, (v) => {
  if (v) {
    step.value = 'choose'
    pastedText.value = ''
    fileText.value = ''
    fileName.value = ''
    payload.value = null
    preview.value = null
    targetGroup.value = null
    targetEnv.value = null
    page.value = 1
  }
})

async function onFileChange(file: any) {
  if (!file?.raw) return
  try {
    fileText.value = await file.raw.text()
    fileName.value = file.name
  } catch {
    ElMessage.error('读取文件失败')
  }
}

function onFileRemove() {
  fileText.value = ''
  fileName.value = ''
}

function parsePayload(): boolean {
  if (!rawText.value.trim()) {
    ElMessage.warning(fileName.value ? '文件内容为空' : '请先上传导出的 JSON 文件或粘贴内容')
    return false
  }
  try {
    const obj = JSON.parse(rawText.value)
    if (typeof obj !== 'object' || obj === null || Array.isArray(obj)) {
      throw new Error('not an object')
    }
    payload.value = obj
    return true
  } catch {
    ElMessage.error('内容不是合法的 JSON 对象，请检查文件（应为平台「导出 JSON 全量」产物）')
    return false
  }
}

async function onPreview() {
  if (!parsePayload()) return
  previewing.value = true
  try {
    preview.value = await caseApi.importCases({
      payload: payload.value!, project_id: props.projectId, dry_run: true,
    })
    page.value = 1
    step.value = 'preview'
  } catch (e: any) {
    ElMessage.error(e.message || '预演失败')
  } finally {
    previewing.value = false
  }
}

async function onImport() {
  if (!payload.value) return
  importing.value = true
  try {
    const result = await caseApi.importCases({
      payload: payload.value,
      project_id: props.projectId,
      group_id: targetGroup.value === 0 ? null : targetGroup.value,
      env_id: targetEnv.value,
      dry_run: false,
    })
    const c = result.created!
    ElMessage.success(`已导入 ${c.cases} 个用例（新建接口 ${c.apis}）`)
    visible.value = false
    emit('imported')
  } catch (e: any) {
    ElMessage.error(e.message || '导入失败')
  } finally {
    importing.value = false
  }
}

/** 接口复用/新建 tag 行数据（空项过滤） */
const assetTags = computed(() => {
  const p = preview.value
  if (!p) return []
  const tags: { label: string; ok: boolean }[] = []
  const add = (n: number, verb: string, word: string, ok: boolean) => {
    if (n > 0) tags.push({ label: `${verb}${word} ${n}`, ok })
  }
  add(p.reuse_apis?.length || 0, '复用', '接口', true)
  add(p.create_apis?.length || 0, '新建', '接口', false)
  return tags
})

// ===== 用例明细分页（大包几百行全量渲染会卡，每页 20 条）=====
const PAGE_SIZE = 20
const page = ref(1)
const pagedCases = computed(() => {
  const all = preview.value?.cases || []
  return all.slice((page.value - 1) * PAGE_SIZE, page.value * PAGE_SIZE)
})
</script>

<template>
  <el-dialog v-model="visible" title="导入用例" width="680px" align-center :close-on-click-modal="false">
    <div class="dialog-body">
      <!-- 步骤 1：选择载荷 -->
      <template v-if="step === 'choose'">
        <el-upload
          drag
          :auto-upload="false"
          accept=".json"
          :limit="1"
          :on-change="onFileChange"
          :on-remove="onFileRemove"
        >
          <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
          <div class="el-upload__text">拖入或点击选择「导出 JSON 全量」文件</div>
          <template #tip>
            <div class="el-upload__tip">v2 迁移包：含节点编排、数据集行与接口定义快照，跨项目导入自动按 method+path 复用已有接口</div>
          </template>
        </el-upload>
        <div class="paste-row">或粘贴 JSON 内容{{ fileText ? '（已选择文件，将以文件为准）' : '：' }}</div>
        <el-input v-model="pastedText" type="textarea" :rows="5" :disabled="!!fileText" placeholder='{"exported_at": "...", "type": "cases", "version": 2, ...}' />
      </template>

      <!-- 步骤 2：预演结果 + 确认 -->
      <template v-else-if="preview">
        <el-alert type="info" :closable="false">
          将导入 <b>{{ preview.case_count }}</b> 个用例（含节点编排与数据集行；环境配置与契约模板绑定不随包迁移）
        </el-alert>
        <div class="asset-tags">
          <el-tag v-for="t in assetTags" :key="t.label" size="small" :type="t.ok ? 'success' : 'warning'" effect="plain">
            {{ t.label }}
          </el-tag>
        </div>
        <div v-if="preview.warnings?.length" class="warn-box">
          <div class="warn-title">警告 {{ preview.warnings.length }} 条</div>
          <div class="warn-items">
            <div v-for="(w, i) in preview.warnings" :key="i" class="warn-item">{{ w }}</div>
          </div>
        </div>
        <el-collapse style="margin-top: 12px">
          <el-collapse-item :title="`用例明细（${preview.cases?.length || 0}）`">
            <el-table :data="pagedCases" size="small" max-height="260">
              <el-table-column prop="name" label="用例" min-width="180" show-overflow-tooltip />
              <el-table-column prop="nodes" label="节点" width="90" align="center" />
              <el-table-column prop="datasets" label="数据集" width="90" align="center" />
              <el-table-column prop="rows" label="数据行" width="90" align="center" />
            </el-table>
            <el-pagination
              v-if="(preview.cases?.length || 0) > PAGE_SIZE"
              v-model:current-page="page"
              :page-size="PAGE_SIZE"
              :total="preview.cases?.length || 0"
              layout="prev, pager, next"
              size="small"
              class="case-pager"
            />
          </el-collapse-item>
        </el-collapse>
        <div class="config-row">
          <el-tree-select
            v-model="targetGroup"
            :data="treeData"
            node-key="id"
            :props="treeProps"
            placeholder="导入到分组（默认未分组）"
            clearable
            filterable
            check-strictly
            style="flex: 1"
          />
          <el-select v-model="targetEnv" placeholder="统一绑定环境（可选）" clearable style="flex: 1">
            <el-option v-for="e in envs" :key="e.id" :label="e.name" :value="e.id" />
          </el-select>
        </div>
        <div v-if="targetEnv === null" class="env-tip">不绑定时导入的用例无法直接执行，需在用例编辑中选择环境</div>
      </template>
    </div>

    <template #footer>
      <template v-if="step === 'choose'">
        <el-button @click="visible = false">取消</el-button>
        <el-button type="primary" :loading="previewing" @click="onPreview">预演导入</el-button>
      </template>
      <template v-else>
        <el-button @click="step = 'choose'">重新选择</el-button>
        <el-button type="primary" :loading="importing" @click="onImport">确认导入</el-button>
      </template>
    </template>
  </el-dialog>
</template>

<style scoped>
.dialog-body {
  max-height: calc(100vh - 240px);
  overflow-y: auto;
  padding-right: 4px;
}
.paste-row {
  margin: 12px 0 6px;
  color: var(--app-text-muted);
  font-size: 13px;
}
.asset-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 12px;
}
.warn-box {
  margin-top: 8px;
  border: 1px solid var(--el-color-warning-light-5);
  border-radius: 4px;
  background: var(--el-color-warning-light-9);
}
.warn-title {
  padding: 6px 10px 2px;
  font-size: 12px;
  font-weight: 600;
  color: var(--el-color-warning);
}
.warn-items {
  max-height: 110px;
  overflow-y: auto;
  padding: 2px 10px 8px;
}
.warn-item {
  font-size: 12px;
  line-height: 1.7;
  color: var(--el-color-warning);
  word-break: break-all;
}
.case-pager {
  margin-top: 8px;
  justify-content: flex-end;
}
.config-row {
  display: flex;
  gap: 12px;
  margin-top: 14px;
}
.env-tip {
  margin-top: 6px;
  font-size: 12px;
  color: var(--app-text-faint);
}
</style>

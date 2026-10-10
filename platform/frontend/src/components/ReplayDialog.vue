<template>
  <el-dialog
    :model-value="visible"
    title="编辑并重放节点"
    width="1080px"
    :close-on-click-modal="false"
    class="replay-dialog"
    @update:model-value="(v: boolean) => emit('update:visible', v)"
  >
    <el-alert
      type="info"
      :closable="false"
      style="margin-bottom: 10px"
      title="按原执行环境真实重发一次（写接口有副作用）；${} 用报告上下文重新求值，发送后同口径跑断言与提取——通过仅打「已重放通过」徽标，不写回报告"
    />
    <div class="replay-split">
      <div class="replay-left">
        <div class="section-title">请求体（编辑后点右下角「重放」）</div>
        <el-input
          v-model="replayBodyText"
          type="textarea"
          :rows="22"
          class="mono replay-body-input"
          spellcheck="false"
          placeholder="JSON 请求体"
        />
      </div>
      <div class="replay-right">
        <template v-if="replayResult">
          <div class="section-title" style="display: flex; align-items: center; gap: 8px">
            重放结果：HTTP {{ replayResult.status_code }} · {{ replayResult.elapsed_ms }} ms
            <el-tag v-if="replayResult.passed" type="success" size="small">断言全过</el-tag>
            <el-tag v-else type="danger" size="small">未通过</el-tag>
          </div>
          <VueJsonPretty :data="replayResult.response_body" :deep="4" />
          <template v-if="replayResult.assertions?.length">
            <div class="section-title" style="margin-top: 12px">断言（{{ replayResult.assertions.filter(a => a.pass).length }}/{{ replayResult.assertions.length }} 通过）</div>
            <div v-for="(a, i) in replayResult.assertions" :key="i" class="replay-assertion" :class="{ fail: !a.pass }">
              <el-tag :type="a.pass ? 'success' : 'danger'" size="small" effect="light">{{ a.pass ? '通过' : '失败' }}</el-tag>
              <span class="mono">{{ a.type }}</span>
              <span v-if="a.message" class="replay-assertion-msg">{{ a.message }}</span>
            </div>
          </template>
          <template v-if="replayResult.extracted && Object.keys(replayResult.extracted).length">
            <div class="section-title" style="margin-top: 12px">本次提取（断点续跑时并入上下文）</div>
            <VueJsonPretty :data="replayResult.extracted" :deep="2" />
          </template>
          <el-alert
            v-if="replayResult.passed"
            type="success"
            :closable="false"
            style="margin-top: 12px"
            title="验证通过：请把正确参数同步到数据集/节点配置，然后点「断点续跑」从该节点真实重跑"
          />
        </template>
        <EmptyState v-else description="点击右下角「重放」后在此查看结果" :image-size="60" />
      </div>
    </div>
    <template #footer>
      <el-button @click="emit('update:visible', false)">关闭</el-button>
      <el-button type="primary" :loading="replayLoading" @click="doReplay">重放</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
/**
 * 节点编辑重放（ReportDetail 迁出）：左右布局——左请求体常驻不滚走，
 * 右结果独立滚动。重放走 execApi.replayStep；通过后 emit('replayed')
 * 由父级静默刷新（列表「已重放通过」徽标数据源在后端步骤打点上）。
 */
import { ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import VueJsonPretty from 'vue-json-pretty'
import 'vue-json-pretty/lib/styles.css'
import EmptyState from '@/components/EmptyState.vue'
import { execApi } from '@/api'

const props = defineProps<{
  visible: boolean
  stepId: number | null
  /** 打开时的请求体快照（JSON 序列化展示与编辑） */
  initialBody: unknown
}>()
const emit = defineEmits<{ (e: 'update:visible', v: boolean): void; (e: 'replayed', passed: boolean): void }>()

const replayLoading = ref(false)
const replayBodyText = ref('')
const replayResult = ref<{ status_code: number; response_body: any; elapsed_ms: number; passed: boolean; assertions: { type: string; pass: boolean; message?: string }[]; extracted: Record<string, any> } | null>(null)

watch(
  () => props.visible,
  (v) => {
    if (v) {
      replayBodyText.value = JSON.stringify(props.initialBody ?? {}, null, 2)
      replayResult.value = null
    }
  },
)

async function doReplay() {
  if (!props.stepId) return
  let body: unknown
  try {
    body = JSON.parse(replayBodyText.value)
  } catch (e: any) {
    ElMessage.error(`请求体 JSON 解析失败：${e.message}`)
    return
  }
  replayLoading.value = true
  try {
    replayResult.value = await execApi.replayStep(props.stepId, body)
    emit('replayed', replayResult.value.passed)
  } catch (e: any) {
    ElMessage.error(e.message || '重放失败')
  } finally {
    replayLoading.value = false
  }
}
</script>

<style scoped>
.mono {
  font-family: var(--app-font-mono);
  font-size: 12px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.section-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--app-text);
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}
/* 断言行：通过/失败 + 类型 + 消息 */
.replay-assertion {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 0;
  font-size: 13px;
}
.replay-assertion.fail {
  color: var(--el-color-danger);
}
.replay-assertion-msg {
  color: var(--el-text-color-secondary);
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
/* 左右布局：左请求体常驻 + 右结果独立滚动（解决滚动看结果时请求体滚走的痛点） */
.replay-split {
  display: flex;
  gap: 14px;
  align-items: stretch;
}
.replay-left {
  flex: 0 0 46%;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
/* textarea 撑满左侧高度，与右侧等高 */
.replay-body-input :deep(.el-textarea__inner) {
  font-family: Consolas, Menlo, 'Liberation Mono', monospace;
  font-size: 12px;
  line-height: 1.6;
  resize: vertical;
}
.replay-right {
  flex: 1;
  min-width: 0;
  max-height: 64vh;
  overflow-y: auto;
  padding-left: 14px;
  border-left: 1px solid var(--el-border-color);
}
/* 窄屏回退上下布局（避免挤压不可用） */
@media (max-width: 900px) {
  .replay-split {
    flex-direction: column;
  }
  .replay-left {
    flex: none;
  }
  .replay-right {
    max-height: none;
    padding-left: 0;
    border-left: none;
    border-top: 1px solid var(--el-border-color);
    padding-top: 10px;
  }
}
</style>

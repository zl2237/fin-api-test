<template>
  <el-drawer
    :model-value="visible"
    @update:model-value="$emit('update:visible', $event)"
    title="节点配置"
    size="min(780px, 92vw)"
    direction="rtl"
    class="node-config-drawer"
    destroy-on-close
  >
    <el-tabs v-if="draft" v-model="activeTab" class="node-config-tabs">
      <el-tab-pane label="基础配置" name="basic">
        <el-form label-width="90px">
          <el-form-item label="节点ID">
            <el-input :model-value="draft.node_id" disabled />
          </el-form-item>
          <el-form-item label="绑定接口" required>
            <el-select v-model="draft.api_id" placeholder="选择接口（必选）" filterable style="width: 100%">
              <el-option
                v-for="a in apis"
                :key="a.id"
                :label="`${a.name} (${a.method} ${a.path})`"
                :value="a.id"
              />
            </el-select>
          </el-form-item>
          <el-form-item label="等待时间">
            <el-input-number
              v-model="waitAfterMs"
              :min="0"
              :step="500"
              :step-strict="false"
              controls-position="right"
              style="width: 180px"
            />
            <span class="wait-unit">ms</span>
            <p class="tip wait-tip">当前接口执行完成后、下一个接口请求前的等待间隔，给后端处理事务/数据落库留出时间。默认 0（不等待）。</p>
          </el-form-item>
        </el-form>
      </el-tab-pane>

      <el-tab-pane label="前置处理" name="pre">
        <PreProcessTable v-model="draft.pre_process" :fields="currentApiFields" />
        <div class="tip-with-help">
          <p class="tip">设置字段值支持表达式：<code>${order_id}</code>、<code>${generate_bl_no(prefix='smoke')}</code>。遍历赋值用于费用 unique_id 关联。</p>
          <el-button text size="small" class="help-link" @click="store.openCoreCapability('expression')">
            <el-icon><QuestionFilled /></el-icon> 查看表达式用法
          </el-button>
        </div>
      </el-tab-pane>

      <el-tab-pane label="后置提取" name="extract">
        <PostExtractTable v-model="draft.post_extract" />
        <p class="tip">提取的变量存入上下文，供后续节点以 <code>${变量名}</code> 引用。</p>
      </el-tab-pane>

      <el-tab-pane label="断言规则" name="assert">
        <AssertionTable v-model="draft.assertions" />
        <div class="tip-with-help">
          <p class="tip">DB 断言 SQL 中可用 <code>${变量名}</code> 引用已提取变量。</p>
          <el-button text size="small" class="help-link" @click="store.openCoreCapability('assertion')">
            <el-icon><QuestionFilled /></el-icon> 查看断言规则
          </el-button>
        </div>
      </el-tab-pane>
    </el-tabs>

    <template #footer>
      <el-button @click="$emit('update:visible', false)">取消</el-button>
      <!-- 双层保存语义：此处仅应用到画布，持久化需再点画布右上「保存用例」 -->
      <el-button type="primary" @click="onSave">应用配置</el-button>
    </template>
  </el-drawer>
</template>

<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { QuestionFilled } from '@element-plus/icons-vue'
import PreProcessTable from './PreProcessTable.vue'
import PostExtractTable from './PostExtractTable.vue'
import AssertionTable from './AssertionTable.vue'
import { useAppStore } from '@/stores'
import type { ApiDef, NodeConfig, ApiField } from '@/api'

const store = useAppStore()

const props = defineProps<{
  visible: boolean
  config: NodeConfig
  apis: ApiDef[]
}>()
const emit = defineEmits<{
  (e: 'update:visible', v: boolean): void
  (e: 'save', config: NodeConfig): void
}>()

const activeTab = ref('basic')

// 编辑草稿：打开抽屉时深拷贝一份，避免直接 mutate 父组件引用导致
// 「关闭即生效、保存按钮无实义」的假保存语义；取消即丢弃草稿。
const draft = ref<NodeConfig | null>(null)
watch(
  () => props.visible,
  (v) => {
    if (v) {
      draft.value = JSON.parse(JSON.stringify(props.config))
    }
  },
  { immediate: true },
)

// 当前节点绑定接口的请求字段，供前置处理字段路径选择
const currentApiFields = computed<ApiField[]>(() => {
  if (!draft.value?.api_id) return []
  const api = props.apis.find((a) => a.id === draft.value!.api_id)
  return api?.fields || []
})

// 节点间等待时间（ms），默认 0；用 computed 兼容旧数据未携带该字段的情况
const waitAfterMs = computed<number>({
  get: () => draft.value?.wait_after_ms ?? 0,
  set: (v: number) => { if (draft.value) draft.value.wait_after_ms = v },
})

function onSave() {
  if (!draft.value) return
  if (!draft.value.api_id) {
    ElMessage.warning('请先绑定接口，未绑定接口的节点不会执行')
    return
  }
  emit('save', JSON.parse(JSON.stringify(draft.value)))
  emit('update:visible', false)
  ElMessage.success('已应用到画布；点右上角「保存用例」持久化')
}
</script>

<style scoped>
.tip {
  margin-top: 12px;
  font-size: 12px;
  color: var(--app-text-muted);
  line-height: 1.6;
}
.tip code {
  background: var(--app-hover);
  padding: 1px 5px;
  border-radius: var(--app-radius-xs);
}
.tip-with-help {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  margin-top: 12px;
}
.tip-with-help .tip {
  margin-top: 0;
  flex: 1;
  min-width: 0;
}
.help-link {
  flex-shrink: 0;
  color: var(--app-primary);
  padding: 0;
  height: auto;
}
.help-link .el-icon {
  margin-right: 4px;
  font-size: 14px;
}
.help-link:hover {
  opacity: 0.8;
}
.wait-unit {
  margin-left: 8px;
  color: var(--app-text-muted);
  font-size: 13px;
}
.wait-tip {
  margin-top: 6px;
  margin-bottom: 0;
}
</style>

<!-- el-drawer teleport 到 body，scoped 无法命中外层元素，需用全局样式 -->
<style>
/* drawer body 改为 flex 布局：tabs header 固定，content 区域独立滚动 */
.node-config-drawer .el-drawer__body {
  display: flex;
  flex-direction: column;
  overflow: hidden;
  padding: 0;
}
/* tabs 占满 body 高度 */
.node-config-tabs {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
}
/* tabs header 固定在顶部 */
.node-config-tabs > .el-tabs__header {
  flex-shrink: 0;
  margin-bottom: 0;
  padding: 0 20px;
}
/* tab content 区域独立滚动 */
.node-config-tabs > .el-tabs__content {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 16px 20px;
}
/* 自定义滚动条 */
.node-config-tabs > .el-tabs__content::-webkit-scrollbar {
  width: 8px;
}
.node-config-tabs > .el-tabs__content::-webkit-scrollbar-track {
  background: transparent;
}
.node-config-tabs > .el-tabs__content::-webkit-scrollbar-thumb {
  background: var(--app-border);
  border-radius: 4px;
}
.node-config-tabs > .el-tabs__content::-webkit-scrollbar-thumb:hover {
  background: var(--app-text-muted);
}
</style>

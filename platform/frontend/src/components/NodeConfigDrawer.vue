<template>
  <el-drawer
    :model-value="visible"
    @update:model-value="$emit('update:visible', $event)"
    title="节点配置"
    size="640px"
    direction="rtl"
  >
    <el-tabs v-model="activeTab">
      <el-tab-pane label="基础配置" name="basic">
        <el-form label-width="90px">
          <el-form-item label="节点ID">
            <el-input :model-value="config.node_id" disabled />
          </el-form-item>
          <el-form-item label="绑定接口">
            <el-select v-model="config.api_id" placeholder="选择接口" filterable style="width: 100%">
              <el-option
                v-for="a in apis"
                :key="a.id"
                :label="`${a.name} (${a.method} ${a.path})`"
                :value="a.id"
              />
            </el-select>
          </el-form-item>
        </el-form>
      </el-tab-pane>

      <el-tab-pane label="前置处理" name="pre">
        <PreProcessTable v-model="config.pre_process" :fields="currentApiFields" />
        <p class="tip">设置字段值支持表达式：<code>${order_id}</code>、<code>${generate_bl_no(prefix='smoke')}</code>。遍历赋值用于费用 unique_id 关联。</p>
      </el-tab-pane>

      <el-tab-pane label="后置提取" name="extract">
        <PostExtractTable v-model="config.post_extract" />
        <p class="tip">提取的变量存入上下文，供后续节点以 <code>${变量名}</code> 引用。</p>
      </el-tab-pane>

      <el-tab-pane label="断言规则" name="assert">
        <AssertionTable v-model="config.assertions" />
        <p class="tip">DB 断言 SQL 中可用 <code>${变量名}</code> 引用已提取变量。</p>
      </el-tab-pane>
    </el-tabs>

    <template #footer>
      <el-button @click="$emit('update:visible', false)">关闭</el-button>
      <el-button type="primary" @click="onSave">保存配置</el-button>
    </template>
  </el-drawer>
</template>

<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import { ElMessage } from 'element-plus'
import PreProcessTable from './PreProcessTable.vue'
import PostExtractTable from './PostExtractTable.vue'
import AssertionTable from './AssertionTable.vue'
import type { ApiDef, NodeConfig, ApiField } from '@/api'

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

// 当前节点绑定接口的请求字段，供前置处理字段路径选择
const currentApiFields = computed<ApiField[]>(() => {
  if (!props.config.api_id) return []
  const api = props.apis.find((a) => a.id === props.config.api_id)
  return api?.fields || []
})

function onSave() {
  emit('save', { ...props.config })
  ElMessage.success('节点配置已保存（点击右上角「保存用例」持久化）')
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
  border-radius: 4px;
}
</style>

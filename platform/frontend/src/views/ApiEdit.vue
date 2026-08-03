<template>
  <div class="api-edit">
    <!-- 顶部工具栏 -->
    <div class="edit-header">
      <el-button @click="onBack">
        <el-icon><ArrowLeft /></el-icon>返回
      </el-button>
      <span class="edit-title">{{ isEdit ? '编辑接口' : '新建接口' }}</span>
      <div class="header-right">
        <span v-if="dirty" class="dirty-tip">有未保存改动</span>
        <el-button v-if="isEdit" type="success" :loading="debugging" @click="openDebug">调试</el-button>
        <el-button type="primary" :loading="saving" @click="onSave">保存</el-button>
      </div>
    </div>

    <!-- 调试弹窗 -->
    <el-dialog v-model="debugVisible" title="接口调试" width="780px" :close-on-click-modal="false">
      <div class="debug-bar">
        <el-select v-model="debugEnvId" placeholder="选择环境" style="width: 200px" :disabled="debugging">
          <el-option v-for="e in store.environments" :key="e.id" :label="e.name" :value="e.id" />
        </el-select>
        <el-button type="success" :loading="debugging" :disabled="!debugEnvId" @click="onDebug">
          发送请求
        </el-button>
        <span v-if="debugResult" class="debug-meta">
          <el-tag :type="debugResult.ok ? 'success' : 'danger'" size="small" effect="plain" round>
            {{ debugResult.ok ? '成功' : '失败' }}
          </el-tag>
          <el-tag v-if="debugResult.response_status" size="small" type="info" effect="plain" round>
            HTTP {{ debugResult.response_status }}
          </el-tag>
          <el-tag size="small" type="info" effect="plain" round>
            {{ debugResult.response_time_ms }} ms
          </el-tag>
        </span>
      </div>
      <el-alert v-if="debugResult?.login_failed" type="error" :closable="false" show-icon style="margin: 8px 0">
        登录失败：{{ debugResult.error }}
      </el-alert>
      <el-alert v-else-if="debugResult?.error" type="warning" :closable="false" show-icon style="margin: 8px 0">
        {{ debugResult.error }}
      </el-alert>

      <el-tabs v-if="debugResult" v-model="debugTab" class="debug-tabs">
        <el-tab-pane label="请求" name="request">
          <div class="debug-section">
            <div class="debug-section-title">请求头</div>
            <pre class="debug-json">{{ formatJson(debugResult.request_headers) }}</pre>
          </div>
          <div class="debug-section">
            <div class="debug-section-title">请求体</div>
            <pre class="debug-json">{{ formatJson(debugResult.request_body) }}</pre>
          </div>
        </el-tab-pane>
        <el-tab-pane label="响应" name="response">
          <div class="debug-section">
            <div class="debug-section-title">响应体</div>
            <pre class="debug-json">{{ formatJson(debugResult.response_body) }}</pre>
          </div>
        </el-tab-pane>
      </el-tabs>
      <el-empty v-else description="选择环境后点「发送请求」" :image-size="60" />
    </el-dialog>

    <!-- 主体：左右布局 -->
    <div class="edit-body">
      <!-- 左侧：基础信息 -->
      <div class="basic-panel">
        <div class="panel-title">基础信息</div>
        <el-form label-width="90px" :model="formData">
          <el-form-item label="接口名称">
            <el-input v-model="formData.name" placeholder="创建订单" />
          </el-form-item>
          <el-form-item label="接口编码">
            <el-input v-model="formData.code" placeholder="order_create" />
          </el-form-item>
          <el-form-item label="接口分组">
            <el-select v-model="formData.group_id" placeholder="选择分组" clearable style="width: 100%">
              <el-option v-for="g in groups" :key="g.id" :label="g.name" :value="g.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="请求方法">
            <el-select v-model="formData.method" style="width: 100%">
              <el-option label="GET" value="GET" />
              <el-option label="POST" value="POST" />
              <el-option label="PUT" value="PUT" />
              <el-option label="DELETE" value="DELETE" />
            </el-select>
          </el-form-item>
          <el-form-item label="请求路径">
            <el-input v-model="formData.path" placeholder="/api/order/orderEntrust/orderAdd" />
          </el-form-item>
          <el-form-item label="描述">
            <el-input v-model="formData.description" type="textarea" :rows="2" placeholder="可选" />
          </el-form-item>
        </el-form>
      </div>

      <!-- 右侧：字段级请求模板 -->
      <div class="fields-panel">
        <div class="panel-title">
          请求字段配置
          <span class="panel-hint">支持点号嵌套路径，默认值支持 ${} 表达式</span>
        </div>
        <FieldTable v-model="formData.fields" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, reactive, watch, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowLeft } from '@element-plus/icons-vue'
import { apiApi, apiGroupApi, type ApiDef, type ApiField, type ApiGroup } from '@/api'
import FieldTable from '@/components/FieldTable.vue'
import { useAppStore } from '@/stores'
import { storeToRefs } from 'pinia'

const route = useRoute()
const router = useRouter()
const store = useAppStore()
const { currentProjectId } = storeToRefs(store)

const projectId = computed(() => currentProjectId.value)
const isEdit = computed(() => !!route.params.id)
const saving = ref(false)
const dirty = ref(false)
const groups = ref<ApiGroup[]>([])

// ===== 调试 =====
const debugVisible = ref(false)
const debugging = ref(false)
const debugEnvId = ref<number | null>(null)
const debugResult = ref<any>(null)
const debugTab = ref('request')

function formatJson(v: any): string {
  try {
    return JSON.stringify(v, null, 2)
  } catch {
    return String(v)
  }
}

function openDebug() {
  if (!isEdit.value) return
  if (!store.environments.length) {
    ElMessage.warning('当前项目暂无环境，请先到环境配置创建')
    return
  }
  debugResult.value = null
  debugTab.value = 'request'
  if (!debugEnvId.value && store.environments.length) {
    debugEnvId.value = store.environments[0].id
  }
  debugVisible.value = true
}

async function onDebug() {
  if (!debugEnvId.value || !formData.id) return
  debugging.value = true
  try {
    debugResult.value = await apiApi.debug(formData.id, debugEnvId.value)
  } catch (e: any) {
    ElMessage.error(e.message || '调试失败')
  } finally {
    debugging.value = false
  }
}

interface ApiFormData {
  id?: number
  name: string
  code: string
  group_id: number | null
  method: string
  path: string
  description: string
  fields: ApiField[]
}

const formData = reactive<ApiFormData>({
  name: '',
  code: '',
  group_id: null,
  method: 'POST',
  path: '',
  description: '',
  fields: [],
})

// 监听变更
watch(formData, () => { dirty.value = true }, { deep: true })

async function loadGroups() {
  if (!projectId.value) return
  groups.value = await apiGroupApi.list(projectId.value)
}

async function loadApi() {
  if (!isEdit.value) return
  const id = Number(route.params.id)
  const api: ApiDef = await apiApi.get(id)
  formData.id = api.id
  formData.name = api.name
  formData.code = api.code
  formData.group_id = api.group_id ?? null
  formData.method = api.method
  formData.path = api.path
  formData.description = api.description || ''
  formData.fields = (api.fields || []).map(f => ({ ...f }))
  // watch(formData) 是异步触发的，会在下一个 tick 把 dirty 设为 true；
  // 这里用 nextTick 等待 watch 触发后再重置，避免误判"有未保存改动"
  await nextTick()
  dirty.value = false
}

function onBack() {
  router.push('/apis')
}

async function onSave() {
  if (!formData.name || !formData.code || !formData.path) {
    ElMessage.warning('名称、编码、路径不能为空')
    return
  }
  saving.value = true
  try {
    const payload: Partial<ApiDef> = {
      project_id: projectId.value!,
      group_id: formData.group_id,
      name: formData.name,
      code: formData.code,
      method: formData.method,
      path: formData.path,
      description: formData.description,
      fields: formData.fields.filter(f => f.key),
    }
    if (isEdit.value) {
      await apiApi.update(formData.id!, payload)
      ElMessage.success('已保存')
    } else {
      await apiApi.create(payload)
      ElMessage.success('已创建')
      router.push('/apis')
    }
    dirty.value = false
  } catch (e: any) {
    ElMessage.error(e.message || '保存失败')
  } finally {
    saving.value = false
  }
}

onMounted(async () => {
  await loadGroups()
  await loadApi()
  window.addEventListener('keydown', onKeydown)
})
onUnmounted(() => {
  window.removeEventListener('keydown', onKeydown)
})

function onKeydown(e: KeyboardEvent) {
  if ((e.ctrlKey || e.metaKey) && e.key === 's') {
    e.preventDefault()
    onSave()
  }
}
</script>

<style scoped>
.api-edit {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--app-bg);
}
.edit-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 20px;
  background: var(--app-card);
  backdrop-filter: saturate(180%) blur(20px);
  border-bottom: 1px solid var(--app-border);
}
.edit-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--app-text);
  flex: 1;
}
.header-right {
  display: flex;
  align-items: center;
  gap: 10px;
}
.dirty-tip {
  color: #ff9500;
  font-size: 13px;
}
.edit-body {
  display: flex;
  gap: 16px;
  flex: 1;
  padding: 16px;
  overflow: auto;
}
.basic-panel {
  width: 360px;
  background: #fff;
  border-radius: 16px;
  padding: 20px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
  height: fit-content;
}
.fields-panel {
  flex: 1;
  background: #fff;
  border-radius: 16px;
  padding: 20px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
  min-width: 0;
}
.panel-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--app-text);
  margin-bottom: 16px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.panel-hint {
  font-size: 12px;
  font-weight: 400;
  color: var(--app-text-muted);
}
.debug-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}
.debug-meta {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.debug-tabs {
  margin-top: 8px;
}
.debug-section {
  margin-bottom: 12px;
}
.debug-section-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--app-text);
  margin-bottom: 6px;
}
.debug-json {
  background: var(--app-bg);
  border-radius: 8px;
  padding: 12px;
  font-size: 12px;
  font-family: 'SF Mono', Menlo, Consolas, monospace;
  color: var(--app-text);
  max-height: 260px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-all;
  margin: 0;
}
</style>

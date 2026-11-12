<template>
  <div class="page">
    <div class="page-head">
      <div class="head-left">
        <span class="page-title">API 密钥</span>
        <el-button type="primary" @click="openCreate">+ 新建密钥</el-button>
      </div>
      <div class="head-right">
        <el-select v-model="filterProjectId" style="width: 200px" placeholder="按项目过滤" clearable @change="load">
          <el-option v-for="p in store.projects" :key="p.id" :label="p.name" :value="p.id" />
        </el-select>
        <el-button @click="load">刷新</el-button>
      </div>
    </div>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="usage-tip"
      title="密钥供外部系统（Jenkins / CI / 脚本）调用平台接口触发执行"
    >
      <template #default>
        认证两种方式任选其一：<code>Authorization: Bearer fin_xxx</code> 或 <code>X-API-Key: fin_xxx</code>；
        密钥身份 = 创建人身份（member 创建的密钥只有 member 权限）；明文仅创建时展示一次，丢失只能删旧建新。
      </template>
    </el-alert>

    <div class="table-wrap">
      <el-card shadow="never" class="card">
        <el-skeleton v-if="loading" :rows="4" animated class="skeleton-wrap" />
        <div v-else-if="loadError" class="app-load-error">
          <el-icon><WarningFilled /></el-icon>
          <span>{{ loadError }}</span>
          <el-button size="small" @click="load">重试</el-button>
        </div>
        <el-table v-else :data="keys" stripe size="small" row-key="id">
          <template #empty>
            <EmptyState description="暂无 API 密钥" :image-size="80">
              <el-button type="primary" @click="openCreate">新建密钥</el-button>
            </EmptyState>
          </template>
          <el-table-column prop="id" label="ID" width="70" />
          <el-table-column prop="name" label="用途名" min-width="160" show-overflow-tooltip />
          <el-table-column label="密钥前缀" width="180">
            <template #default="{ row }">
              <el-tag size="small" type="info" class="mono">{{ row.key_prefix }}…</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="所属项目" min-width="140">
            <template #default="{ row }">{{ projectName(row.project_id) }}</template>
          </el-table-column>
          <el-table-column label="创建人" width="110" align="center">
            <template #default="{ row }">{{ row.created_by_name || '—' }}</template>
          </el-table-column>
          <el-table-column label="最近使用" width="160" align="center">
            <template #default="{ row }">
              <span v-if="row.last_used_at">{{ formatTime(row.last_used_at) }}</span>
              <span v-else class="dim">从未使用</span>
            </template>
          </el-table-column>
          <el-table-column label="创建时间" width="160" align="center">
            <template #default="{ row }">{{ row.created_at ? formatTime(row.created_at) : '—' }}</template>
          </el-table-column>
          <el-table-column label="操作" width="90" align="center" fixed="right">
            <template #default="{ row }">
              <el-popconfirm title="吊销后外部调用立即 401，确定？" confirm-button-text="吊销" @confirm="onRevoke(row)">
                <template #reference>
                  <el-button type="danger" link size="small" :disabled="!canRevoke(row)">吊销</el-button>
                </template>
              </el-popconfirm>
            </template>
          </el-table-column>
        </el-table>
      </el-card>
    </div>

    <!-- 新建密钥：两段式（表单 → 一次性明文展示） -->
    <el-dialog v-model="visible" :title="phase === 'form' ? '新建 API 密钥' : '密钥已创建'" width="560px" :close-on-click-modal="phase !== 'created'">
      <template v-if="phase === 'form'">
        <el-form label-width="80px" @submit.prevent>
          <el-form-item label="用途名" required>
            <el-input v-model="form.name" maxlength="100" placeholder="如 jenkins-nightly（供辨识）" @keyup.enter="onCreate" />
          </el-form-item>
          <el-form-item label="归属项目" required>
            <el-select v-model="form.project_id" style="width: 100%" placeholder="选择项目">
              <el-option v-for="p in store.projects" :key="p.id" :label="p.name" :value="p.id" />
            </el-select>
          </el-form-item>
        </el-form>
      </template>
      <template v-else>
        <el-alert type="warning" :closable="false" show-icon class="once-tip"
                  title="明文仅此一次展示——关闭弹窗后无法再查，请立即复制保存" />
        <div class="key-box">
          <code class="mono">{{ createdKey?.api_key }}</code>
          <el-button type="primary" size="small" @click="copyKey">复制</el-button>
        </div>
        <div class="curl-example">
          <div class="curl-title">curl 触发用例执行示例：</div>
          <pre class="mono">curl -X POST "{{ baseApiUrl }}/testcases/{case_id}/execute" \
  -H "X-API-Key: {{ createdKey?.api_key }}" \
  -H "Content-Type: application/json" \
  -d '{"case_id": 123, "dataset_id": null, "dataset_row_index": null}'</pre>
        </div>
      </template>
      <template #footer>
        <el-button v-if="phase === 'form'" @click="visible = false">取消</el-button>
        <el-button v-if="phase === 'form'" type="primary" :loading="creating" :disabled="!form.name.trim() || !form.project_id" @click="onCreate">创建</el-button>
        <el-button v-else type="primary" @click="visible = false">我已保存，关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { WarningFilled } from '@element-plus/icons-vue'
import { apiKeyApi, type ApiKeyCreated, type ApiKeyItem } from '@/api'
import { useAppStore } from '@/stores'
import { formatTime } from '@/utils/format'
import EmptyState from '@/components/EmptyState.vue'

const store = useAppStore()

const keys = ref<ApiKeyItem[]>([])
const loading = ref(false)
const loadError = ref('')
const filterProjectId = ref<number | null>(null)

const visible = ref(false)
const phase = ref<'form' | 'created'>('form')
const creating = ref(false)
const form = reactive({ name: '', project_id: null as number | null })
const createdKey = ref<ApiKeyCreated | null>(null)

const baseApiUrl = computed(() => `${window.location.origin}/api`)

function projectName(projectId: number): string {
  return store.projects.find((p) => p.id === projectId)?.name || `#${projectId}`
}

/** member 只能吊销自己的密钥；admin 可吊销任意（后端同口径，前端仅禁用按钮） */
function canRevoke(row: ApiKeyItem): boolean {
  return store.user?.role === 'admin' || row.created_by === store.user?.id
}

async function load() {
  loading.value = true
  loadError.value = ''
  try {
    keys.value = await apiKeyApi.list(filterProjectId.value ?? undefined)
  } catch (e: any) {
    loadError.value = e?.response?.data?.detail || e?.message || '加载失败'
  } finally {
    loading.value = false
  }
}

function openCreate() {
  phase.value = 'form'
  form.name = ''
  form.project_id = filterProjectId.value ?? store.currentProjectId ?? store.projects[0]?.id ?? null
  createdKey.value = null
  visible.value = true
}

async function onCreate() {
  if (!form.name.trim() || !form.project_id) return
  creating.value = true
  try {
    createdKey.value = await apiKeyApi.create({ project_id: form.project_id, name: form.name.trim() })
    phase.value = 'created'
    ElMessage.success('密钥已创建')
    await load()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '创建失败')
  } finally {
    creating.value = false
  }
}

async function copyKey() {
  if (!createdKey.value) return
  try {
    await navigator.clipboard.writeText(createdKey.value.api_key)
    ElMessage.success('已复制到剪贴板')
  } catch {
    ElMessage.warning('复制失败，请手动选择复制')
  }
}

async function onRevoke(row: ApiKeyItem) {
  try {
    await apiKeyApi.remove(row.id)
    ElMessage.success(`已吊销「${row.name}」`)
    await load()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '吊销失败')
  }
}

onMounted(async () => {
  if (!store.projects.length) await store.loadProjects()
  await load()
})
</script>

<style scoped>
.usage-tip {
  margin-bottom: 12px;
}
.usage-tip code {
  background: var(--el-fill-color-light);
  padding: 1px 6px;
  border-radius: 3px;
}
.dim {
  color: var(--el-text-color-placeholder);
}
.mono {
  font-family: 'JetBrains Mono', Consolas, monospace;
}
.once-tip {
  margin-bottom: 12px;
}
.key-box {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px;
  background: var(--el-fill-color-light);
  border-radius: 6px;
  word-break: break-all;
}
.key-box code {
  flex: 1;
  font-size: 13px;
}
.curl-example {
  margin-top: 12px;
}
.curl-title {
  font-size: 13px;
  color: var(--el-text-color-secondary);
  margin-bottom: 6px;
}
.curl-example pre {
  margin: 0;
  padding: 10px;
  background: var(--el-fill-color-darker);
  color: var(--el-color-success);
  border-radius: 6px;
  font-size: 12px;
  line-height: 1.6;
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-all;
}
</style>

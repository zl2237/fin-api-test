<template>
  <div class="page">
    <div class="page-head">
      <div class="head-left">
        <span class="page-title">环境配置</span>
        <el-button type="primary" @click="onCreate">+ 新建环境</el-button>
      </div>
      <div class="head-right">
        <el-select
          v-model="filterCreator"
          style="width: 160px"
          placeholder="创建人"
          clearable
          filterable
          @change="load"
        >
          <el-option v-for="u in users" :key="u.id" :label="u.name" :value="u.id" />
        </el-select>
        <el-select
          v-model="filterUpdater"
          style="width: 160px"
          placeholder="更新人"
          clearable
          filterable
          @change="load"
        >
          <el-option v-for="u in users" :key="u.id" :label="u.name" :value="u.id" />
        </el-select>
      </div>
    </div>
    <div class="table-wrap">
      <el-card shadow="never" class="card">
        <!-- 页面级加载失败：内联错误块 + 重试 -->
        <div v-if="loadError" class="app-load-error">
          <el-icon><WarningFilled /></el-icon>
          <span>{{ loadError }}</span>
          <el-button size="small" @click="load">重试</el-button>
        </div>
        <el-skeleton v-else-if="loading" :rows="5" animated class="skeleton-wrap" />
        <el-table v-else ref="tableRef" :data="pagedList" stripe size="small" row-key="id" @sort-change="onSortChange">
          <template #empty>
            <EmptyState description="暂无环境" :image-size="80">
              <el-button type="primary" @click="onCreate">+ 新建环境</el-button>
            </EmptyState>
          </template>
          <el-table-column width="36" align="center">
            <template #default>
              <el-tooltip content="拖拽排序" placement="top" popper-class="app-tip">
                <el-icon class="drag-handle"><Rank /></el-icon>
              </el-tooltip>
            </template>
          </el-table-column>
          <el-table-column prop="id" label="ID" width="70" align="center" sortable="custom" />
          <el-table-column prop="name" label="环境" width="120" show-overflow-tooltip sortable="custom" />
          <el-table-column prop="base_url" label="Base URL" min-width="200" show-overflow-tooltip />
          <el-table-column label="数据库" width="100" align="center">
            <template #default="{ row }">
              <el-tag size="small" :type="dbTag(row.db_config).type" effect="plain">
                {{ dbTag(row.db_config).text }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="登录" width="100" align="center">
            <template #default="{ row }">
              <el-tag size="small" :type="loginTag(row.login_config).type" effect="plain">
                {{ loginTag(row.login_config).text }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="通知" width="100" align="center">
            <template #default="{ row }">
              <el-tag size="small" :type="row.notify_config?.wecom_webhook ? 'success' : 'info'" effect="plain">
                {{ row.notify_config?.wecom_webhook ? '已配置' : '无' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="默认" width="80" align="center">
            <template #default="{ row }">
              <el-tag v-if="row.is_default" size="small" type="primary">默认</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="创建人" width="100" align="center">
            <template #default="{ row }">{{ row.created_by_name || '未知' }}</template>
          </el-table-column>
          <el-table-column label="更新人" width="100" align="center">
            <template #default="{ row }">{{ row.updated_by_name || '未知' }}</template>
          </el-table-column>
          <el-table-column label="操作" width="220" fixed="right">
            <template #default="{ row }">
              <el-button link type="primary" size="small" @click="onEdit(row)">编辑</el-button>
              <el-button link type="primary" size="small" @click="onCopy(row)">复制</el-button>
              <el-button link type="danger" size="small" @click="onRemove(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
        <div class="pagination-wrap">
          <el-pagination
            v-model:current-page="page"
            v-model:page-size="pageSize"
            :total="list.length"
            :page-sizes="[10, 20, 50, 100]"
            layout="total, sizes, prev, pager, next"
            background
            small
          />
        </div>
      </el-card>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import Sortable from 'sortablejs'
import { Rank, WarningFilled } from '@element-plus/icons-vue'
import { envApi, userApi, type Environment, type SimpleUser } from '@/api'
import { useAppStore } from '@/stores'
import { useClientSort } from '@/composables/useClientSort'
import EmptyState from '@/components/EmptyState.vue'

const store = useAppStore()
const router = useRouter()
const list = ref<Environment[]>([])
const users = ref<SimpleUser[]>([])
const filterCreator = ref<number | null>(null)
const filterUpdater = ref<number | null>(null)
const loading = ref(false)
const loadError = ref('')
const page = ref(1)
const pageSize = ref(10)
// 表头排序（sortable="custom"）：先排全量再分页切片；取消排序回到手动拖拽序
const { sortProp, onSortChange, sorted: sortedList } = useClientSort(list, {
  id: e => e.id,
  name: e => e.name,
}, () => { page.value = 1 })
const pagedList = computed(() => {
  const start = (page.value - 1) * pageSize.value
  return sortedList.value.slice(start, start + pageSize.value)
})

// ===== 拖拽排序（SortableJS 绑定 el-table tbody）=====
const tableRef = ref<any>(null)
let sortableInst: any = null

function bindSortable() {
  const tbody = tableRef.value?.$el?.querySelector?.('.el-table__body-wrapper tbody')
  if (!tbody) return
  if (sortableInst) { sortableInst.destroy(); sortableInst = null }
  // 过滤/排序激活时禁拖：reorder 按显示顺序重写全局 sort_order，会静默打乱未过滤数据的排序
  if (filterCreator.value != null || filterUpdater.value != null || sortProp.value != null) return
  sortableInst = Sortable.create(tbody, {
    handle: '.drag-handle',
    animation: 200,
    ghostClass: 'sortable-ghost',
    onEnd: async (evt: any) => {
      if (evt.oldIndex === evt.newIndex) return
      const start = (page.value - 1) * pageSize.value
      const moved = list.value.splice(start + evt.oldIndex, 1)[0]
      list.value.splice(start + evt.newIndex, 0, moved)
      const items = list.value.map((e, i) => ({ id: e.id, sort_order: i }))
      try {
        await envApi.reorder(items)
        ElMessage.success('已保存')
        list.value.forEach((e, i) => { e.sort_order = i })
      } catch (e: any) {
        ElMessage.error(e.message || '排序保存失败')
        await load()
      }
    },
  })
}

watch([pagedList, loading], () => {
  if (!loading.value && pagedList.value.length > 0) {
    requestAnimationFrame(bindSortable)
  }
})

onBeforeUnmount(() => {
  if (sortableInst) { sortableInst.destroy(); sortableInst = null }
})

// 配置完整度三态：无 / 未完成 / 已配置
function dbTag(cfg: any): { type: 'success' | 'warning' | 'info'; text: string } {
  if (!cfg) return { type: 'info', text: '无' }
  const fields = [cfg.host, cfg.user, cfg.password, cfg.database]
  const filled = fields.filter((v) => v && String(v).trim()).length
  if (filled === 0) return { type: 'info', text: '无' }
  if (filled === fields.length) return { type: 'success', text: '已配置' }
  return { type: 'warning', text: '未完成' }
}

function loginTag(cfg: any): { type: 'success' | 'warning' | 'info'; text: string } {
  if (!cfg) return { type: 'info', text: '无' }
  // login_body 的每个 value 也必须非空才算填完
  const bodyEntries = cfg.login_body ? Object.entries(cfg.login_body) : []
  const hasBody = bodyEntries.length > 0
  const bodyAllFilled = hasBody && bodyEntries.every(([, v]) => v !== null && v !== undefined && String(v).trim() !== '')
  // auth_header_value_template 可留空（等价于 ${token}），不参与判断
  const fields = [cfg.login_path, hasBody, cfg.token_jsonpath, cfg.auth_header_name]
  const filled = fields.filter((v) => v).length
  if (filled === 0) return { type: 'info', text: '无' }
  // login_body 有键但部分 value 为空 → 未完成
  if (hasBody && !bodyAllFilled) return { type: 'warning', text: '未完成' }
  if (filled === fields.length) return { type: 'success', text: '已配置' }
  return { type: 'warning', text: '未完成' }
}

async function load() {
  if (!store.currentProjectId) return
  loading.value = true
  loadError.value = ''
  try {
    list.value = await envApi.list(store.currentProjectId, filterCreator.value ?? undefined, filterUpdater.value ?? undefined)
    page.value = 1
  } catch (e: any) {
    // 页面级失败：内联错误块 + 重试
    loadError.value = e?.message || '加载失败'
  } finally {
    loading.value = false
  }
}

async function loadUsers() {
  try {
    users.value = await userApi.simple()
  } catch {
    users.value = []
  }
}

function onCreate() {
  router.push('/envs/edit')
}

function onEdit(row: Environment) {
  router.push(`/envs/edit/${row.id}`)
}

async function onCopy(row: Environment) {
  try {
    await envApi.copy(row.id)
    ElMessage.success('已复制')
    await load()
    store.loadEnvironments()
  } catch (e: any) {
    ElMessage.error(e.message || '复制失败')
  }
}

async function onRemove(row: Environment) {
  try {
    await ElMessageBox.confirm(
      `确认删除环境「${row.name}」？引用该环境的定时任务将失效，此操作不可恢复`,
      '删除环境',
      { type: 'warning', confirmButtonText: '删除' },
    )
    await envApi.remove(row.id)
    ElMessage.success('已删除')
    load()
    store.loadEnvironments()
  } catch (e: any) {
    if (e !== 'cancel') ElMessage.error(e.message || '删除失败')
  }
}

watch(() => store.currentProjectId, load)
onMounted(() => {
  load()
  loadUsers()
})
</script>

<style scoped>
.page {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--app-bg);
}
.table-wrap {
  flex: 1;
  overflow: auto;
  padding: 16px 20px;
}
.card {
  background: var(--app-card);
  border-radius: var(--app-radius-lg);
}
.pagination-wrap {
  display: flex;
  justify-content: flex-end;
  margin-top: 12px;
}
.drag-handle {
  cursor: grab;
  color: var(--app-text-faint);
}
.drag-handle:active {
  cursor: grabbing;
}
</style>

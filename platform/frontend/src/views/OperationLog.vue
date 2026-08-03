<template>
  <div class="log-manage">
    <div class="toolbar">
      <div class="title">操作日志</div>
      <div class="filters">
        <el-select v-model="filterUserId" placeholder="操作人" clearable filterable style="width: 140px" @change="load">
          <el-option v-for="u in users" :key="u.id" :label="u.name" :value="u.id" />
        </el-select>
        <el-select v-model="filterAction" placeholder="操作类型" clearable style="width: 120px" @change="load">
          <el-option label="新增" value="create" />
          <el-option label="修改" value="update" />
          <el-option label="删除" value="delete" />
          <el-option label="复制" value="copy" />
        </el-select>
        <el-select v-model="filterTarget" placeholder="目标类型" clearable style="width: 140px" @change="load">
          <el-option label="项目" value="project" />
          <el-option label="环境" value="environment" />
          <el-option label="接口" value="api" />
          <el-option label="用例" value="testcase" />
          <el-option label="用户" value="user" />
          <el-option label="接口分组" value="api_group" />
          <el-option label="用例分组" value="case_group" />
        </el-select>
        <el-button @click="resetFilter">重置</el-button>
        <el-button @click="load">刷新</el-button>
      </div>
    </div>

    <el-card shadow="never" class="table-card">
      <el-skeleton v-if="loading" :rows="6" animated class="skeleton-wrap" />
      <el-table v-else :data="pagedList" border>
        <el-table-column prop="id" label="ID" width="70" align="center" />
        <el-table-column label="操作人" width="120">
          <template #default="{ row }">{{ row.username || '未知' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="90" align="center">
          <template #default="{ row }">
            <el-tag :type="actionTagType(row.action)" effect="light" round size="small">
              {{ actionText(row.action) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="目标类型" width="110">
          <template #default="{ row }">{{ targetTypeText(row.target_type) }}</template>
        </el-table-column>
        <el-table-column prop="target_id" label="目标ID" width="80" align="center" />
        <el-table-column prop="target_name" label="目标名称" min-width="160" show-overflow-tooltip />
        <el-table-column prop="detail" label="详情" min-width="140" show-overflow-tooltip />
        <el-table-column prop="created_at" label="操作时间" min-width="170" />
      </el-table>
      <div class="pagination-wrap">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :total="logs.length"
          :page-sizes="[10, 20, 50, 100]"
          layout="total, sizes, prev, pager, next"
          background
          small
        />
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { logApi, userApi, type OperationLog, type SimpleUser } from '@/api'

const logs = ref<OperationLog[]>([])
const loading = ref(false)
const users = ref<SimpleUser[]>([])
const filterAction = ref('')
const filterTarget = ref('')
const filterUserId = ref<number | null>(null)
const page = ref(1)
const pageSize = ref(20)
const pagedList = computed(() => {
  const start = (page.value - 1) * pageSize.value
  return logs.value.slice(start, start + pageSize.value)
})

async function load() {
  loading.value = true
  try {
    const params: { action?: string; target_type?: string; user_id?: number; limit?: number } = { limit: 500 }
    if (filterAction.value) params.action = filterAction.value
    if (filterTarget.value) params.target_type = filterTarget.value
    if (filterUserId.value) params.user_id = filterUserId.value
    logs.value = await logApi.list(params)
    page.value = 1
  } catch (e: any) {
    ElMessage.error(e.message || '加载失败')
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

function resetFilter() {
  filterAction.value = ''
  filterTarget.value = ''
  filterUserId.value = null
  load()
}

function actionText(a: string) {
  return a === 'create' ? '新增' : a === 'update' ? '修改' : a === 'delete' ? '删除' : a === 'copy' ? '复制' : a
}

function actionTagType(a: string) {
  return a === 'create' ? 'success' : a === 'update' ? 'warning' : a === 'delete' ? 'danger' : 'info'
}

function targetTypeText(t: string) {
  const map: Record<string, string> = {
    project: '项目',
    environment: '环境',
    api: '接口',
    testcase: '用例',
    user: '用户',
    api_group: '接口分组',
    case_group: '用例分组',
  }
  return map[t] || t
}

onMounted(() => {
  load()
  loadUsers()
})
</script>

<style scoped>
.log-manage {
  display: flex;
  flex-direction: column;
  gap: 12px;
  height: 100%;
}
.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 8px;
}
.title {
  font-size: 17px;
  font-weight: 600;
  color: var(--app-text);
}
.filters {
  display: flex;
  gap: 8px;
  align-items: center;
}
.table-card {
  background: var(--app-card);
  backdrop-filter: saturate(180%) blur(20px);
  border-radius: 16px;
}
.pagination-wrap {
  display: flex;
  justify-content: flex-end;
  margin-top: 12px;
}
</style>

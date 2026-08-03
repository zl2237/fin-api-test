<template>
  <div class="page">
    <div class="page-head">
      <el-button type="primary" @click="onCreate">+ 新建环境</el-button>
      <el-select
        v-model="filterCreator"
        style="width: 160px; margin-left: 12px"
        placeholder="创建人"
        clearable
        filterable
        @change="load"
      >
        <el-option v-for="u in users" :key="u.id" :label="u.name" :value="u.id" />
      </el-select>
      <el-select
        v-model="filterUpdater"
        style="width: 160px; margin-left: 12px"
        placeholder="更新人"
        clearable
        filterable
        @change="load"
      >
        <el-option v-for="u in users" :key="u.id" :label="u.name" :value="u.id" />
      </el-select>
    </div>
    <div class="table-wrap">
      <el-card shadow="never" class="card">
        <el-skeleton v-if="loading" :rows="5" animated class="skeleton-wrap" />
        <el-table v-else :data="pagedList" stripe empty-text="暂无环境，点击左上角「新建环境」开始配置">
          <el-table-column prop="name" label="环境" width="100" />
          <el-table-column prop="base_url" label="Base URL" min-width="200" />
          <el-table-column label="数据库" width="100" align="center">
            <template #default="{ row }">
              <el-tag size="small" :type="row.db_config?.host ? 'success' : 'info'" effect="plain">
                {{ row.db_config?.host ? '已配置' : '无' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="登录" width="100" align="center">
            <template #default="{ row }">
              <el-tag size="small" :type="row.login_config?.login_body ? 'success' : 'info'" effect="plain">
                {{ row.login_config?.login_body ? '已配置' : '无' }}
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
              <el-button link type="primary" @click="onEdit(row)">编辑</el-button>
              <el-button link type="primary" @click="onCopy(row)">复制</el-button>
              <el-button link type="danger" @click="onRemove(row)">删除</el-button>
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
import { ref, computed, watch, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { envApi, userApi, type Environment, type SimpleUser } from '@/api'
import { useAppStore } from '@/stores'

const store = useAppStore()
const router = useRouter()
const list = ref<Environment[]>([])
const users = ref<SimpleUser[]>([])
const filterCreator = ref<number | null>(null)
const filterUpdater = ref<number | null>(null)
const loading = ref(false)
const page = ref(1)
const pageSize = ref(10)
const pagedList = computed(() => {
  const start = (page.value - 1) * pageSize.value
  return list.value.slice(start, start + pageSize.value)
})

async function load() {
  if (!store.currentProjectId) return
  loading.value = true
  try {
    list.value = await envApi.list(store.currentProjectId, filterCreator.value ?? undefined, filterUpdater.value ?? undefined)
    page.value = 1
  } catch (e: any) {
    ElMessage.error(e.message)
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
    await ElMessageBox.confirm(`确定删除环境「${row.name}」？`, '提示', { type: 'warning' })
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
.page-head {
  padding: 12px 20px;
  background: var(--app-card);
  backdrop-filter: saturate(180%) blur(20px);
  border-bottom: 1px solid var(--app-border);
}
.table-wrap {
  flex: 1;
  overflow: auto;
  padding: 16px 20px;
}
.card {
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

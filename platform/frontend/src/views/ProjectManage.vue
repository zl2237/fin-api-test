<template>
  <div class="page">
    <div class="page-head">
      <el-button type="primary" @click="openCreate">+ 新建项目</el-button>
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
        <el-table v-else :data="pagedList" stripe>
          <el-table-column prop="id" label="ID" width="70" />
          <el-table-column prop="name" label="项目名称" min-width="160" show-overflow-tooltip />
          <el-table-column prop="description" label="描述" min-width="240" show-overflow-tooltip />
          <el-table-column label="当前" width="80" align="center">
            <template #default="{ row }">
              <el-tag v-if="row.id === store.currentProjectId" size="small" type="primary">当前</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="创建人" width="100" align="center">
            <template #default="{ row }">{{ row.created_by_name || '未知' }}</template>
          </el-table-column>
          <el-table-column label="更新人" width="100" align="center">
            <template #default="{ row }">{{ row.updated_by_name || '未知' }}</template>
          </el-table-column>
          <el-table-column prop="created_at" label="创建时间" min-width="170" show-overflow-tooltip />
          <el-table-column label="操作" width="260" fixed="right">
            <template #default="{ row }">
              <el-button link type="primary" size="small" @click="onSwitch(row)">切换为当前</el-button>
              <el-button link type="primary" size="small" @click="onEdit(row)">编辑</el-button>
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

      <!-- 空状态引导 -->
      <EmptyState v-if="!loading && !list.length" description="暂无项目">
        <el-button type="primary" @click="openCreate">创建第一个项目</el-button>
      </EmptyState>
    </div>

    <!-- 新建/编辑弹窗 -->
    <el-dialog v-model="dialogVisible" :title="isEdit ? '编辑项目' : '新建项目'" width="480px" align-center>
      <el-form :model="form" label-width="80px">
        <el-form-item label="项目名称">
          <el-input v-model="form.name" placeholder="如：fin-order 测试" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="form.description" type="textarea" :rows="3" placeholder="可选" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="onSave">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { projectApi, userApi, type Project, type SimpleUser } from '@/api'
import { useAppStore } from '@/stores'
import EmptyState from '@/components/EmptyState.vue'

const store = useAppStore()
const list = ref<Project[]>([])
const loading = ref(false)
const users = ref<SimpleUser[]>([])
const filterCreator = ref<number | null>(null)
const filterUpdater = ref<number | null>(null)
const page = ref(1)
const pageSize = ref(10)
const pagedList = computed(() => {
  const start = (page.value - 1) * pageSize.value
  return list.value.slice(start, start + pageSize.value)
})
const dialogVisible = ref(false)
const isEdit = ref(false)
const saving = ref(false)
const form = ref<{ id?: number; name: string; description: string }>({ name: '', description: '' })

async function load() {
  loading.value = true
  try {
    list.value = await projectApi.list({ created_by: filterCreator.value ?? undefined, updated_by: filterUpdater.value ?? undefined })
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

function openCreate() {
  isEdit.value = false
  form.value = { name: '', description: '' }
  dialogVisible.value = true
}

function onEdit(row: Project) {
  isEdit.value = true
  form.value = { id: row.id, name: row.name, description: row.description || '' }
  dialogVisible.value = true
}

async function onSave() {
  if (!form.value.name.trim()) return ElMessage.warning('请输入项目名称')
  saving.value = true
  try {
    if (isEdit.value && form.value.id) {
      await projectApi.update(form.value.id, { name: form.value.name, description: form.value.description })
      ElMessage.success('已保存')
    } else {
      const created = await projectApi.create({ name: form.value.name, description: form.value.description })
      ElMessage.success('已创建')
      // 新建后自动切换为当前项目，避免新用户卡死
      await store.loadProjects()
      store.setProject(created.id)
    }
    dialogVisible.value = false
    await load()
  } catch (e: any) {
    ElMessage.error(e.message || '保存失败')
  } finally {
    saving.value = false
  }
}

async function onSwitch(row: Project) {
  store.setProject(row.id)
  ElMessage.success(`已切换到项目「${row.name}」`)
}

async function onRemove(row: Project) {
  try {
    await ElMessageBox.confirm(`确定删除项目「${row.name}」？关联的接口/用例/环境将一并删除，此操作不可恢复。`, '提示', { type: 'warning' })
  } catch {
    return
  }
  try {
    await projectApi.remove(row.id)
    ElMessage.success('已删除')
    // 若删除的是当前项目，自动切到第一个
    if (store.currentProjectId === row.id) {
      await store.loadProjects()
      const first = store.projects[0]
      if (first) store.setProject(first.id)
      else {
        store.currentProjectId = null
        store.currentEnvId = null
        store.environments = []
      }
    }
    await load()
  } catch (e: any) {
    ElMessage.error(e.message || '删除失败')
  }
}

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
.pagination-wrap {
  display: flex;
  justify-content: flex-end;
  margin-top: 12px;
}
.card {
  background: var(--app-card);
  backdrop-filter: saturate(180%) blur(20px);
  border-radius: var(--app-radius-lg);
}
</style>

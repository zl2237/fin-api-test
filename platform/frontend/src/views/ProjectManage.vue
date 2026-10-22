<template>
  <div class="page">
    <div class="page-head">
      <div class="head-left">
        <span class="page-title">项目管理</span>
        <el-button type="primary" @click="openCreate">+ 新建项目</el-button>
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
      <!-- 空态：EmptyState 承担全部引导（表格/分页不再渲染，避免同屏双空态）；加载失败时优先展示错误块 -->
      <el-card v-if="!loading && !loadError && !list.length" shadow="never" class="card empty-card">
        <EmptyState description="暂无项目">
          <el-button type="primary" @click="openCreate">创建第一个项目</el-button>
        </EmptyState>
      </el-card>
      <el-card v-else shadow="never" class="card">
        <!-- 页面级加载失败：内联错误块 + 重试 -->
        <div v-if="loadError" class="app-load-error">
          <el-icon><WarningFilled /></el-icon>
          <span>{{ loadError }}</span>
          <el-button size="small" @click="load">重试</el-button>
        </div>
        <el-skeleton v-else-if="loading" :rows="5" animated class="skeleton-wrap" />
        <el-table v-else ref="tableRef" :data="pagedList" stripe size="small" row-key="id" @sort-change="onSortChange">
          <el-table-column width="36" align="center">
            <template #default>
              <el-tooltip content="拖拽排序" placement="top" popper-class="app-tip">
                <el-icon class="drag-handle"><Rank /></el-icon>
              </el-tooltip>
            </template>
          </el-table-column>
          <el-table-column prop="id" label="ID" width="70" sortable="custom">
            <template #default="{ row }"><span class="app-data">{{ row.id }}</span></template>
          </el-table-column>
          <el-table-column prop="name" label="项目名称" min-width="160" show-overflow-tooltip sortable="custom">
            <template #default="{ row }">
              <!-- 首字徽章：项目名首字 + hash 取色（同名恒色），纯表格里唯一的品牌识别元素 -->
              <span class="proj-cell">
                <span class="proj-avatar" :style="avatarStyle(row.name)">{{ avatarChar(row.name) }}</span>
                <span class="proj-name">{{ row.name }}</span>
              </span>
            </template>
          </el-table-column>
          <el-table-column prop="description" label="描述" min-width="240" show-overflow-tooltip />
          <el-table-column label="当前" width="80" align="center">
            <template #default="{ row }">
              <el-tag v-if="row.id === store.currentProjectId" size="small" type="primary">当前</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="创建人" width="100" align="center">
            <template #default="{ row }">{{ row.created_by_name || '—' }}</template>
          </el-table-column>
          <el-table-column label="更新人" width="100" align="center">
            <template #default="{ row }">{{ row.updated_by_name || '—' }}</template>
          </el-table-column>
          <el-table-column prop="created_at" label="创建时间" width="120" sortable="custom">
            <template #default="{ row }">
              <el-tooltip :content="formatTime(row.created_at)" placement="top" popper-class="app-tip">
                <span class="app-data">{{ formatRelativeTime(row.created_at) }}</span>
              </el-tooltip>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="260" fixed="right">
            <template #default="{ row }">
              <el-button link type="primary" size="small" @click="onSwitch(row)">切换为当前</el-button>
              <el-button link type="primary" size="small" @click="onEdit(row)">编辑</el-button>
              <el-button link type="danger" size="small" @click="onRemove(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
        <div v-if="list.length > pageSize" class="pagination-wrap">
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

    <!-- 新建/编辑弹窗 -->
    <el-dialog v-model="dialogVisible" :title="isEdit ? '编辑项目' : '新建项目'" width="420px" align-center :close-on-click-modal="false">
      <el-form ref="formRef" :model="form" :rules="formRules" label-width="80px">
        <el-form-item label="项目名称" prop="name">
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
import { ref, computed, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import { ElMessage, ElMessageBox, type FormInstance, type FormRules } from 'element-plus'
import Sortable from 'sortablejs'
import { Rank, WarningFilled } from '@element-plus/icons-vue'
import { projectApi, userApi, type Project, type SimpleUser } from '@/api'
import { useAppStore } from '@/stores'
import { formatTime, formatRelativeTime } from '@/utils/format'

// ===== 首字徽章：固定品牌色板 + 名字 hash 取色（同名恒色，切换/刷新不跳变） =====
const AVATAR_PALETTE = ['#0f7285', '#3d6fb5', '#b57f2a', '#7a5fb5', '#b5475f', '#3f8a5f']

function avatarChar(name: string): string {
  const ch = (name || '?').trim().charAt(0)
  return ch || '?'
}

function avatarStyle(name: string): { background: string } {
  const s = name || '?'
  let hash = 0
  for (let i = 0; i < s.length; i++) hash = (hash * 31 + s.charCodeAt(i)) >>> 0
  return { background: AVATAR_PALETTE[hash % AVATAR_PALETTE.length] }
}
import { useClientSort } from '@/composables/useClientSort'
import EmptyState from '@/components/EmptyState.vue'

const store = useAppStore()
const list = ref<Project[]>([])
const loading = ref(false)
const loadError = ref('')
const users = ref<SimpleUser[]>([])
const filterCreator = ref<number | null>(null)
const filterUpdater = ref<number | null>(null)
const page = ref(1)
const pageSize = ref(10)
// 表头排序（sortable="custom"）：先排全量再分页切片；取消排序回到手动拖拽序
const { sortProp, onSortChange, sorted: sortedList } = useClientSort(list, {
  id: p => p.id,
  name: p => p.name,
  created_at: p => p.created_at ?? '',
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
      const items = list.value.map((p, i) => ({ id: p.id, sort_order: i }))
      try {
        await projectApi.reorder(items)
        ElMessage.success('已保存')
        list.value.forEach((p, i) => { p.sort_order = i })
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
const dialogVisible = ref(false)
// 字段级校验（el-form rules）：错误定位到输入框，替代提交时 if 判空 + toast
const formRef = ref<FormInstance>()
const formRules: FormRules = {
  name: [{ required: true, whitespace: true, message: '请输入项目名称', trigger: 'blur' }],
}
const isEdit = ref(false)
const saving = ref(false)
const form = ref<{ id?: number; name: string; description: string }>({ name: '', description: '' })

async function load() {
  loading.value = true
  loadError.value = ''
  try {
    list.value = await projectApi.list({ created_by: filterCreator.value ?? undefined, updated_by: filterUpdater.value ?? undefined })
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

function openCreate() {
  isEdit.value = false
  form.value = { name: '', description: '' }
  dialogVisible.value = true
  nextTick(() => formRef.value?.clearValidate())
}

function onEdit(row: Project) {
  isEdit.value = true
  form.value = { id: row.id, name: row.name, description: row.description || '' }
  dialogVisible.value = true
  nextTick(() => formRef.value?.clearValidate())
}

async function onSave() {
  if (!formRef.value) return
  await formRef.value.validate(async (valid) => {
    if (!valid) return
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
  })
}

async function onSwitch(row: Project) {
  store.setProject(row.id)
  ElMessage.success(`已切换到项目「${row.name}」`)
}

async function onRemove(row: Project) {
  try {
    await ElMessageBox.confirm(
      `确认删除项目「${row.name}」？关联的接口/用例/环境将一并删除，此操作不可恢复`,
      '删除项目',
      { type: 'warning', confirmButtonText: '删除' },
    )
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
/* 首字徽章：圆形底 + 白字加粗，近直角系统里与状态徽章同为「圆」档（形状锁三档规则） */
.proj-cell {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}
.proj-avatar {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  border-radius: 50%;
  color: #fff;
  font-size: 12px;
  font-weight: 600;
}
.proj-name {
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
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
.pagination-wrap {
  display: flex;
  justify-content: flex-end;
  margin-top: 12px;
}
.card {
  background: var(--app-card);
  border-radius: var(--app-radius-lg);
}
.drag-handle {
  cursor: grab;
  color: var(--app-text-faint);
}
.drag-handle:active {
  cursor: grabbing;
}
</style>

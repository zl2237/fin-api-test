<template>
  <div class="user-manage">
    <div class="page-head">
      <div class="head-left">
        <span class="page-title">用户管理</span>
        <el-button type="primary" @click="openCreate">+ 新建用户</el-button>
      </div>
      <div class="head-right">
        <!-- 部门筛选：选项从已有用户的部门动态提取（本地过滤，即时生效） -->
        <el-select v-model="filterDepartment" placeholder="部门" clearable filterable style="width: 140px" @change="filterLocal">
          <el-option v-for="d in departments" :key="d" :label="d" :value="d" />
        </el-select>
        <el-select v-model="filterCreator" placeholder="创建人" clearable filterable style="width: 140px" @change="filterLocal">
          <el-option v-for="u in allUsers" :key="u.id" :label="u.name || u.username" :value="u.id" />
        </el-select>
        <el-select v-model="filterUpdater" placeholder="更新人" clearable filterable style="width: 140px" @change="filterLocal">
          <el-option v-for="u in allUsers" :key="u.id" :label="u.name || u.username" :value="u.id" />
        </el-select>
      </div>
    </div>

    <el-card shadow="never" class="table-card">
      <!-- 页面级加载失败：内联错误块 + 重试 -->
      <div v-if="loadError" class="app-load-error">
        <el-icon><WarningFilled /></el-icon>
        <span>{{ loadError }}</span>
        <el-button size="small" @click="load">重试</el-button>
      </div>
      <el-skeleton v-else-if="loading" :rows="6" animated class="skeleton-wrap" />
      <el-table v-else :data="pagedList" stripe size="small" row-key="id" @sort-change="onSortChange">
        <template #empty>
          <EmptyState description="暂无用户" :image-size="80">
            <el-button type="primary" @click="openCreate">+ 新建用户</el-button>
          </EmptyState>
        </template>
        <el-table-column prop="id" label="ID" width="60" align="center" sortable="custom" />
        <el-table-column prop="username" label="用户名" min-width="120" show-overflow-tooltip sortable="custom" />
        <el-table-column prop="name" label="显示名" min-width="100" show-overflow-tooltip sortable="custom" />
        <el-table-column label="部门" min-width="100" show-overflow-tooltip>
          <template #default="{ row }">{{ row.department || '—' }}</template>
        </el-table-column>
        <el-table-column label="手机号" min-width="120" show-overflow-tooltip>
          <template #default="{ row }">{{ row.phone || '—' }}</template>
        </el-table-column>
        <el-table-column label="邮箱" min-width="160" show-overflow-tooltip>
          <template #default="{ row }">{{ row.email || '—' }}</template>
        </el-table-column>
        <el-table-column label="角色" width="90" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.role === 'admin'" type="warning" effect="plain" round size="small">管理员</el-tag>
            <el-tag v-else type="info" effect="plain" round size="small">普通成员</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" width="110" sortable="custom">
          <template #default="{ row }">
            <el-tooltip :content="formatTime(row.created_at)" placement="top" popper-class="app-tip">
              <span>{{ formatRelativeTime(row.created_at) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="创建人" width="90" align="center">
          <template #default="{ row }">{{ row.created_by_name || '—' }}</template>
        </el-table-column>
        <el-table-column label="更新人" width="90" align="center">
          <template #default="{ row }">{{ row.updated_by_name || '—' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="240">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="openEditDrawer(row)">编辑</el-button>
            <el-button link type="warning" size="small" @click="openPasswordDialog(row)">重置密码</el-button>
            <el-button link type="danger" size="small" @click="onDelete(row)" :disabled="row.id === store.user?.id">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="pagination-wrap">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :total="users.length"
          :page-sizes="[10, 20, 50, 100]"
          layout="total, sizes, prev, pager, next"
          background
          small
        />
      </div>
    </el-card>

    <!-- 新增用户抽屉：5 字段超弹窗边界，与编辑抽屉同构（规范 §2：同一实体增改同容器） -->
    <el-drawer v-model="createVisible" title="新增用户" size="440px" :close-on-click-modal="false">
      <el-form ref="createFormRef" :model="createForm" :rules="createRules" label-width="80px">
        <el-form-item label="用户名" prop="username">
          <el-input v-model="createForm.username" placeholder="登录用用户名" />
        </el-form-item>
        <el-form-item label="显示名" prop="name">
          <el-input v-model="createForm.name" placeholder="留空则用用户名" />
        </el-form-item>
        <el-form-item label="密码" prop="password">
          <el-input v-model="createForm.password" type="password" show-password placeholder="至少8位，含字母和数字" />
        </el-form-item>
        <el-form-item label="部门" prop="department">
          <el-select v-model="createForm.department" placeholder="选填，可直接输入" filterable allow-create clearable style="width: 100%">
            <el-option v-for="d in departments" :key="d" :label="d" :value="d" />
          </el-select>
        </el-form-item>
        <el-form-item label="角色" prop="role">
          <el-radio-group v-model="createForm.role">
            <el-radio value="member">普通成员</el-radio>
            <el-radio value="admin">管理员</el-radio>
          </el-radio-group>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitLoading" @click="onCreate">确定</el-button>
      </template>
    </el-drawer>

    <!-- 编辑用户抽屉：6 字段超弹窗边界，升格为抽屉（规范 §2） -->
    <el-drawer v-model="roleVisible" title="编辑用户" size="440px" :close-on-click-modal="false">
      <el-form ref="roleFormRef" :model="roleForm" :rules="roleRules" label-width="80px">
        <el-form-item label="用户名" prop="username">
          <el-input v-model="roleForm.username" placeholder="登录用用户名" maxlength="50" />
        </el-form-item>
        <el-form-item label="显示名" prop="name">
          <el-input v-model="roleForm.name" placeholder="留空则用用户名" maxlength="50" />
        </el-form-item>
        <el-form-item label="手机号" prop="phone">
          <el-input v-model="roleForm.phone" placeholder="选填，全局唯一" maxlength="11" />
        </el-form-item>
        <el-form-item label="邮箱" prop="email">
          <el-input v-model="roleForm.email" placeholder="选填，全局唯一" maxlength="100" />
        </el-form-item>
        <el-form-item label="部门" prop="department">
          <el-select v-model="roleForm.department" placeholder="选填，可直接输入" filterable allow-create clearable style="width: 100%">
            <el-option v-for="d in departments" :key="d" :label="d" :value="d" />
          </el-select>
        </el-form-item>
        <el-form-item label="角色" prop="role">
          <el-radio-group v-model="roleForm.role">
            <el-radio value="member">普通成员</el-radio>
            <el-radio value="admin">管理员</el-radio>
          </el-radio-group>
        </el-form-item>
      </el-form>
      <div class="edit-tip">修改用户名后，该用户需使用新用户名登录</div>
      <template #footer>
        <el-button @click="roleVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitLoading" @click="onRoleUpdate">确定</el-button>
      </template>
    </el-drawer>

    <!-- 重置密码对话框 -->
    <el-dialog v-model="passwordVisible" title="重置密码" width="420px" align-center :close-on-click-modal="false">
      <el-form ref="passwordFormRef" :model="passwordForm" :rules="passwordRules" label-width="80px">
        <el-form-item label="用户名">{{ passwordTarget?.username }}</el-form-item>
        <el-form-item label="新密码" prop="password">
          <el-input v-model="passwordForm.password" type="password" show-password placeholder="至少8位，含字母和数字" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="passwordVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitLoading" @click="onPasswordReset">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox, type FormInstance, type FormRules } from 'element-plus'
import { WarningFilled } from '@element-plus/icons-vue'
import { userApi, type User } from '@/api'
import { useAppStore } from '@/stores'
import { useTabStore } from '@/stores/tabs'
import { formatTime, formatRelativeTime } from '@/utils/format'
import { useClientSort } from '@/composables/useClientSort'
import EmptyState from '@/components/EmptyState.vue'

const router = useRouter()
const store = useAppStore()
const tabStore = useTabStore()
const allUsers = ref<User[]>([])
const loading = ref(false)
const loadError = ref('')
const submitLoading = ref(false)
const filterCreator = ref<number | null>(null)
const filterUpdater = ref<number | null>(null)
const filterDepartment = ref<string | null>(null)
// 部门选项：从已有用户动态提取（自由文本字段，不建独立字典）
const departments = computed(() =>
  Array.from(new Set(allUsers.value.map(u => (u.department || '').trim()).filter(Boolean))).sort((a, b) => a.localeCompare(b, 'zh-CN'))
)
const page = ref(1)
const pageSize = ref(10)
const users = computed(() => {
  let r = allUsers.value
  if (filterCreator.value) r = r.filter(u => u.created_by === filterCreator.value)
  if (filterUpdater.value) r = r.filter(u => u.updated_by === filterUpdater.value)
  if (filterDepartment.value) r = r.filter(u => (u.department || '').trim() === filterDepartment.value)
  return r
})
// 表头排序（sortable="custom"）：先排全量再分页切片；取消排序回到接口默认序
const { onSortChange, sorted: sortedUsers } = useClientSort(users, {
  id: u => u.id,
  username: u => u.username,
  name: u => u.name ?? '',
  created_at: u => u.created_at ?? '',
}, () => { page.value = 1 })
const pagedList = computed(() => {
  const start = (page.value - 1) * pageSize.value
  return sortedUsers.value.slice(start, start + pageSize.value)
})

function filterLocal() {
  page.value = 1
}

// 新增
const createVisible = ref(false)
const createFormRef = ref<FormInstance>()
const createForm = reactive({ username: '', name: '', password: '', role: 'member', department: '' })
const createRules: FormRules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 8, message: '密码至少 8 位', trigger: 'blur' },
    {
      validator: (_rule, value: string, callback) => {
        if (!value) return callback()
        if (!/[A-Za-z]/.test(value) || !/[0-9]/.test(value)) return callback(new Error('密码必须同时包含字母和数字'))
        callback()
      },
      trigger: 'blur',
    },
  ],
}

// 编辑用户（用户名/显示名/手机号/邮箱/角色）
const roleVisible = ref(false)
const roleTarget = ref<User | null>(null)
const roleFormRef = ref<FormInstance>()
const roleForm = reactive({ username: '', name: '', phone: '', email: '', department: '', role: 'member' })
const roleRules: FormRules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { min: 2, max: 50, message: '用户名 2-50 个字符', trigger: 'blur' },
  ],
  name: [{ max: 50, message: '显示名最多 50 个字符', trigger: 'blur' }],
  phone: [
    {
      validator: (_rule, value: string, callback) => {
        if (!value) return callback()
        if (!/^1[3-9]\d{9}$/.test(value)) return callback(new Error('手机号格式不正确'))
        callback()
      },
      trigger: 'blur',
    },
  ],
  email: [
    {
      validator: (_rule, value: string, callback) => {
        if (!value) return callback()
        if (!/^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$/.test(value)) return callback(new Error('邮箱格式不正确'))
        callback()
      },
      trigger: 'blur',
    },
  ],
}

// 重置密码
const passwordVisible = ref(false)
const passwordTarget = ref<User | null>(null)
const passwordFormRef = ref<FormInstance>()
const passwordForm = reactive({ password: '' })
const passwordRules: FormRules = {
  password: [
    { required: true, message: '请输入新密码', trigger: 'blur' },
    { min: 8, message: '密码至少 8 位', trigger: 'blur' },
    {
      validator: (_rule, value: string, callback) => {
        if (!value) return callback()
        if (!/[A-Za-z]/.test(value) || !/[0-9]/.test(value)) return callback(new Error('密码必须同时包含字母和数字'))
        callback()
      },
      trigger: 'blur',
    },
  ],
}

async function load() {
  loading.value = true
  loadError.value = ''
  try {
    allUsers.value = await userApi.list()
    page.value = 1
  } catch (e: any) {
    // 页面级失败：内联错误块 + 重试
    loadError.value = e?.message || '加载失败'
  } finally {
    loading.value = false
  }
}

function openCreate() {
  createForm.username = ''
  createForm.name = ''
  createForm.password = ''
  createForm.role = 'member'
  createForm.department = ''
  createVisible.value = true
}

async function onCreate() {
  if (!createFormRef.value) return
  await createFormRef.value.validate(async (valid) => {
    if (!valid) return
    submitLoading.value = true
    try {
      await userApi.create({
        username: createForm.username.trim(),
        password: createForm.password,
        name: createForm.name.trim() || undefined,
        role: createForm.role,
        department: (createForm.department || '').trim() || undefined,
      })
      ElMessage.success('已创建')
      createVisible.value = false
      await load()
    } catch (e: any) {
      ElMessage.error(e.message || '创建失败')
    } finally {
      submitLoading.value = false
    }
  })
}

function openEditDrawer(row: User) {
  roleTarget.value = row
  roleForm.username = row.username
  roleForm.name = row.name || ''
  roleForm.phone = row.phone || ''
  roleForm.email = row.email || ''
  roleForm.department = row.department || ''
  roleForm.role = row.role
  roleFormRef.value?.clearValidate()
  roleVisible.value = true
}

async function onRoleUpdate() {
  if (!roleTarget.value || !roleFormRef.value) return
  await roleFormRef.value.validate(async (valid) => {
    if (!valid) return
    submitLoading.value = true
    try {
      await userApi.update(roleTarget.value!.id, {
        username: roleForm.username.trim(),
        name: roleForm.name.trim() || null,
        phone: roleForm.phone.trim() || null,
        email: roleForm.email.trim() || null,
        department: (roleForm.department || '').trim() || null,
        role: roleForm.role,
      })
      ElMessage.success('已保存')
      roleVisible.value = false
      // 把自己降级为普通成员：本页已无权访问，同步本地角色后离开，避免停留页面触发 403
      if (store.user?.id === roleTarget.value!.id && roleForm.role !== 'admin') {
        store.user.role = roleForm.role
        const next = tabStore.removeTab('/users')
        router.replace(next || '/apis')
        return
      }
      await load()
    } catch (e: any) {
      ElMessage.error(e.message || '保存失败')
    } finally {
      submitLoading.value = false
    }
  })
}

function openPasswordDialog(row: User) {
  passwordTarget.value = row
  passwordForm.password = ''
  passwordVisible.value = true
}

async function onPasswordReset() {
  if (!passwordTarget.value || !passwordFormRef.value) return
  await passwordFormRef.value.validate(async (valid) => {
    if (!valid) return
    submitLoading.value = true
    try {
      await userApi.resetPassword(passwordTarget.value!.id, passwordForm.password)
      ElMessage.success('已重置')
      passwordVisible.value = false
    } catch (e: any) {
      ElMessage.error(e.message || '重置失败')
    } finally {
      submitLoading.value = false
    }
  })
}

async function onDelete(row: User) {
  try {
    await ElMessageBox.confirm(
      `确认删除用户「${row.username}」？此操作不可恢复`,
      '删除用户',
      { type: 'warning', confirmButtonText: '删除' },
    )
    await userApi.remove(row.id)
    ElMessage.success('已删除')
    await load()
  } catch (e: any) {
    if (e !== 'cancel') ElMessage.error(e.message || '删除失败')
  }
}

onMounted(load)
</script>

<style scoped>
.user-manage {
  display: flex;
  flex-direction: column;
  gap: 12px;
  height: 100%;
}
.table-card {
  background: var(--app-card);
  border-radius: var(--app-radius-lg);
}
.pagination-wrap {
  display: flex;
  justify-content: flex-end;
  margin-top: 12px;
}
/* 编辑抽屉底部提示：用户名变更影响登录 */
.edit-tip {
  margin-top: 4px;
  padding: 8px 12px;
  font-size: 12px;
  color: var(--app-text-muted);
  background: var(--app-hover);
  border-radius: var(--app-radius-sm);
}
</style>

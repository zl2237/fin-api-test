<template>
  <div class="user-manage">
    <div class="toolbar">
      <div class="title">用户管理</div>
      <div class="filters">
        <el-select v-model="filterCreator" placeholder="创建人" clearable filterable style="width: 140px" @change="filterLocal">
          <el-option v-for="u in allUsers" :key="u.id" :label="u.name || u.username" :value="u.id" />
        </el-select>
        <el-select v-model="filterUpdater" placeholder="更新人" clearable filterable style="width: 140px" @change="filterLocal">
          <el-option v-for="u in allUsers" :key="u.id" :label="u.name || u.username" :value="u.id" />
        </el-select>
        <el-button type="primary" @click="openCreate">新增用户</el-button>
      </div>
    </div>

    <el-card shadow="never" class="table-card">
      <el-skeleton v-if="loading" :rows="6" animated class="skeleton-wrap" />
      <el-table v-else :data="pagedList" border empty-text="暂无用户，点击「新建用户」开始添加">
        <el-table-column prop="id" label="ID" width="60" align="center" />
        <el-table-column prop="username" label="用户名" min-width="120" show-overflow-tooltip />
        <el-table-column prop="name" label="显示名" min-width="120" show-overflow-tooltip />
        <el-table-column label="角色" width="120" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.role === 'admin'" type="warning" effect="plain" round size="small">管理员</el-tag>
            <el-tag v-else type="info" effect="plain" round size="small">普通成员</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" min-width="170" show-overflow-tooltip />
        <el-table-column label="创建人" width="100" align="center">
          <template #default="{ row }">{{ row.created_by_name || '—' }}</template>
        </el-table-column>
        <el-table-column label="更新人" width="100" align="center">
          <template #default="{ row }">{{ row.updated_by_name || '—' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="280" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="openRoleDialog(row)">改角色</el-button>
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

    <!-- 新增用户对话框 -->
    <el-dialog v-model="createVisible" title="新增用户" width="420px" align-center>
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
    </el-dialog>

    <!-- 改角色对话框 -->
    <el-dialog v-model="roleVisible" title="修改角色" width="360px" align-center>
      <el-form label-width="80px">
        <el-form-item label="用户名">{{ roleTarget?.username }}</el-form-item>
        <el-form-item label="角色">
          <el-radio-group v-model="roleForm.role">
            <el-radio value="member">普通成员</el-radio>
            <el-radio value="admin">管理员</el-radio>
          </el-radio-group>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="roleVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitLoading" @click="onRoleUpdate">确定</el-button>
      </template>
    </el-dialog>

    <!-- 重置密码对话框 -->
    <el-dialog v-model="passwordVisible" title="重置密码" width="360px" align-center>
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
import { userApi, type User } from '@/api'
import { useAppStore } from '@/stores'
import { useTabStore } from '@/stores/tabs'

const router = useRouter()
const store = useAppStore()
const tabStore = useTabStore()
const allUsers = ref<User[]>([])
const loading = ref(false)
const submitLoading = ref(false)
const filterCreator = ref<number | null>(null)
const filterUpdater = ref<number | null>(null)
const page = ref(1)
const pageSize = ref(10)
const users = computed(() => {
  let r = allUsers.value
  if (filterCreator.value) r = r.filter(u => u.created_by === filterCreator.value)
  if (filterUpdater.value) r = r.filter(u => u.updated_by === filterUpdater.value)
  return r
})
const pagedList = computed(() => {
  const start = (page.value - 1) * pageSize.value
  return users.value.slice(start, start + pageSize.value)
})

function filterLocal() {
  page.value = 1
}

// 新增
const createVisible = ref(false)
const createFormRef = ref<FormInstance>()
const createForm = reactive({ username: '', name: '', password: '', role: 'member' })
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

// 改角色
const roleVisible = ref(false)
const roleTarget = ref<User | null>(null)
const roleForm = reactive({ role: 'member' })

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
  try {
    allUsers.value = await userApi.list()
    page.value = 1
  } catch (e: any) {
    ElMessage.error(e.message || '加载失败')
  } finally {
    loading.value = false
  }
}

function openCreate() {
  createForm.username = ''
  createForm.name = ''
  createForm.password = ''
  createForm.role = 'member'
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

function openRoleDialog(row: User) {
  roleTarget.value = row
  roleForm.role = row.role
  roleVisible.value = true
}

async function onRoleUpdate() {
  if (!roleTarget.value) return
  submitLoading.value = true
  try {
    await userApi.updateRole(roleTarget.value.id, roleForm.role)
    ElMessage.success('已修改角色')
    roleVisible.value = false
    // 把自己降级为普通成员：本页已无权访问，同步本地角色后离开，避免停留页面触发 403
    if (store.user?.id === roleTarget.value.id && roleForm.role !== 'admin') {
      store.user.role = roleForm.role
      const next = tabStore.removeTab('/users')
      router.replace(next || '/apis')
      return
    }
    await load()
  } catch (e: any) {
    ElMessage.error(e.message || '修改失败')
  } finally {
    submitLoading.value = false
  }
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
      ElMessage.success('密码已重置')
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
    await ElMessageBox.confirm(`确认删除用户「${row.username}」？此操作不可恢复`, '提示', { type: 'warning' })
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
.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.filters {
  display: flex;
  gap: 8px;
  align-items: center;
}
.title {
  font-size: 17px;
  font-weight: 600;
  color: var(--app-text);
}
.table-card {
  background: var(--app-card);
  backdrop-filter: saturate(180%) blur(20px);
  border-radius: var(--app-radius-lg);
}
.pagination-wrap {
  display: flex;
  justify-content: flex-end;
  margin-top: 12px;
}
</style>

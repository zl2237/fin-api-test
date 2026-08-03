<template>
  <div class="login-page">
    <div class="login-card">
      <div class="brand">
        <span class="brand-dot"></span>
        <span class="brand-text">fin-api-test</span>
      </div>
      <div class="brand-sub">接口自动化测试平台</div>

      <el-tabs v-model="activeTab" class="login-tabs" stretch>
        <el-tab-pane label="登录" name="login" />
        <el-tab-pane label="注册" name="register" />
      </el-tabs>

      <el-form ref="formRef" :model="form" :rules="rules" label-position="top" @submit.prevent="onSubmit">
        <el-form-item label="用户名" prop="username">
          <el-input v-model="form.username" placeholder="请输入用户名" :prefix-icon="User" />
        </el-form-item>
        <el-form-item label="密码" prop="password">
          <el-input v-model="form.password" type="password" show-password placeholder="请输入密码" :prefix-icon="Lock" />
        </el-form-item>
        <el-form-item v-if="activeTab === 'register'" label="显示名（可选）" prop="name">
          <el-input v-model="form.name" placeholder="留空则用用户名" />
        </el-form-item>
        <el-button type="primary" class="submit-btn" :loading="loading" @click="onSubmit">
          {{ activeTab === 'login' ? '登 录' : '注 册' }}
        </el-button>
      </el-form>

      <div v-if="activeTab === 'register'" class="hint">
        密码要求：至少 8 位，必须同时包含字母和数字<br>
        首个注册用户自动成为管理员，其余为普通成员
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import { User, Lock } from '@element-plus/icons-vue'
import { useAppStore } from '@/stores'
import { authApi, setToken } from '@/api'

const router = useRouter()
const route = useRoute()
const store = useAppStore()

const activeTab = ref<'login' | 'register'>('login')
const loading = ref(false)
const formRef = ref<FormInstance>()

const form = reactive({
  username: '',
  password: '',
  name: '',
})

const rules: FormRules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    // 注册时强制密码强度：长度≥8 + 含字母和数字；登录时不校验强度
    {
      validator: (_rule, value: string, callback) => {
        if (activeTab.value === 'register') {
          if (!value || value.length < 8) return callback(new Error('密码至少 8 位'))
          if (!/[A-Za-z]/.test(value) || !/[0-9]/.test(value)) return callback(new Error('密码必须同时包含字母和数字'))
        }
        callback()
      },
      trigger: 'blur',
    },
  ],
}

// 切换 tab 时清空表单校验
watch(activeTab, () => {
  formRef.value?.clearValidate()
})

async function onSubmit() {
  if (!formRef.value) return
  await formRef.value.validate(async (valid) => {
    if (!valid) return
    loading.value = true
    try {
      const u = form.username.trim()
      const p = form.password
      if (activeTab.value === 'login') {
        await store.login(u, p)
        ElMessage.success('登录成功')
      } else {
        const res = await authApi.register(u, p, form.name.trim() || undefined)
        setToken(res.token)
        await store.loadUser()
        ElMessage.success('注册成功，已自动登录')
      }
      const redirect = (route.query.redirect as string) || '/'
      router.replace(redirect)
    } catch (e: any) {
      ElMessage.error(e.message || '操作失败')
    } finally {
      loading.value = false
    }
  })
}
</script>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, var(--app-bg) 0%, var(--app-bg) 100%);
}
.login-card {
  width: 380px;
  background: var(--app-card-solid);
  backdrop-filter: saturate(180%) blur(20px);
  border: 1px solid var(--app-border);
  border-radius: 18px;
  padding: 32px 32px 24px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.06);
}
.brand {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  font-weight: 600;
  font-size: 22px;
  margin-bottom: 4px;
}
.brand-dot {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: linear-gradient(135deg, var(--app-primary), #42a1ff);
}
.brand-sub {
  text-align: center;
  font-size: 13px;
  color: var(--app-text-muted);
  margin-bottom: 20px;
}
.login-tabs {
  margin-bottom: 8px;
}
.submit-btn {
  width: 100%;
  margin-top: 4px;
  border-radius: 10px;
}
.hint {
  margin-top: 14px;
  font-size: 12px;
  color: var(--app-text-muted);
  text-align: center;
  line-height: 1.6;
}
.hint code {
  background: var(--app-tag-bg);
  padding: 1px 6px;
  border-radius: 4px;
  font-size: 11px;
}
</style>

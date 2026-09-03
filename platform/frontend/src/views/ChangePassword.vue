<template>
  <!-- 改密是工具页：居中单卡，不带品牌区/装饰/署名（署名仅保留登录页一处） -->
  <div class="cp-page">
    <main class="form-panel">
      <div class="form-card">
        <div class="card-header">
          <h2 class="card-title">修改密码</h2>
          <p class="card-sub">
            {{ store.user?.must_change_password ? '首次登录请修改初始密码后继续使用' : '修改你的账户密码' }}
          </p>
        </div>

        <div v-if="store.user?.must_change_password" class="warning-banner">
          <el-icon><WarningFilled /></el-icon>
          <span>首次登录请修改初始密码后继续使用</span>
        </div>

        <el-form ref="formRef" :model="form" :rules="rules" label-position="top" @submit.prevent="onSubmit">
          <el-form-item label="新密码" prop="new_password">
            <el-input v-model="form.new_password" type="password" show-password placeholder="请输入新密码" :prefix-icon="Lock" size="large" @keyup.enter="onSubmit" />
          </el-form-item>
          <el-form-item label="确认新密码" prop="confirm_password">
            <el-input v-model="form.confirm_password" type="password" show-password placeholder="请再次输入新密码" :prefix-icon="Lock" size="large" @keyup.enter="onSubmit" />
          </el-form-item>
          <el-button type="primary" native-type="submit" class="submit-btn" :loading="loading" size="large">
            确认修改
          </el-button>
        </el-form>

        <div v-if="!store.user?.must_change_password" class="back-hint">
          <el-button text @click="router.back()">← 返回</el-button>
        </div>
        <div class="hint">
          密码要求：至少 8 位，必须同时包含字母和数字，不能与当前密码相同
        </div>
      </div>
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import { Lock, WarningFilled } from '@element-plus/icons-vue'
import { useAppStore } from '@/stores'
import { authApi } from '@/api'

const router = useRouter()
const store = useAppStore()

const loading = ref(false)
const formRef = ref<FormInstance>()

const form = reactive({
  new_password: '',
  confirm_password: '',
})

const rules: FormRules = {
  new_password: [
    { required: true, message: '请输入新密码', trigger: 'blur' },
    { min: 8, message: '密码至少 8 位', trigger: 'blur' },
    {
      validator: (_rule, value: string, callback) => {
        if (!value) return callback()
        if (!/[A-Za-z]/.test(value) || !/[0-9]/.test(value)) {
          return callback(new Error('密码必须同时包含字母和数字'))
        }
        callback()
      },
      trigger: 'blur',
    },
  ],
  confirm_password: [
    { required: true, message: '请再次输入新密码', trigger: 'blur' },
    {
      validator: (_rule, value: string, callback) => {
        if (!value) return callback()
        if (value !== form.new_password) {
          return callback(new Error('两次输入的密码不一致'))
        }
        callback()
      },
      trigger: 'blur',
    },
  ],
}

async function onSubmit() {
  if (!formRef.value) return
  await formRef.value.validate(async (valid) => {
    if (!valid) return
    loading.value = true
    try {
      await authApi.changePassword(form.new_password)
      await store.loadUser()
      ElMessage.success('密码修改成功')
      router.replace('/')
    } catch (e: any) {
      ElMessage.error(e.message || '密码修改失败')
    } finally {
      loading.value = false
    }
  })
}
</script>

<style scoped>
/* 工具页：整页居中单卡，无品牌区无装饰 */
.cp-page {
  min-height: 100vh;
  display: flex;
  background: var(--app-bg);
  overflow: hidden;
}

.form-panel {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px;
}
.form-card {
  width: 100%;
  max-width: 360px;
  padding: 32px 28px;
  background: var(--app-card);
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius);
  box-shadow: var(--app-shadow-lg);
}
.card-header {
  margin-bottom: 24px;
}
.card-title {
  font-size: 26px;
  font-weight: 700;
  color: var(--app-text);
  margin: 0 0 8px;
}
.card-sub {
  font-size: 14px;
  color: var(--app-text-muted);
  margin: 0;
}
.warning-banner {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 20px;
  padding: 10px 14px;
  background: var(--app-warn-bg);
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius-sm);
  font-size: 13px;
  color: var(--app-warn-text);
}
.submit-btn {
  width: 100%;
  margin-top: 4px;
  border-radius: var(--app-radius-sm);
  font-weight: 600;
  letter-spacing: 1px;
}
.back-hint {
  text-align: center;
  margin-top: 8px;
}
.hint {
  margin-top: 16px;
  font-size: 12px;
  color: var(--app-text-muted);
  text-align: center;
  line-height: 1.6;
}

@media (max-width: 600px) {
  .form-panel {
    padding: 20px;
  }
}
</style>

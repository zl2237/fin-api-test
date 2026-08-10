<template>
  <div class="cp-page" @mousemove="onMouseMove">
    <!-- 左侧品牌展示区（与登录页保持一致）-->
    <aside class="brand-panel">
      <div class="deco-layer" :style="parallaxStyle">
        <svg class="deco-svg" viewBox="0 0 600 700" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
          <defs>
            <linearGradient id="cpDecoGrad" x1="0" y1="0" x2="1" y2="1">
              <stop offset="0%" stop-color="#ffffff" stop-opacity="0.9" />
              <stop offset="100%" stop-color="#ffffff" stop-opacity="0.5" />
            </linearGradient>
          </defs>
          <!-- 锁形主题装饰 -->
          <path d="M250 280 v-30 a50 50 0 0 1 100 0 v30" stroke="rgba(255,255,255,0.3)" stroke-width="2.5" fill="none" stroke-linecap="round" />
          <rect x="220" y="280" width="160" height="140" rx="18" fill="rgba(255,255,255,0.12)" stroke="rgba(255,255,255,0.35)" stroke-width="2.5" />
          <circle cx="300" cy="340" r="14" fill="url(#cpDecoGrad)" class="deco-node deco-node-1" />
          <path d="M300 340 v22" stroke="url(#cpDecoGrad)" stroke-width="4" stroke-linecap="round" />
          <!-- 浮动光点 -->
          <circle cx="140" cy="200" r="6" fill="rgba(255,255,255,0.5)" class="deco-node deco-node-2" />
          <circle cx="480" cy="180" r="8" fill="rgba(255,255,255,0.4)" class="deco-node deco-node-3" />
          <circle cx="120" cy="500" r="5" fill="rgba(255,255,255,0.5)" class="deco-node deco-node-4" />
          <circle cx="500" cy="520" r="7" fill="rgba(255,255,255,0.4)" class="deco-node deco-node-5" />
          <circle cx="80" cy="350" r="4" fill="rgba(255,255,255,0.6)" class="deco-node deco-node-6" />
        </svg>
      </div>

      <div class="brand-content">
        <div class="brand-logo-row">
          <svg viewBox="0 0 32 32" width="40" height="40" fill="none" xmlns="http://www.w3.org/2000/svg">
            <defs>
              <linearGradient id="cpBrandGrad" x1="0" y1="0" x2="1" y2="1">
                <stop offset="0%" stop-color="#ffffff" />
                <stop offset="100%" stop-color="#ffffff" stop-opacity="0.7" />
              </linearGradient>
            </defs>
            <rect width="32" height="32" rx="8" fill="rgba(255,255,255,0.15)" />
            <circle cx="16" cy="9" r="2.6" fill="url(#cpBrandGrad)" />
            <circle cx="9" cy="23" r="2.6" fill="url(#cpBrandGrad)" />
            <circle cx="23" cy="23" r="2.6" fill="url(#cpBrandGrad)" />
            <path d="M16 11.6 L9 20.4 M16 11.6 L23 20.4" stroke="#fff" stroke-width="1.8" stroke-linecap="round" />
          </svg>
          <span class="brand-name">fin-api-test</span>
        </div>
        <h1 class="brand-title">保护你的账户安全</h1>
        <p class="brand-slogan">定期修改密码是保障账户安全的第一道防线</p>

        <!-- 安全提示卡片 -->
        <div class="tip-list">
          <div class="tip-item">
            <div class="tip-icon">
              <svg viewBox="0 0 24 24" width="20" height="20" fill="none"><path d="M5 12h14 M12 5v14" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>
            </div>
            <div class="tip-text">
              <div class="tip-name">密码强度要求</div>
              <div class="tip-desc">至少 8 位，必须同时包含字母和数字</div>
            </div>
          </div>
          <div class="tip-item">
            <div class="tip-icon">
              <svg viewBox="0 0 24 24" width="20" height="20" fill="none"><path d="M12 2 L4 6v6c0 5 3.5 8 8 10 4.5-2 8-5 8-10V6z M9 12l2 2 4-4" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>
            </div>
            <div class="tip-text">
              <div class="tip-name">不可与当前密码相同</div>
              <div class="tip-desc">避免重复使用近期密码</div>
            </div>
          </div>
          <div class="tip-item">
            <div class="tip-icon">
              <svg viewBox="0 0 24 24" width="20" height="20" fill="none"><circle cx="12" cy="12" r="3" stroke="currentColor" stroke-width="1.8"/><path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7-10-7-10-7z" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>
            </div>
            <div class="tip-text">
              <div class="tip-name">修改后需重新登录</div>
              <div class="tip-desc">新密码立即生效，保障账户安全</div>
            </div>
          </div>
        </div>
      </div>

      <div class="brand-footer">Developed by zhangle</div>
    </aside>

    <!-- 右侧表单区 -->
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
import { ref, reactive, computed } from 'vue'
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

// ===== 鼠标视差（与登录页一致）=====
const mouseX = ref(0)
const mouseY = ref(0)
const parallaxStyle = computed(() => ({
  transform: `translate(${mouseX.value * 12}px, ${mouseY.value * 12}px)`,
}))

function onMouseMove(e: MouseEvent) {
  mouseX.value = (e.clientX / window.innerWidth - 0.5) * 2
  mouseY.value = (e.clientY / window.innerHeight - 0.5) * 2
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
.cp-page {
  min-height: 100vh;
  display: flex;
  background: var(--app-bg);
  overflow: hidden;
}

/* ===== 左侧品牌展示区（与登录页保持一致）===== */
.brand-panel {
  position: relative;
  flex: 1;
  min-width: 0;
  background: linear-gradient(135deg, #1a2b4a 0%, #2b7fd6 60%, #409eff 100%);
  display: flex;
  flex-direction: column;
  justify-content: center;
  padding: 60px 56px;
  overflow: hidden;
}
.brand-panel::before {
  content: '';
  position: absolute;
  top: -20%;
  right: -10%;
  width: 500px;
  height: 500px;
  background: radial-gradient(circle, rgba(255, 255, 255, 0.12) 0%, transparent 70%);
  pointer-events: none;
}
.brand-panel::after {
  content: '';
  position: absolute;
  bottom: -15%;
  left: -10%;
  width: 400px;
  height: 400px;
  background: radial-gradient(circle, rgba(103, 194, 58, 0.1) 0%, transparent 70%);
  pointer-events: none;
}

.deco-layer {
  position: absolute;
  inset: 0;
  transition: transform 0.3s ease-out;
  pointer-events: none;
}
.deco-svg {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.deco-node {
  transform-origin: center;
  animation: deco-float 6s ease-in-out infinite;
}
.deco-node-1 { animation-delay: 0s; }
.deco-node-2 { animation-delay: 0.7s; }
.deco-node-3 { animation-delay: 1.4s; }
.deco-node-4 { animation-delay: 2.1s; }
.deco-node-5 { animation-delay: 2.8s; }
.deco-node-6 { animation-delay: 1s; }
@keyframes deco-float {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-12px); }
}

.brand-content {
  position: relative;
  z-index: 2;
  color: #fff;
  max-width: 420px;
}
.brand-logo-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 32px;
}
.brand-name {
  font-size: 24px;
  font-weight: 600;
  letter-spacing: 0.5px;
}
.brand-title {
  font-size: 36px;
  font-weight: 700;
  line-height: 1.3;
  margin: 0 0 12px;
  letter-spacing: -0.5px;
}
.brand-slogan {
  font-size: 15px;
  opacity: 0.85;
  margin: 0 0 48px;
  line-height: 1.6;
}

.tip-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.tip-item {
  display: flex;
  align-items: flex-start;
  gap: 14px;
  padding: 16px 18px;
  background: rgba(255, 255, 255, 0.1);
  border: 1px solid rgba(255, 255, 255, 0.15);
  border-radius: 12px;
  backdrop-filter: blur(8px);
  transition: transform 0.25s ease, background 0.25s ease;
}
.tip-item:hover {
  transform: translateX(6px);
  background: rgba(255, 255, 255, 0.16);
}
.tip-icon {
  flex-shrink: 0;
  width: 36px;
  height: 36px;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.15);
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
}
.tip-name {
  font-size: 15px;
  font-weight: 600;
  margin-bottom: 4px;
}
.tip-desc {
  font-size: 13px;
  opacity: 0.8;
  line-height: 1.4;
}

.brand-footer {
  position: absolute;
  bottom: 28px;
  left: 56px;
  z-index: 2;
  font-size: 12px;
  color: rgba(255, 255, 255, 0.6);
  letter-spacing: 0.5px;
}

/* ===== 右侧表单区 ===== */
.form-panel {
  width: 480px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px;
}
.form-card {
  width: 100%;
  max-width: 360px;
  animation: card-enter 0.5s cubic-bezier(0.25, 0.8, 0.25, 1);
}
@keyframes card-enter {
  from {
    opacity: 0;
    transform: translateY(16px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
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
  border-radius: 10px;
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

@media (max-width: 900px) {
  .brand-panel {
    display: none;
  }
  .form-panel {
    width: 100%;
  }
}

@media (prefers-reduced-motion: reduce) {
  .deco-node,
  .form-card {
    animation: none;
  }
  .deco-layer {
    transition: none;
  }
}
</style>

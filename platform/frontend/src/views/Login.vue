<template>
  <div class="login-page" @mousemove="onMouseMove">
    <!-- 左侧品牌展示区 -->
    <aside class="brand-panel">
      <!-- 浮动 DAG 节点装饰（鼠标视差跟随）-->
      <div class="deco-layer" :style="parallaxStyle">
        <svg class="deco-svg" viewBox="0 0 600 700" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
          <defs>
            <linearGradient id="decoNodeGrad" x1="0" y1="0" x2="1" y2="1">
              <stop offset="0%" stop-color="#ffffff" stop-opacity="0.9" />
              <stop offset="100%" stop-color="#ffffff" stop-opacity="0.5" />
            </linearGradient>
          </defs>
          <!-- 连线 -->
          <path d="M120 180 L300 320 M300 320 L500 220 M300 320 L200 520 M300 320 L460 500" stroke="rgba(255,255,255,0.25)" stroke-width="2" stroke-linecap="round" stroke-dasharray="6 8" />
          <!-- 节点：不同大小 + 不同动画延迟 -->
          <circle cx="120" cy="180" r="14" fill="url(#decoNodeGrad)" class="deco-node deco-node-1" />
          <circle cx="300" cy="320" r="20" fill="url(#decoNodeGrad)" class="deco-node deco-node-2" />
          <circle cx="500" cy="220" r="12" fill="url(#decoNodeGrad)" class="deco-node deco-node-3" />
          <circle cx="200" cy="520" r="10" fill="url(#decoNodeGrad)" class="deco-node deco-node-4" />
          <circle cx="460" cy="500" r="16" fill="url(#decoNodeGrad)" class="deco-node deco-node-5" />
          <!-- 小光点 -->
          <circle cx="80" cy="400" r="4" fill="rgba(255,255,255,0.6)" class="deco-node deco-node-6" />
          <circle cx="540" cy="380" r="5" fill="rgba(255,255,255,0.5)" class="deco-node deco-node-7" />
        </svg>
      </div>

      <!-- 品牌内容 -->
      <div class="brand-content">
        <div class="brand-logo-row">
          <svg viewBox="0 0 32 32" width="40" height="40" fill="none" xmlns="http://www.w3.org/2000/svg">
            <defs>
              <linearGradient id="loginBrandGrad" x1="0" y1="0" x2="1" y2="1">
                <stop offset="0%" stop-color="#ffffff" />
                <stop offset="100%" stop-color="#ffffff" stop-opacity="0.7" />
              </linearGradient>
            </defs>
            <rect width="32" height="32" rx="8" fill="rgba(255,255,255,0.15)" />
            <circle cx="16" cy="9" r="2.6" fill="url(#loginBrandGrad)" />
            <circle cx="9" cy="23" r="2.6" fill="url(#loginBrandGrad)" />
            <circle cx="23" cy="23" r="2.6" fill="url(#loginBrandGrad)" />
            <path d="M16 11.6 L9 20.4 M16 11.6 L23 20.4" stroke="#fff" stroke-width="1.8" stroke-linecap="round" />
          </svg>
          <span class="brand-name">fin-api-test</span>
        </div>
        <h1 class="brand-title">接口自动化测试平台</h1>
        <p class="brand-slogan">DAG 可视化编排 · 17 种断言 · 一键执行报告</p>

        <!-- 核心能力卡片 -->
        <div class="feature-list">
          <div class="feature-item">
            <div class="feature-icon">
              <svg viewBox="0 0 24 24" width="22" height="22" fill="none"><path d="M5 4h14v16H5z M9 8h6 M9 12h6 M9 16h4" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>
            </div>
            <div class="feature-text">
              <div class="feature-name">用例管理</div>
              <div class="feature-desc">分组编排 · 拖拽排序 · 批量执行</div>
            </div>
          </div>
          <div class="feature-item">
            <div class="feature-icon">
              <svg viewBox="0 0 24 24" width="22" height="22" fill="none"><circle cx="12" cy="12" r="9" stroke="currentColor" stroke-width="1.8"/><path d="M8 12l3 3 5-6" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>
            </div>
            <div class="feature-text">
              <div class="feature-name">智能断言</div>
              <div class="feature-desc">JSONPath · 状态码 · DB 交叉校验</div>
            </div>
          </div>
          <div class="feature-item">
            <div class="feature-icon">
              <svg viewBox="0 0 24 24" width="22" height="22" fill="none"><path d="M4 17V7l8-4 8 4v10l-8 4z M4 7l8 4 8-4 M12 11v10" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>
            </div>
            <div class="feature-text">
              <div class="feature-name">报告导出</div>
              <div class="feature-desc">耗时趋势 · HTML 导出 · 重新执行</div>
            </div>
          </div>
        </div>
      </div>

      <!-- 底部版权 -->
      <div class="brand-footer">Developed by zhangle</div>
    </aside>

    <!-- 右侧表单区 -->
    <main class="form-panel">
      <div class="form-card">
        <div class="card-header">
          <h2 class="card-title">{{ activeTab === 'login' ? '欢迎回来' : '创建账号' }}</h2>
          <p class="card-sub">{{ activeTab === 'login' ? '登录以继续使用平台' : '注册后即可开始编排用例' }}</p>
        </div>

        <el-tabs v-model="activeTab" class="login-tabs" stretch>
          <el-tab-pane label="登录" name="login" />
          <el-tab-pane label="注册" name="register" />
        </el-tabs>

        <el-form ref="formRef" :model="form" :rules="rules" label-position="top" @submit.prevent="onSubmit">
          <el-form-item label="用户名" prop="username">
            <el-input v-model="form.username" placeholder="请输入用户名" :prefix-icon="User" size="large" />
          </el-form-item>
          <el-form-item label="密码" prop="password">
            <el-input v-model="form.password" type="password" show-password placeholder="请输入密码" :prefix-icon="Lock" size="large" />
          </el-form-item>
          <el-form-item v-if="activeTab === 'register'" label="显示名（可选）" prop="name">
            <el-input v-model="form.name" placeholder="留空则用用户名" size="large" />
          </el-form-item>
          <el-button type="primary" native-type="submit" class="submit-btn" :loading="loading" size="large">
            {{ activeTab === 'login' ? '登 录' : '注 册' }}
          </el-button>
        </el-form>

        <div v-if="activeTab === 'register'" class="hint">
          密码要求：至少 8 位，必须同时包含字母和数字<br>
          首个注册用户自动成为管理员，其余为普通成员
        </div>
      </div>
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, watch, computed } from 'vue'
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

watch(activeTab, () => {
  formRef.value?.clearValidate()
})

// ===== 鼠标视差：左侧装饰节点跟随鼠标轻微移动 =====
const mouseX = ref(0)
const mouseY = ref(0)
const parallaxStyle = computed(() => ({
  transform: `translate(${mouseX.value * 12}px, ${mouseY.value * 12}px)`,
}))

function onMouseMove(e: MouseEvent) {
  // 归一化到 -1 ~ 1
  mouseX.value = (e.clientX / window.innerWidth - 0.5) * 2
  mouseY.value = (e.clientY / window.innerHeight - 0.5) * 2
}

async function onSubmit() {
  if (!formRef.value || loading.value) return
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
  background: var(--app-bg);
  overflow: hidden;
}

/* ===== 左侧品牌展示区 ===== */
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
/* 背景光晕装饰 */
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

/* 浮动 DAG 节点装饰层 */
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
/* 节点持续浮动动画，不同延迟错开 */
.deco-node {
  transform-origin: center;
  animation: deco-float 6s ease-in-out infinite;
}
.deco-node-1 { animation-delay: 0s; }
.deco-node-2 { animation-delay: 0.8s; }
.deco-node-3 { animation-delay: 1.6s; }
.deco-node-4 { animation-delay: 2.4s; }
.deco-node-5 { animation-delay: 3.2s; }
.deco-node-6 { animation-delay: 1.2s; }
.deco-node-7 { animation-delay: 2s; }
@keyframes deco-float {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-12px); }
}

/* 品牌内容 */
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

/* 核心能力卡片 */
.feature-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.feature-item {
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
.feature-item:hover {
  transform: translateX(6px);
  background: rgba(255, 255, 255, 0.16);
}
.feature-icon {
  flex-shrink: 0;
  width: 40px;
  height: 40px;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.15);
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
}
.feature-name {
  font-size: 15px;
  font-weight: 600;
  margin-bottom: 4px;
}
.feature-desc {
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
  margin-bottom: 28px;
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
.login-tabs {
  margin-bottom: 8px;
}
.submit-btn {
  width: 100%;
  margin-top: 4px;
  border-radius: 10px;
  font-weight: 600;
  letter-spacing: 1px;
}
.hint {
  margin-top: 16px;
  font-size: 12px;
  color: var(--app-text-muted);
  text-align: center;
  line-height: 1.6;
}

/* ===== 响应式：窄屏隐藏左侧品牌区 ===== */
@media (max-width: 900px) {
  .brand-panel {
    display: none;
  }
  .form-panel {
    width: 100%;
  }
}

/* 尊重减少动态效果偏好 */
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

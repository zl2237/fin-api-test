<template>
  <div class="login-page">
    <!-- 左侧品牌展示区：静态 DAG 品牌图（产品视觉识别符，不做任何动画） -->
    <aside class="brand-panel">
      <div class="brand-content">
        <div class="brand-logo-row">
          <svg viewBox="0 0 32 32" width="40" height="40" fill="none" xmlns="http://www.w3.org/2000/svg">
            <defs>
              <marker id="loginBrandArrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="4" markerHeight="4" orient="auto">
                <polygon points="0 0, 10 5, 0 10" fill="#fff"/>
              </marker>
            </defs>
            <!-- 产品图标：DAG 节点汇聚 → 断言对勾（与 favicon 同构的白色版） -->
            <rect width="32" height="32" rx="2" fill="rgba(255,255,255,0.16)" />
            <g stroke="#fff" stroke-width="1" fill="none" stroke-linecap="round">
              <path d="M7.4 9 L11 12" marker-end="url(#loginBrandArrow)" />
              <path d="M16 7.6 L16 11.5" marker-end="url(#loginBrandArrow)" />
              <path d="M24.6 9 L21 12" marker-end="url(#loginBrandArrow)" />
            </g>
            <g fill="rgba(255,255,255,0.18)" stroke="#fff" stroke-width="1.1">
              <circle cx="6.8" cy="8.2" r="1.9" />
              <circle cx="16" cy="6.5" r="1.9" />
              <circle cx="25.2" cy="8.2" r="1.9" />
            </g>
            <path d="M11 19.6 L14.6 23.4 L21.4 15.6" fill="none" stroke="#fff" stroke-width="2"
                  stroke-linecap="round" stroke-linejoin="round" />
          </svg>
          <span class="brand-name">fin-api-test</span>
        </div>
        <h1 class="brand-title">接口自动化测试平台</h1>
        <p class="brand-slogan app-mono">DAG 可视化编排，17 种断言，一键执行报告</p>

        <!-- 静态 DAG 品牌大图：本产品视觉识别符（画布同构，无动画） -->
        <svg class="brand-dag" viewBox="0 0 480 300" fill="none" xmlns="http://www.w3.org/2000/svg" role="img"
             aria-label="用例编排 DAG 示意：三个接口节点汇聚到断言节点，其中一条链路校验失败">
          <defs>
            <marker id="dagArrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto">
              <polygon points="0 0, 10 5, 0 10" fill="rgba(255,255,255,0.55)" />
            </marker>
          </defs>
          <!-- 连线：两条成功链路（实线）+ 一条失败链路（虚线红） -->
          <path d="M110 70 C 170 70, 190 128, 250 138" stroke="rgba(255,255,255,0.4)" stroke-width="1.6" marker-end="url(#dagArrow)" />
          <path d="M110 150 C 170 150, 190 148, 250 148" stroke="rgba(255,255,255,0.4)" stroke-width="1.6" marker-end="url(#dagArrow)" />
          <path d="M110 230 C 170 230, 190 168, 250 158" stroke="rgba(255,120,110,0.75)" stroke-width="1.6" stroke-dasharray="5 5" marker-end="url(#dagArrow)" />
          <path d="M330 148 C 370 148, 380 70, 425 66" stroke="rgba(255,255,255,0.4)" stroke-width="1.6" marker-end="url(#dagArrow)" />
          <path d="M330 148 C 370 148, 380 226, 425 230" stroke="rgba(255,255,255,0.4)" stroke-width="1.6" marker-end="url(#dagArrow)" />
          <!-- 上游接口节点 -->
          <g>
            <rect x="28" y="46" width="82" height="48" rx="2" fill="rgba(255,255,255,0.1)" stroke="rgba(255,255,255,0.55)" stroke-width="1.2" />
            <text x="69" y="67" text-anchor="middle" fill="rgba(255,255,255,0.85)" font-size="11" font-weight="600">POST</text>
            <text x="69" y="83" text-anchor="middle" fill="rgba(255,255,255,0.55)" font-size="9">/login</text>
          </g>
          <g>
            <rect x="28" y="126" width="82" height="48" rx="2" fill="rgba(255,255,255,0.1)" stroke="rgba(255,255,255,0.55)" stroke-width="1.2" />
            <text x="69" y="147" text-anchor="middle" fill="rgba(255,255,255,0.85)" font-size="11" font-weight="600">POST</text>
            <text x="69" y="163" text-anchor="middle" fill="rgba(255,255,255,0.55)" font-size="9">/orders</text>
          </g>
          <!-- 失败链路节点 -->
          <g>
            <rect x="28" y="206" width="82" height="48" rx="2" fill="rgba(255,120,110,0.12)" stroke="rgba(255,120,110,0.8)" stroke-width="1.2" />
            <text x="69" y="227" text-anchor="middle" fill="rgba(255,255,255,0.85)" font-size="11" font-weight="600">GET</text>
            <text x="69" y="243" text-anchor="middle" fill="rgba(255,255,255,0.55)" font-size="9">/refund</text>
          </g>
          <!-- 汇聚断言节点（产品核心：17 种校验） -->
          <g>
            <rect x="250" y="118" width="80" height="60" rx="2" fill="rgba(255,255,255,0.16)" stroke="#fff" stroke-width="1.3" />
            <path d="M272 148 l7 8 l14 -16" stroke="#fff" stroke-width="2.2" fill="none" stroke-linecap="round" stroke-linejoin="round" />
            <text x="290" y="171" text-anchor="middle" fill="rgba(255,255,255,0.6)" font-size="9">17 断言</text>
          </g>
          <!-- 下游结果节点 -->
          <g>
            <rect x="425" y="42" width="34" height="44" rx="2" fill="rgba(110,220,150,0.16)" stroke="rgba(110,220,150,0.85)" stroke-width="1.2" />
            <path d="M435 60 l5 6 l10 -12" stroke="rgba(110,220,150,1)" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round" />
          </g>
          <g>
            <rect x="425" y="208" width="34" height="44" rx="2" fill="rgba(255,120,110,0.14)" stroke="rgba(255,120,110,0.85)" stroke-width="1.2" />
            <path d="M434 224 l12 12 M446 224 l-12 12" stroke="rgba(255,120,110,1)" stroke-width="2" stroke-linecap="round" />
          </g>
        </svg>

        <!-- 三行直陈能力（无卡片无图标框，工具感文案） -->
        <ul class="brand-points">
          <li>画布拖拽编排接口流程，双击节点配断言</li>
          <li>JSONPath / 状态码 / 数据库交叉校验，17 种断言</li>
          <li>cURL 粘贴、HAR 抓包、Swagger 文档批量导入</li>
        </ul>
      </div>

      <!-- 底部版权 -->
      <div class="brand-footer">Developed by zhangle</div>
    </aside>

    <!-- 右侧表单区 -->
    <main class="form-panel">
      <div class="form-card">
        <Transition name="head-swap" mode="out-in">
          <div class="card-header" :key="activeTab">
            <h2 class="card-title">{{ activeTab === 'login' ? '欢迎回来' : '创建账号' }}</h2>
            <p class="card-sub">{{ activeTab === 'login' ? '登录以继续使用平台' : '注册后即可开始编排用例' }}</p>
          </div>
        </Transition>

        <el-tabs v-model="activeTab" class="login-tabs" stretch>
          <el-tab-pane label="登录" name="login" />
          <el-tab-pane label="注册" name="register" />
        </el-tabs>

        <el-form ref="formRef" :model="form" :rules="rules" label-position="top" @submit.prevent="onSubmit">
          <el-form-item label="用户名" prop="username">
            <el-input
              v-model="form.username"
              name="username"
              autocomplete="username"
              :spellcheck="false"
              placeholder="请输入用户名"
              :prefix-icon="User"
              size="large"
            />
          </el-form-item>
          <el-form-item label="密码" prop="password">
            <el-input
              v-model="form.password"
              type="password"
              show-password
              name="password"
              :autocomplete="activeTab === 'login' ? 'current-password' : 'new-password'"
              placeholder="请输入密码"
              :prefix-icon="Lock"
              size="large"
            />
            <!-- 规则提示前置到输入框旁（注册态/focus 可见），不再是提交失败后才发现规则 -->
            <div v-if="activeTab === 'register'" class="pwd-rule-hint">
              至少 8 位，同时包含字母和数字
              <span :class="pwdMeetsRule ? 'pwd-ok' : 'pwd-bad'">{{ pwdMeetsRule ? '✓ 已满足' : '未满足' }}</span>
            </div>
          </el-form-item>
          <Transition name="field-collapse">
            <div v-if="activeTab === 'register'" class="field-wrap">
              <el-form-item label="显示名（可选）" prop="name">
                <el-input v-model="form.name" placeholder="留空则用用户名" size="large" />
              </el-form-item>
            </div>
          </Transition>
          <el-button type="primary" native-type="submit" class="submit-btn" :loading="loading" size="large">
            {{ activeTab === 'login' ? '登 录' : '注 册' }}
          </el-button>
        </el-form>

        <Transition name="field-collapse">
          <div v-if="activeTab === 'register'" class="field-wrap">
            <div class="hint">
              密码要求：至少 8 位，必须同时包含字母和数字<br>
              首个注册用户自动成为管理员，其余为普通成员
            </div>
          </div>
        </Transition>
      </div>
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, watch, computed } from 'vue'
// computed 仅用于注册密码实时合规提示；品牌区已静态化，无交互状态
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

// 注册密码实时合规提示（与后端 validate_password_strength 同规则：≥8 位 + 字母 + 数字）
const pwdMeetsRule = computed(() =>
  form.password.length >= 8 && /[a-zA-Z]/.test(form.password) && /\d/.test(form.password)
)

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

/* ===== 左侧品牌展示区：实底深墨青 + 蓝图网格（工程制图纸，替代渐变光晕） ===== */
.brand-panel {
  position: relative;
  flex: 1;
  min-width: 0;
  background: #0e2a33;
  display: flex;
  flex-direction: column;
  justify-content: center;
  padding: 60px 56px;
  overflow: hidden;
}
/* 蓝图网格：主网格 24px + 细分格 4px（品牌母题：测试画布的工程底纹） */
.brand-panel::before {
  content: '';
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(var(--app-grid-line-strong) 1px, transparent 1px),
    linear-gradient(90deg, var(--app-grid-line) 1px, transparent 1px),
    linear-gradient(var(--app-grid-line) 1px, transparent 1px),
    linear-gradient(90deg, var(--app-grid-line) 1px, transparent 1px);
  background-size:
    var(--app-grid-size) var(--app-grid-size),
    var(--app-grid-size) var(--app-grid-size),
    calc(var(--app-grid-size) / 6) calc(var(--app-grid-size) / 6),
    calc(var(--app-grid-size) / 6) calc(var(--app-grid-size) / 6);
  background-position: -1px -1px;
  pointer-events: none;
}

/* 品牌内容 */
.brand-content {
  position: relative;
  z-index: 2;
  color: #fff;
  max-width: 460px;
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
  margin: 0 0 40px;
  line-height: 1.6;
}

/* 静态 DAG 品牌大图：产品视觉识别符，纯静态（无动画无交互） */
.brand-dag {
  display: block;
  width: 100%;
  max-width: 440px;
  height: auto;
  margin-bottom: 36px;
}

/* 三行直陈能力：无卡片无图标框，工具感文案 */
.brand-points {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.brand-points li {
  position: relative;
  padding-left: 18px;
  font-size: 14px;
  line-height: 1.6;
  opacity: 0.85;
}
/* 能力列表标记：DAG 节点方框（与画布节点同构，替代实心圆点） */
.brand-points li::before {
  content: '';
  position: absolute;
  left: 0;
  top: 8px;
  width: 7px;
  height: 7px;
  border: 1.2px solid rgba(255, 255, 255, 0.55);
  border-radius: 1px;
  background: transparent;
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
  /* 实底面板 + 发丝线 + 单层低阴影（工程面板语言，无入场动画：登录是工具页） */
  padding: 32px 28px;
  background: var(--app-card-solid);
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius);
  box-shadow: var(--app-shadow-lg);
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
  border-radius: var(--app-radius-sm);
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
/* 注册密码实时合规提示（前置到输入框旁） */
.pwd-rule-hint {
  margin-top: 4px;
  font-size: 12px;
  color: var(--app-text-muted);
  line-height: 1.5;
}
.pwd-ok { color: var(--app-success); margin-left: 6px; }
.pwd-bad { color: var(--app-text-muted); margin-left: 6px; }

/* ===== 登录/注册切换过渡 ===== */
/* 标题/副标题淡切（out-in 模式：旧的先淡出、新的再淡入） */
.head-swap-enter-active,
.head-swap-leave-active {
  transition: opacity 0.18s ease, transform 0.18s ease;
}
.head-swap-enter-from {
  opacity: 0;
  transform: translateY(6px);
}
.head-swap-leave-to {
  opacity: 0;
  transform: translateY(-6px);
}
/* 条件字段高度展开/收起（max-height 近似，避免布局跳变） */
.field-collapse-enter-active,
.field-collapse-leave-active {
  transition: opacity 0.25s ease, transform 0.25s ease, max-height 0.25s ease, margin 0.25s ease;
  overflow: hidden;
  max-height: 110px; /* 覆盖 显示名输入框(~80px) 与 密码提示(~60px) 的实际高度 */
}
.field-collapse-enter-from,
.field-collapse-leave-to {
  opacity: 0;
  transform: translateY(-8px);
  max-height: 0;
}
@media (prefers-reduced-motion: reduce) {
  .head-swap-enter-active,
  .head-swap-leave-active,
  .field-collapse-enter-active,
  .field-collapse-leave-active {
    transition: none;
  }
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

</style>

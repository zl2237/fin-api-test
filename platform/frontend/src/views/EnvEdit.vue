<template>
  <div class="env-edit">
    <!-- 顶部工具栏 -->
    <div class="edit-header">
      <el-button @click="onBack">
        <el-icon><ArrowLeft /></el-icon>返回
      </el-button>
      <span class="edit-title">{{ isEdit ? '编辑环境' : '新建环境' }}</span>
      <div class="header-right">
        <span v-if="dirty" class="dirty-tip">有未保存改动</span>
        <el-button type="primary" :loading="saving" @click="onSave">保存 (Ctrl+S)</el-button>
      </div>
    </div>

    <!-- 主体：分区卡片 -->
    <div class="edit-body" v-loading="loading" element-loading-text="加载环境配置中...">
      <!-- 基础信息 -->
      <div class="card-section">
        <div class="section-title">基础信息</div>
        <el-form label-width="120px" :model="formData">
          <el-form-item label="环境名称" required>
            <el-input v-model="formData.name" placeholder="test / pre / prod" style="width: 280px" />
          </el-form-item>
          <el-form-item label="Base URL" required>
            <el-input v-model="formData.base_url" placeholder="http://127.0.0.1:8080" style="width: 380px" />
          </el-form-item>
          <el-form-item label="业务成功码">
            <el-input v-model="formData.success_codes" placeholder="200" style="width: 280px" />
            <span class="form-hint">响应 code 命中任一即判成功，逗号分隔；ThinkPHP 系填 1 或 200,1</span>
          </el-form-item>
          <el-form-item label="超时时间">
            <el-input-number v-model="formData.timeout" :min="1" :max="120" controls-position="right" style="width: 140px" />
            <span class="form-hint">秒，接口请求超时时间（1-120）</span>
          </el-form-item>
          <el-form-item label="默认环境">
            <el-switch v-model="formData.is_default" />
            <span class="form-hint">设为默认后，执行用例时自动选中此环境</span>
          </el-form-item>
        </el-form>
      </div>

      <!-- 数据库配置 -->
      <div class="card-section">
        <div class="section-title">
          数据库配置
          <!-- 新建态以禁用态预告能力（原 v-if 凭空消失，用户不知保存后可测试） -->
          <el-tooltip v-if="!isEdit" content="保存后可测试连接" placement="top">
            <el-button size="small" disabled>测试连接</el-button>
          </el-tooltip>
          <el-button v-else size="small" :loading="testingDb" @click="onTestDb">测试连接</el-button>
        </div>
        <el-form label-width="120px">
          <div class="form-row">
            <el-form-item label="Host">
              <el-input v-model="formData.db_config.host" placeholder="127.0.0.1" />
            </el-form-item>
            <el-form-item label="Port">
              <el-input-number v-model="formData.db_config.port" :min="1" :max="65535" controls-position="right" />
            </el-form-item>
          </div>
          <div class="form-row">
            <el-form-item label="用户名">
              <el-input v-model="formData.db_config.user" placeholder="root" />
            </el-form-item>
            <el-form-item label="密码">
              <el-input v-model="formData.db_config.password" type="password" show-password placeholder="数据库密码" />
            </el-form-item>
          </div>
          <el-form-item label="数据库名">
            <el-input v-model="formData.db_config.database" placeholder="fin_order" style="width: 280px" />
          </el-form-item>
        </el-form>
      </div>

      <!-- 登录配置 -->
      <div class="card-section">
        <div class="section-title">
          登录配置
          <span class="section-hint">token 型登录后注入鉴权头；session 型登录后靠 Cookie 会话保持</span>
          <el-tooltip v-if="!isEdit" content="保存后可测试登录" placement="top">
            <el-button size="small" disabled>测试登录</el-button>
          </el-tooltip>
          <el-button v-else size="small" :loading="testingLogin" @click="onTestLogin">测试登录</el-button>
        </div>
        <el-form label-width="120px">
          <el-form-item label="登录接口路径">
            <el-input v-model="formData.login_config.login_path" placeholder="/api/home/login/userLogin" style="width: 380px" />
          </el-form-item>
          <div class="form-row">
            <el-form-item label="登录方式">
              <el-radio-group v-model="formData.login_config.login_mode">
                <el-radio value="token">Token 注入请求头</el-radio>
                <el-radio value="session">Session Cookie</el-radio>
              </el-radio-group>
            </el-form-item>
            <el-form-item label="提交格式">
              <el-radio-group v-model="formData.login_config.login_content_type">
                <el-radio value="json">JSON</el-radio>
                <el-radio value="form">表单 urlencoded</el-radio>
              </el-radio-group>
            </el-form-item>
          </div>
          <el-form-item label="登录请求体">
            <KeyValueTable
              v-model="formData.login_config.login_body"
              key-placeholder="字段名"
              value-placeholder="字段值"
              value-type="textarea"
            />
            <div v-if="formData.login_config.login_content_type === 'form'" class="form-hint">
              表单模式下键值按 urlencoded 提交；键可含中括号，如 <code>data[username]</code>
            </div>
          </el-form-item>

          <div class="group-title">验证码自动识别<span>选填 · 图片地址与字段名都填才启用</span></div>
          <div class="form-row">
            <el-form-item label="验证码图片地址">
              <el-input v-model="formData.login_config.captcha_url" placeholder="/Public/verify.html" />
            </el-form-item>
            <el-form-item label="验证码字段名">
              <el-input v-model="formData.login_config.captcha_field" placeholder="data[verify]" />
            </el-form-item>
          </div>
          <el-form-item label="识别重试次数">
            <el-input-number
              v-model="formData.login_config.captcha_retry"
              :min="1"
              :max="20"
              :step="1"
              step-strictly
            />
            <div class="form-hint">
              验证码识别错误时自动换图重试的次数，默认 3；验证码较难识别时可调大提高登录成功率
            </div>
          </el-form-item>
          <div class="group-hint">
            登录前经同一会话取验证码图 → OCR 识别 → 自动填入该字段提交。需后端安装 ddddocr
          </div>

          <template v-if="formData.login_config.login_mode === 'token'">
            <div class="group-title">Token 注入<span>Token 模式专属</span></div>
            <div class="form-row">
              <el-form-item label="Token JSONPath">
                <el-input v-model="formData.login_config.token_jsonpath" placeholder="$.data.token" />
              </el-form-item>
              <el-form-item label="Header 名称">
                <el-input v-model="formData.login_config.auth_header_name" placeholder="Authorization" />
              </el-form-item>
            </div>
            <el-form-item label="鉴权头值模板">
              <el-input
                v-model="formData.login_config.auth_header_value_template"
                placeholder="${token}"
                style="width: 380px"
              />
              <div class="form-hint">
                支持 <code>${token}</code> 和 <code>${timestamp}</code> 占位符。例：<code>Bearer ${token}</code>、<code>${token}_${timestamp}</code>；留空则等价于 <code>${token}</code>
              </div>
            </el-form-item>
          </template>
          <template v-else>
            <div class="group-title">登录成功校验<span>Session 模式专属 · 选填</span></div>
            <div class="form-row">
              <el-form-item label="成功校验路径">
                <el-input v-model="formData.login_config.login_check_jsonpath" placeholder="$.code" />
              </el-form-item>
              <el-form-item label="期望值">
                <el-input v-model="formData.login_config.login_check_value" placeholder="success" />
              </el-form-item>
            </div>
            <div class="group-hint">
              两项都填才生效：响应中该路径的值等于期望值才算登录成功，留空仅校验 HTTP 200。
              登录成功后 Cookie 自动保持到该环境的后续请求
            </div>
          </template>
        </el-form>
      </div>

      <!-- 通知配置 -->
      <div class="card-section">
        <div class="section-title">
          通知配置
          <span class="section-hint">用于执行后给企业微信机器人推送结果</span>
        </div>
        <el-form label-width="120px">
          <el-form-item label="企微机器人 Webhook">
            <el-input
              v-model="formData.notify_config.wecom_webhook"
              placeholder="https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx"
              style="width: 480px"
            />
          </el-form-item>
          <el-form-item label="失败时通知">
            <el-switch v-model="formData.notify_config.enable_on_failure" />
          </el-form-item>
          <el-form-item label="成功时通知">
            <el-switch v-model="formData.notify_config.enable_on_success" />
          </el-form-item>
        </el-form>
      </div>

      <!-- 公共请求头 -->
      <div class="card-section">
        <div class="section-title">
          公共请求头
          <span class="section-hint">所有接口请求都会带上这些 header</span>
        </div>
        <KeyValueTable
          v-model="formData.common_headers"
          key-placeholder="Content-Type"
          value-placeholder="application/json"
        />
      </div>

      <!-- 业务变量 -->
      <div class="card-section">
        <div class="section-title">
          业务变量
          <span class="section-hint">测试中可用 ${env.变量名} 引用</span>
          <el-button text size="small" class="help-link" @click="store.openCoreCapability('expression')">
            查看表达式用法
          </el-button>
        </div>
        <KeyValueTable
          v-model="formData.variables"
          key-placeholder="变量名"
          value-placeholder="变量值"
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, reactive, watch, nextTick } from 'vue'
import { useRoute, useRouter, onBeforeRouteLeave } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowLeft } from '@element-plus/icons-vue'
import { envApi, type Environment } from '@/api'
import { useAppStore } from '@/stores'
import { useTabStore } from '@/stores/tabs'
import { storeToRefs } from 'pinia'
import KeyValueTable from '@/components/KeyValueTable.vue'

const route = useRoute()
const router = useRouter()
const store = useAppStore()
const tabStore = useTabStore()
const { currentProjectId } = storeToRefs(store)

const isEdit = computed(() => !!route.params.id)
const saving = ref(false)
const dirty = ref(false)
const loading = ref(false)
const testingDb = ref(false)
const testingLogin = ref(false)

interface EnvFormData {
  id?: number
  name: string
  base_url: string
  success_codes: string
  timeout: number
  is_default: boolean
  db_config: { host: string; port: number; user: string; password: string; database: string }
  login_config: {
    login_path: string
    login_body: Record<string, any>
    login_mode: string
    login_content_type: string
    token_jsonpath: string
    auth_header_name: string
    auth_header_value_template: string
    login_check_jsonpath: string
    login_check_value: string
    captcha_url: string
    captcha_field: string
    captcha_retry: number | null
  }
  notify_config: {
    wecom_webhook: string
    enable_on_failure: boolean
    enable_on_success: boolean
  }
  variables: Record<string, any>
  common_headers: Record<string, any>
}

const formData = reactive<EnvFormData>({
  name: '',
  base_url: '',
  success_codes: '200',
  timeout: 15,
  is_default: false,
  db_config: { host: '', port: 3306, user: '', password: '', database: '' },
  login_config: {
    login_path: '/api/home/login/userLogin',
    login_body: {},
    login_mode: 'token',
    login_content_type: 'json',
    token_jsonpath: '$.data.token',
    auth_header_name: 'Authorization',
    auth_header_value_template: '${token}',
    login_check_jsonpath: '',
    login_check_value: '',
    captcha_url: '',
    captcha_field: '',
    captcha_retry: 3,
  },
  notify_config: {
    wecom_webhook: '',
    enable_on_failure: true,
    enable_on_success: false,
  },
  variables: {},
  common_headers: { 'Content-Type': 'application/json' },
})

watch(formData, () => { dirty.value = true }, { deep: true })

async function loadEnv() {
  if (!isEdit.value) return
  const id = Number(route.params.id)
  const env: Environment = await envApi.get(id)
  formData.id = env.id
  formData.name = env.name
  formData.base_url = env.base_url
  formData.success_codes = env.success_codes || '200'
  formData.timeout = env.timeout ?? 15
  formData.is_default = env.is_default
  // db_config
  const db = env.db_config || {}
  formData.db_config = {
    host: db.host || '',
    port: db.port || 3306,
    user: db.user || '',
    password: db.password || '',
    database: db.database || '',
  }
  // login_config（兼容旧数据：若 login_config 为空但 variables 里有登录配置，则从 variables 迁移）
  const lc = env.login_config || {}
  const oldVars = env.variables || {}
  formData.login_config = {
    login_path: lc.login_path || oldVars.login_path || '/api/home/login/userLogin',
    login_body: lc.login_body || oldVars.login_body || {},
    login_mode: lc.login_mode || 'token',
    login_content_type: lc.login_content_type || 'json',
    token_jsonpath: lc.token_jsonpath || oldVars.token_jsonpath || '$.data.token',
    auth_header_name: lc.auth_header_name || oldVars.auth_header_name || 'Authorization',
    auth_header_value_template: lc.auth_header_value_template || '${token}',
    login_check_jsonpath: lc.login_check_jsonpath || '',
    login_check_value: lc.login_check_value || '',
    captcha_url: lc.captcha_url || '',
    captcha_field: lc.captcha_field || '',
    captcha_retry: lc.captcha_retry ?? 3,
  }
  // notify_config（兼容旧数据：wecom_webhook 从 variables 迁移）
  const nc = env.notify_config || {}
  formData.notify_config = {
    wecom_webhook: nc.wecom_webhook || oldVars.wecom_webhook || '',
    enable_on_failure: nc.enable_on_failure ?? true,
    enable_on_success: nc.enable_on_success ?? false,
  }
  // variables（去掉旧的登录/通知字段，只保留业务变量）
  const pureVars: Record<string, any> = {}
  for (const [k, v] of Object.entries(oldVars)) {
    if (!['login_path', 'login_body', 'token_jsonpath', 'auth_header_name', 'wecom_webhook'].includes(k)) {
      pureVars[k] = v
    }
  }
  formData.variables = pureVars
  formData.common_headers = env.common_headers || { 'Content-Type': 'application/json' }
  // watch(formData) 是异步触发的，会在下一个 tick 把 dirty 设为 true；
  // 这里用 nextTick 等待 watch 触发后再重置，避免误判"有未保存改动"
  await nextTick()
  dirty.value = false
}

function onBack() {
  router.push('/envs')
}

// ===== 未保存改动防丢失：路由离开 + 关闭/刷新标签页双层拦截 =====
// 与 CaseDesigner 同法：编辑页是带 :id 的临时页，守卫放行时统一关闭自身标签，避免残留 + keep-alive 复活
onBeforeRouteLeave(async () => {
  const closeSelfTab = () => tabStore.removeTab(route.path)
  if (!dirty.value) {
    closeSelfTab()
    return true
  }
  try {
    await ElMessageBox.confirm(
      '有未保存的环境配置改动，离开后将丢失。确定离开？',
      '未保存提示',
      { type: 'warning', confirmButtonText: '放弃改动并离开', cancelButtonText: '留在本页' },
    )
    closeSelfTab()
    return true
  } catch {
    // 留在本页：标签原样保留
    return false
  }
})

const onBeforeUnload = (e: BeforeUnloadEvent) => {
  if (dirty.value) {
    e.preventDefault()
    e.returnValue = ''
  }
}
onMounted(() => window.addEventListener('beforeunload', onBeforeUnload))
onUnmounted(() => window.removeEventListener('beforeunload', onBeforeUnload))

async function onSave() {
  // trim 关键字段，避免首尾空格
  formData.name = formData.name.trim()
  formData.base_url = formData.base_url.trim()
  if (!formData.name || !formData.base_url) {
    ElMessage.warning('环境名称和 Base URL 不能为空')
    return
  }
  saving.value = true
  try {
    const payload: Partial<Environment> = {
      project_id: currentProjectId.value!,
      name: formData.name,
      base_url: formData.base_url,
      success_codes: formData.success_codes.trim() || '200',
      timeout: formData.timeout,
      is_default: formData.is_default,
      db_config: formData.db_config,
      login_config: formData.login_config,
      notify_config: formData.notify_config,
      variables: formData.variables,
      common_headers: formData.common_headers,
    }
    if (isEdit.value) {
      await envApi.update(formData.id!, payload)
      ElMessage.success('已保存')
    } else {
      await envApi.create(payload)
      ElMessage.success('已创建')
      router.push('/envs')
    }
    dirty.value = false
    // 重新加载环境列表（更新顶部下拉）
    store.loadEnvironments()
  } catch (e: any) {
    ElMessage.error(e.message || '保存失败')
  } finally {
    saving.value = false
  }
}

async function onTestDb() {
  if (!formData.id) return
  if (dirty.value) {
    ElMessage.warning('有未保存改动，请先保存再测试')
    return
  }
  testingDb.value = true
  try {
    const res = await envApi.testDb(formData.id)
    if (res.ok) {
      ElMessage.success(res.message)
    } else {
      ElMessage.error(res.message)
    }
  } catch (e: any) {
    ElMessage.error(e.message || '测试失败')
  } finally {
    testingDb.value = false
  }
}

async function onTestLogin() {
  if (!formData.id) return
  if (dirty.value) {
    ElMessage.warning('有未保存改动，请先保存再测试')
    return
  }
  testingLogin.value = true
  try {
    const res = await envApi.testLogin(formData.id)
    if (res.ok) {
      ElMessage.success(res.message)
    } else {
      ElMessage.error(res.message)
    }
  } catch (e: any) {
    ElMessage.error(e.message || '测试失败')
  } finally {
    testingLogin.value = false
  }
}

onMounted(() => {
  // 编辑模式加载数据期间显示遮罩，避免空白无反馈
  loading.value = isEdit.value
  loadEnv().finally(() => { loading.value = false })
  window.addEventListener('keydown', onKeydown)
})
onUnmounted(() => {
  window.removeEventListener('keydown', onKeydown)
})

function onKeydown(e: KeyboardEvent) {
  if ((e.ctrlKey || e.metaKey) && e.key === 's') {
    e.preventDefault()
    onSave()
  }
}
</script>

<style scoped>
.env-edit {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--app-bg);
}
.edit-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 20px;
  background: var(--app-card);
  border-bottom: 1px solid var(--app-border);
}
.edit-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--app-text);
  flex: 1;
}
.header-right {
  display: flex;
  align-items: center;
  gap: 10px;
}
.dirty-tip {
  color: var(--app-warn-accent);
  font-size: 13px;
}
.edit-body {
  flex: 1;
  overflow: auto;
  padding: 16px 20px;
}
.card-section {
  background: var(--app-card-solid);
  border-radius: var(--app-radius-lg);
  padding: 20px 24px;
  margin-bottom: 16px;
  box-shadow: var(--app-shadow-sm);
}
.section-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--app-text);
  margin-bottom: 16px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.section-hint {
  font-size: 12px;
  font-weight: 400;
  color: var(--app-text-muted);
}
.help-link {
  margin-left: auto;
  padding: 2px 6px;
  font-size: 12px;
}
.form-row {
  display: flex;
  gap: 16px;
}
.form-row .el-form-item {
  flex: 1;
}
.form-hint {
  margin-left: 12px;
  font-size: 12px;
  color: var(--app-text-muted);
}
.group-title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 20px 0 14px;
  font-size: 13px;
  font-weight: 600;
  color: var(--app-text);
}
.group-title::before {
  content: '';
  width: 3px;
  height: 13px;
  border-radius: 2px;
  background: var(--app-primary);
}
.group-title span {
  font-size: 12px;
  font-weight: 400;
  color: var(--app-text-muted);
}
.group-hint {
  margin: -4px 0 4px 132px;
  font-size: 12px;
  line-height: 1.6;
  color: var(--app-text-muted);
}
</style>

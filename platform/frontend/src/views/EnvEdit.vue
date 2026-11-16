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
        <el-button type="primary" :loading="saving" @click="onSave">保存 (Ctrl+S)<DrawCheck v-if="justSaved" :size="13" class="save-check" /></el-button>
      </div>
    </div>

    <!-- 主体：统一 4 列网格 + 顶部标签，说明文字全部收进标签旁 ? 提示 -->
    <div v-if="loadError" class="app-load-error">
      <el-icon><WarningFilled /></el-icon>
      <span>{{ loadError }}</span>
      <el-button size="small" @click="initialLoad">重试</el-button>
    </div>
    <div v-else class="edit-body" v-loading="loading" element-loading-text="加载环境配置中...">
      <el-form ref="formRef" :model="formData" :rules="formRules" label-position="top" class="env-form" @submit.prevent>
        <!-- 基础信息 -->
        <div class="card-section">
          <div class="section-head"><span class="title">基础信息</span></div>
          <div class="form-grid">
            <el-form-item label="环境名称" prop="name">
              <el-input v-model="formData.name" placeholder="test / pre / prod" />
            </el-form-item>
            <el-form-item label="Base URL" prop="base_url" class="col-2">
              <el-input v-model="formData.base_url" placeholder="http://127.0.0.1:8080" />
            </el-form-item>
            <el-form-item>
              <template #label>
                默认环境
                <el-tooltip content="执行用例时自动选中" placement="top"><el-icon class="lbl-help"><QuestionFilled /></el-icon></el-tooltip>
              </template>
              <el-switch v-model="formData.is_default" />
            </el-form-item>

            <el-form-item>
              <template #label>
                业务成功码
                <el-tooltip content="响应 code 命中任一即判成功，逗号分隔（ThinkPHP 系填 1 或 200,1）" placement="top"><el-icon class="lbl-help"><QuestionFilled /></el-icon></el-tooltip>
              </template>
              <el-input v-model="formData.success_codes" placeholder="200,1" />
            </el-form-item>
            <el-form-item label="超时（秒）">
              <el-input-number v-model="formData.timeout" :min="1" :max="120" controls-position="right" />
            </el-form-item>
            <el-form-item>
              <template #label>
                失败重试次数
                <el-tooltip content="请求层失败（状态码/业务码/超时）自动重发；0=不重试，断言失败不重试" placement="top"><el-icon class="lbl-help"><QuestionFilled /></el-icon></el-tooltip>
              </template>
              <el-input-number v-model="formData.node_retry_count" :min="0" :max="10" controls-position="right" />
            </el-form-item>
            <el-form-item>
              <template #label>
                重试间隔（秒）
                <el-tooltip content="被测系统有分钟级异步同步时可调大（如 60）" placement="top"><el-icon class="lbl-help"><QuestionFilled /></el-icon></el-tooltip>
              </template>
              <el-input-number v-model="formData.node_retry_interval" :min="1" :max="600" controls-position="right" />
            </el-form-item>
          </div>
        </div>

        <!-- 数据库配置 -->
        <div class="card-section">
          <div class="section-head">
            <span class="title">数据库配置</span>
            <span class="grow" />
            <!-- 新建态以禁用态预告能力（原 v-if 凭空消失，用户不知保存后可测试） -->
            <el-tooltip v-if="!isEdit" content="保存后可测试连接" placement="top">
              <el-button size="small" disabled>测试连接</el-button>
            </el-tooltip>
            <el-button v-else size="small" :loading="testingDb" @click="onTestDb">测试连接</el-button>
          </div>
          <div class="form-grid">
            <el-form-item label="Host" class="col-2">
              <el-input v-model="formData.db_config.host" placeholder="127.0.0.1" />
            </el-form-item>
            <el-form-item label="Port">
              <el-input-number v-model="formData.db_config.port" :min="1" :max="65535" controls-position="right" />
            </el-form-item>
            <el-form-item label="用户名">
              <el-input v-model="formData.db_config.user" placeholder="root" />
            </el-form-item>
            <el-form-item label="密码" class="col-2">
              <el-input v-model="formData.db_config.password" type="password" show-password placeholder="数据库密码" />
            </el-form-item>
            <el-form-item class="col-2">
              <template #label>
                数据库名
                <el-tooltip content="「查库」参数与 SQL 断言/提取的数据源" placement="top"><el-icon class="lbl-help"><QuestionFilled /></el-icon></el-tooltip>
              </template>
              <el-input v-model="formData.db_config.database" placeholder="fin_order" />
            </el-form-item>
          </div>
        </div>

        <!-- 登录配置（enabled 开关：免登录环境关闭即跳过登录，关联表单整体隐藏） -->
        <div class="card-section">
          <div class="section-head">
            <span class="title">登录配置</span>
            <el-switch v-model="formData.login_config.enabled" size="small" class="title-switch"
              aria-label="启用登录" />
            <el-tooltip content="免登录环境（如网关直连的第三方接口）关闭即跳过登录；配置保留不丢，重新开启即恢复" placement="top">
              <el-icon class="lbl-help"><QuestionFilled /></el-icon>
            </el-tooltip>
            <span class="grow" />
            <template v-if="formData.login_config.enabled">
              <el-tooltip v-if="!isEdit" content="保存后可测试登录" placement="top">
                <el-button size="small" disabled>测试登录</el-button>
              </el-tooltip>
              <el-button v-else size="small" :loading="testingLogin" @click="onTestLogin">测试登录</el-button>
            </template>
          </div>
          <template v-if="formData.login_config.enabled">
            <div class="form-grid">
              <el-form-item label="登录接口路径" class="col-2">
                <el-input v-model="formData.login_config.login_path" placeholder="/api/home/login/userLogin" />
              </el-form-item>
              <el-form-item>
                <template #label>
                  登录方式
                  <el-tooltip content="Token 型登录后注入鉴权头；Session 型登录后靠 Cookie 会话保持" placement="top"><el-icon class="lbl-help"><QuestionFilled /></el-icon></el-tooltip>
                </template>
                <el-radio-group v-model="formData.login_config.login_mode">
                  <el-radio-button value="token">Token 注入</el-radio-button>
                  <el-radio-button value="session">Session Cookie</el-radio-button>
                </el-radio-group>
              </el-form-item>
              <el-form-item label="提交格式">
                <el-radio-group v-model="formData.login_config.login_content_type">
                  <el-radio-button value="json">JSON</el-radio-button>
                  <el-radio-button value="form">表单</el-radio-button>
                </el-radio-group>
              </el-form-item>
              <el-form-item class="span-all">
                <template #label>
                  登录请求体
                  <el-tooltip content="表单模式按 urlencoded 提交，键可含中括号（如 data[username]）" placement="top"><el-icon class="lbl-help"><QuestionFilled /></el-icon></el-tooltip>
                </template>
                <KeyValueTable
                  v-model="formData.login_config.login_body"
                  key-placeholder="字段名"
                  value-placeholder="字段值"
                  value-type="textarea"
                />
              </el-form-item>
            </div>

            <div class="group-title">
              验证码自动识别
              <el-switch v-model="captchaEnabled" size="small" />
              <el-tooltip content="登录前经同一会话取验证码图 → OCR 识别 → 自动填入该字段提交；识别错误自动换图重试；需后端安装 ddddocr" placement="top">
                <el-icon class="lbl-help"><QuestionFilled /></el-icon>
              </el-tooltip>
            </div>
            <div v-if="captchaEnabled" class="form-grid">
              <el-form-item label="图片地址" required class="col-2">
                <el-input v-model="formData.login_config.captcha_url" placeholder="/Public/verify.html" />
              </el-form-item>
              <el-form-item label="字段名" required>
                <el-input v-model="formData.login_config.captcha_field" placeholder="data[verify]" />
              </el-form-item>
              <el-form-item>
                <template #label>
                  识别重试
                  <el-tooltip content="识别错误自动换图重试；难识别可调大" placement="top"><el-icon class="lbl-help"><QuestionFilled /></el-icon></el-tooltip>
                </template>
                <el-input-number v-model="formData.login_config.captcha_retry" :min="1" :max="20" :step="1" step-strictly controls-position="right" />
              </el-form-item>
            </div>

            <template v-if="formData.login_config.login_mode === 'token'">
              <div class="group-title">Token 注入<span>Token 模式</span></div>
              <div class="form-grid">
                <el-form-item label="Token JSONPath">
                  <el-input v-model="formData.login_config.token_jsonpath" placeholder="$.data.token" />
                </el-form-item>
                <el-form-item label="Header 名称">
                  <el-input v-model="formData.login_config.auth_header_name" placeholder="Authorization" />
                </el-form-item>
                <el-form-item class="col-2">
                  <template #label>
                    鉴权头值模板
                    <el-tooltip content="支持 ${token} 与 ${timestamp} 占位符，例：Bearer ${token}；留空等价于 ${token}" placement="top"><el-icon class="lbl-help"><QuestionFilled /></el-icon></el-tooltip>
                  </template>
                  <el-input v-model="formData.login_config.auth_header_value_template" placeholder="${token}" />
                </el-form-item>
              </div>
            </template>
            <template v-else>
              <div class="group-title">登录成功校验<span>Session 模式 · 选填</span></div>
              <div class="form-grid">
                <el-form-item class="col-2">
                  <template #label>
                    成功校验路径
                    <el-tooltip content="两项都填才生效：响应中该路径的值等于期望值才算登录成功；留空仅校验 HTTP 200。Cookie 自动保持到后续请求" placement="top"><el-icon class="lbl-help"><QuestionFilled /></el-icon></el-tooltip>
                  </template>
                  <el-input v-model="formData.login_config.login_check_jsonpath" placeholder="$.code" />
                </el-form-item>
                <el-form-item label="期望值" class="col-2">
                  <el-input v-model="formData.login_config.login_check_value" placeholder="success" />
                </el-form-item>
              </div>
            </template>
          </template>
        </div>

        <!-- 通知配置（双渠道：企微机器人 + 邮件；方案执行另有聚合通知） -->
        <div class="card-section">
          <div class="section-head"><span class="title">通知配置</span><span class="sub">用例单条与方案聚合通知共用本配置</span></div>
          <div class="form-grid">
            <el-form-item label="企微机器人 Webhook" class="col-2">
              <el-input v-model="formData.notify_config.wecom_webhook" placeholder="https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx" />
            </el-form-item>
            <el-form-item label="企微·失败时通知">
              <el-switch v-model="formData.notify_config.enable_on_failure" />
            </el-form-item>
            <el-form-item label="企微·成功时通知">
              <el-switch v-model="formData.notify_config.enable_on_success" />
            </el-form-item>
          </div>
          <div class="group-title">邮件通知<span>SMTP · 服务器/发件人/收件人齐备才启用</span></div>
          <div class="form-grid">
            <el-form-item>
              <template #label>
                SMTP 服务器
                <el-tooltip content="如 smtp.exmail.qq.com；留空则邮件渠道不启用" placement="top"><el-icon class="lbl-help"><QuestionFilled /></el-icon></el-tooltip>
              </template>
              <el-input v-model="formData.notify_config.email.smtp_host" placeholder="smtp.exmail.qq.com" />
            </el-form-item>
            <el-form-item label="端口">
              <el-input-number v-model="formData.notify_config.email.smtp_port" :min="1" :max="65535" controls-position="right" />
            </el-form-item>
            <el-form-item label="SSL 直连">
              <el-switch v-model="formData.notify_config.email.use_ssl" />
            </el-form-item>
            <el-form-item label="发件人邮箱">
              <el-input v-model="formData.notify_config.email.from_addr" placeholder="bot@corp.com" />
            </el-form-item>
            <el-form-item>
              <template #label>
                授权码
                <el-tooltip content="SMTP 授权码（非邮箱登录密码）；留空表示免登录（内网中继场景）" placement="top"><el-icon class="lbl-help"><QuestionFilled /></el-icon></el-tooltip>
              </template>
              <el-input v-model="formData.notify_config.email.auth_code" type="password" show-password autocomplete="new-password" />
            </el-form-item>
            <el-form-item class="col-2">
              <template #label>
                收件人
                <el-tooltip content="多个邮箱用逗号或空格分隔" placement="top"><el-icon class="lbl-help"><QuestionFilled /></el-icon></el-tooltip>
              </template>
              <el-input v-model="formData.notify_config.email.recipients" placeholder="leader@corp.com, qa@corp.com" />
            </el-form-item>
            <el-form-item label="邮件·失败时通知">
              <el-switch v-model="formData.notify_config.email.enable_on_failure" />
            </el-form-item>
            <el-form-item label="邮件·成功时通知">
              <el-switch v-model="formData.notify_config.email.enable_on_success" />
            </el-form-item>
          </div>
        </div>

        <!-- 加密配置（接口级加密传输的密钥库：名称多对，接口加密配置按名称引用） -->
        <div class="card-section">
          <div class="section-head">
            <span class="title">加密配置</span>
            <span class="sub">名称供接口「加密配置」引用；测试/生产密钥分环境录入，禁止共用</span>
            <span class="grow" />
            <el-tooltip v-if="!isEdit" content="保存后可测试加解密" placement="top">
              <el-button size="small" disabled>测试加解密</el-button>
            </el-tooltip>
            <template v-else>
              <el-select v-model="testCipherName" size="small" clearable placeholder="第一对" class="cipher-name-select">
                <el-option v-for="n in savedKeyNames" :key="n" :label="n" :value="n" />
              </el-select>
              <el-button size="small" :loading="testingCipher" @click="onTestCipher">测试加解密</el-button>
            </template>
          </div>
          <div v-if="!formData.cipher_config.key_pairs.length" class="cipher-empty">
            未配置密钥对。对接加密传输接口（如海关 requestCipher 协议）时在此录入公私钥。
          </div>
          <div v-for="(pair, i) in formData.cipher_config.key_pairs" :key="i" class="key-pair-item">
            <div class="pair-head">
              <el-input v-model="pair.name" placeholder="名称（如 customs / cfca）" class="pair-name-input" />
              <span class="grow" />
              <el-button text type="danger" size="small" @click="formData.cipher_config.key_pairs.splice(i, 1)">删除</el-button>
            </div>
            <div class="pair-grid">
              <el-form-item>
                <template #label>
                  公钥
                  <el-tooltip content="X.509/SPKI 格式（-----BEGIN PUBLIC KEY----- 开头），粘贴其 Base64 密钥体亦可；请求加密用" placement="top"><el-icon class="lbl-help"><QuestionFilled /></el-icon></el-tooltip>
                </template>
                <el-input v-model="pair.public_key" type="textarea" :rows="3" placeholder="-----BEGIN PUBLIC KEY-----&#10;MIIBIjANBg..." spellcheck="false" />
              </el-form-item>
              <el-form-item>
                <template #label>
                  私钥
                  <el-tooltip content="PKCS#8 无口令格式（-----BEGIN PRIVATE KEY----- 开头）；响应解密与测试加解密需要成对录入" placement="top"><el-icon class="lbl-help"><QuestionFilled /></el-icon></el-tooltip>
                </template>
                <el-input v-model="pair.private_key" type="textarea" :rows="3" placeholder="-----BEGIN PRIVATE KEY-----&#10;MIIEvQ..." spellcheck="false" />
              </el-form-item>
            </div>
          </div>
          <el-button size="small" @click="addKeyPair">+ 添加密钥对</el-button>
        </div>

        <!-- 公共请求头 -->
        <div class="card-section">
          <div class="section-head">
            <span class="title">公共请求头</span>
            <span class="sub">所有接口请求自动携带</span>
          </div>
          <KeyValueTable
            v-model="formData.common_headers"
            key-placeholder="Content-Type"
            value-placeholder="application/json"
          />
        </div>
      </el-form>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, reactive, watch, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import { ArrowLeft, QuestionFilled, WarningFilled } from '@element-plus/icons-vue'
import { envApi, type Environment } from '@/api'
import { useAppStore } from '@/stores'
import { useTabStore } from '@/stores/tabs'
import { storeToRefs } from 'pinia'
import KeyValueTable from '@/components/KeyValueTable.vue'
import DrawCheck from '@/components/DrawCheck.vue'
import { useTransientFlag } from '@/composables/useTransientFlag'

const route = useRoute()
const router = useRouter()
const store = useAppStore()
const tabStore = useTabStore()
const { currentProjectId } = storeToRefs(store)

const isEdit = computed(() => !!route.params.id)
const saving = ref(false)
const dirty = ref(false)
/** 保存成功就地反馈：按钮内对勾按笔画绘制 1.5s（编辑态）；新建态保存后即跳转，仍走 toast */
const { active: justSaved, trigger: pulseSaved } = useTransientFlag(1500)
const loading = ref(false)
// 页面级加载失败（编辑模式拉环境配置失败）：内联错误块 + 重试，不让页面静默空壳
const loadError = ref('')

async function initialLoad() {
  loading.value = isEdit.value
  loadError.value = ''
  try {
    await loadEnv()
  } catch (e: any) {
    loadError.value = e?.message || '加载环境配置失败'
  } finally {
    loading.value = false
  }
}
const testingDb = ref(false)
const testingLogin = ref(false)
const testingCipher = ref(false)
// 已保存（非表单态）密钥对名称：测试加解密下拉数据源，loadEnv/保存成功后刷新
const savedKeyNames = ref<string[]>([])
const testCipherName = ref('')

function addKeyPair() {
  formData.cipher_config.key_pairs.push({ name: '', public_key: '', private_key: '' })
}

async function onTestCipher() {
  if (!formData.id) return
  if (dirty.value) {
    ElMessage.warning('有未保存改动，请先保存再测试')
    return
  }
  testingCipher.value = true
  try {
    const res = await envApi.testCipher(formData.id, testCipherName.value || undefined)
    if (res.ok) {
      ElMessage.success(res.message)
    } else {
      ElMessage.error(res.message)
    }
  } catch (e: any) {
    ElMessage.error(e.message || '测试失败')
  } finally {
    testingCipher.value = false
  }
}

interface EnvFormData {
  id?: number
  name: string
  base_url: string
  success_codes: string
  timeout: number
  node_retry_count: number
  node_retry_interval: number
  is_default: boolean
  db_config: { host: string; port: number; user: string; password: string; database: string }
  login_config: {
    enabled: boolean
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
    email: {
      smtp_host: string
      smtp_port: number
      use_ssl: boolean
      from_addr: string
      auth_code: string
      recipients: string   // 表单态：逗号分隔文本；保存时拆为数组
      enable_on_failure: boolean
      enable_on_success: boolean
    }
  }
  common_headers: Record<string, any>
  cipher_config: { key_pairs: CipherKeyPair[] }
}

/** 环境加密密钥对（表单态；名称供接口加密配置引用） */
interface CipherKeyPair {
  name: string
  public_key: string
  private_key: string
}

const formData = reactive<EnvFormData>({
  name: '',
  base_url: '',
  success_codes: '200',
  timeout: 15,
  node_retry_count: 0,
  node_retry_interval: 1,
  is_default: false,
  db_config: { host: '', port: 3306, user: '', password: '', database: '' },
  login_config: {
    enabled: true,
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
    email: {
      smtp_host: '',
      smtp_port: 465,
      use_ssl: true,
      from_addr: '',
      auth_code: '',
      recipients: '',
      enable_on_failure: true,
      enable_on_success: false,
    },
  },
  common_headers: { 'Content-Type': 'application/json' },
  cipher_config: { key_pairs: [] },
})
// 字段级校验（el-form rules）：错误定位到输入框，替代提交时 if 判空 + toast
const formRef = ref<FormInstance>()
const formRules: FormRules = {
  name: [{ required: true, whitespace: true, message: '请输入环境名称', trigger: 'blur' }],
  base_url: [{ required: true, whitespace: true, message: '请输入 Base URL', trigger: 'blur' }],
}

watch(formData, () => { dirty.value = true }, { deep: true })

// 验证码识别开关：开启时三字段展示且必填；关闭即清空地址/字段名
// （后端以「图片地址与字段名均非空」判定启用，清空即真正关闭，无需后端改动）
const captchaEnabled = ref(false)
watch(captchaEnabled, (on) => {
  if (!on) {
    formData.login_config.captcha_url = ''
    formData.login_config.captcha_field = ''
  }
})

async function loadEnv() {
  if (!isEdit.value) return
  const id = Number(route.params.id)
  const env: Environment = await envApi.get(id)
  formData.id = env.id
  formData.name = env.name
  formData.base_url = env.base_url
  formData.success_codes = env.success_codes || '200'
  formData.timeout = env.timeout ?? 15
  formData.node_retry_count = env.node_retry_count ?? 0
  formData.node_retry_interval = env.node_retry_interval ?? 1
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
  // login_config（测试数据来源唯一为数据集，环境不提供变量）
  const lc = env.login_config || {}
  formData.login_config = {
    // 免登录开关：存量数据无此键 = 启用（向后兼容）
    enabled: lc.enabled ?? true,
    login_path: lc.login_path || '/api/home/login/userLogin',
    login_body: lc.login_body || {},
    login_mode: lc.login_mode || 'token',
    login_content_type: lc.login_content_type || 'json',
    token_jsonpath: lc.token_jsonpath || '$.data.token',
    auth_header_name: lc.auth_header_name || 'Authorization',
    auth_header_value_template: lc.auth_header_value_template || '${token}',
    login_check_jsonpath: lc.login_check_jsonpath || '',
    login_check_value: lc.login_check_value || '',
    captcha_url: lc.captcha_url || '',
    captcha_field: lc.captcha_field || '',
    captcha_retry: lc.captcha_retry ?? 3,
  }
  captchaEnabled.value = !!(lc.captcha_url && lc.captcha_field)
  // notify_config（email 子对象历史缺失时给默认态）
  const nc: Record<string, any> = env.notify_config || {}
  const em: Record<string, any> = nc.email || {}
  formData.notify_config = {
    wecom_webhook: nc.wecom_webhook || '',
    enable_on_failure: nc.enable_on_failure ?? true,
    enable_on_success: nc.enable_on_success ?? false,
    email: {
      smtp_host: em.smtp_host || '',
      smtp_port: em.smtp_port ?? 465,
      use_ssl: em.use_ssl ?? true,
      from_addr: em.from_addr || '',
      auth_code: em.auth_code || '',
      recipients: (em.recipients || []).join(', '),
      enable_on_failure: em.enable_on_failure ?? true,
      enable_on_success: em.enable_on_success ?? false,
    },
  }
  formData.common_headers = env.common_headers || { 'Content-Type': 'application/json' }
  // cipher_config（密钥对列表；公私钥 PEM 原样回显）
  const kp = (env.cipher_config || {}).key_pairs || []
  formData.cipher_config = {
    key_pairs: kp.map((p: Record<string, any>) => ({
      name: p.name || '',
      public_key: p.public_key || '',
      private_key: p.private_key || '',
    })),
  }
  savedKeyNames.value = formData.cipher_config.key_pairs.map((p) => p.name).filter(Boolean)
  // watch(formData) 是异步触发的，会在下一个 tick 把 dirty 设为 true；
  // 这里用 nextTick 等待 watch 触发后再重置，避免误判"有未保存改动"
  await nextTick()
  dirty.value = false
}

function onBack() {
  router.push('/envs')
}

// ===== 未保存改动防丢失（浏览器标签模型）：切换标签不弹窗不关签（多开并行编辑），
// dirty 上报全局登记；关闭标签（X/右键/批量）时由 MainLayout 统一弹未保存确认。
// 刷新/关闭浏览器仍由 beforeunload 原生拦截。
watch(dirty, (v) => tabStore.setDirty(route.path, v ? '环境配置' : null), { immediate: true })

const onBeforeUnload = (e: BeforeUnloadEvent) => {
  if (dirty.value) {
    e.preventDefault()
    e.returnValue = ''
  }
}
onMounted(() => window.addEventListener('beforeunload', onBeforeUnload))
onUnmounted(() => window.removeEventListener('beforeunload', onBeforeUnload))

async function onSave() {
  if (!formRef.value) return
  await formRef.value.validate(async (valid) => {
    if (!valid) return
    // trim 关键字段，避免首尾空格（rules 的 whitespace 已拦全空格，此处只清首尾）
    formData.name = formData.name.trim()
    formData.base_url = formData.base_url.trim()
    // 验证码开关开启时，地址与字段名为必填。
    // 跨卡片的条件校验，保留提交时指名 toast（字段级 rules 需跨卡片 prop 绑定，性价比低）
    if (captchaEnabled.value) {
      const lc = formData.login_config
      lc.captcha_url = lc.captcha_url.trim()
      lc.captcha_field = lc.captcha_field.trim()
      if (!lc.captcha_url || !lc.captcha_field) {
        ElMessage.warning('验证码识别已开启：图片地址与字段名均为必填')
        return
      }
    }
    saving.value = true
    try {
      const payload: Partial<Environment> = {
        project_id: currentProjectId.value!,
        name: formData.name,
        base_url: formData.base_url,
        success_codes: formData.success_codes.trim() || '200',
        timeout: formData.timeout,
        node_retry_count: formData.node_retry_count,
        node_retry_interval: formData.node_retry_interval,
        is_default: formData.is_default,
        db_config: formData.db_config,
        login_config: formData.login_config,
        notify_config: {
          wecom_webhook: formData.notify_config.wecom_webhook.trim(),
          enable_on_failure: formData.notify_config.enable_on_failure,
          enable_on_success: formData.notify_config.enable_on_success,
          email: {
            smtp_host: formData.notify_config.email.smtp_host.trim(),
            smtp_port: formData.notify_config.email.smtp_port,
            use_ssl: formData.notify_config.email.use_ssl,
            from_addr: formData.notify_config.email.from_addr.trim(),
            auth_code: formData.notify_config.email.auth_code,
            // 表单逗号/空格分隔文本 → 数组落库
            recipients: formData.notify_config.email.recipients
              .split(/[,，;；\s]+/).map((s) => s.trim()).filter(Boolean),
            enable_on_failure: formData.notify_config.email.enable_on_failure,
            enable_on_success: formData.notify_config.email.enable_on_success,
          },
        },
        common_headers: formData.common_headers,
        cipher_config: {
          key_pairs: formData.cipher_config.key_pairs
            .map((p) => ({ name: p.name.trim(), public_key: p.public_key.trim(), private_key: p.private_key.trim() }))
            .filter((p) => p.name || p.public_key || p.private_key),
        },
      }
      if (isEdit.value) {
        await envApi.update(formData.id!, payload)
        pulseSaved()
      } else {
        await envApi.create(payload)
        ElMessage.success('已创建')
        router.push('/envs')
      }
      dirty.value = false
      // 密钥名下拉（测试加解密选择器）跟随最新保存值
      savedKeyNames.value = (payload.cipher_config?.key_pairs || []).map((p: CipherKeyPair) => p.name).filter(Boolean)
      // 重新加载环境列表（更新顶部下拉）
      store.loadEnvironments()
    } catch (e: any) {
      ElMessage.error(e.message || '保存失败')
    } finally {
      saving.value = false
    }
  })
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
  initialLoad()
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
/* 保存按钮成功对勾：墨绿主按钮底上成功绿无对比度，随按钮文字色（白）走；
   loading/禁用态文字色变化也一并继承，始终可读 */
.save-check {
  margin-left: 4px;
  color: inherit;
}
.edit-body {
  flex: 1;
  overflow: auto;
  padding: 16px 20px;
}
.card-section {
  background: var(--app-card-solid);
  border-radius: var(--app-radius-lg);
  padding: 18px 22px;
  margin-bottom: 14px;
  box-shadow: var(--app-shadow-sm);
}
/* 分区头：标题 + 右侧动作（测试连接/测试登录） */
.section-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 14px;
}
.section-head .title {
  font-size: 14px;
  font-weight: 600;
  color: var(--app-text);
}
.section-head .sub {
  font-size: 12px;
  color: var(--app-text-muted);
}
.section-head .grow {
  flex: 1;
}
/* 统一 4 列网格：输入框宽度只由列宽决定，行与行严格对齐 */
.form-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 0 16px;
}
.form-grid .el-form-item {
  margin-bottom: 14px;
  min-width: 0;
}
.form-grid .el-input-number {
  width: 100%;
}
.col-2 {
  grid-column: span 2;
}
.span-all {
  grid-column: 1 / -1;
}
/* 标签旁 ? 提示（长说明全部收纳于此，不再铺文字段） */
.lbl-help {
  font-size: 12px;
  color: var(--app-text-faint);
  cursor: help;
  margin-left: 2px;
  vertical-align: -1px;
}
/* 卡内分组条 */
.group-title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 18px 0 12px;
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
/* ===== 加密配置：密钥对块 ===== */
.cipher-name-select {
  width: 130px;
  margin-right: 8px;
}
.cipher-empty {
  font-size: 12px;
  color: var(--app-text-muted);
  padding: 6px 0 12px;
}
.key-pair-item {
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius, 8px);
  padding: 10px 14px 0;
  margin-bottom: 10px;
}
.pair-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}
.pair-head .grow {
  flex: 1;
}
.pair-name-input {
  width: 240px;
}
.pair-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0 16px;
}
.pair-grid .el-form-item {
  min-width: 0;
}
@media (max-width: 1100px) {
  .pair-grid {
    grid-template-columns: 1fr;
  }
}
@media (max-width: 1100px) {
  .form-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>

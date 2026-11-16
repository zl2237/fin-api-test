<template>
  <div class="callback-verify">
    <el-card shadow="never" class="main-card">
      <template #header>
        <div class="card-head">
          <span class="title">回调验签工具</span>
          <span class="sub">粘贴完整回调报文（含 sign/signType），环境公钥 RSA2 验签</span>
        </div>
      </template>

      <el-form label-position="top" @submit.prevent>
        <div class="ctrl-row">
          <el-form-item label="环境（密钥库来源）">
            <el-select v-model="envId" placeholder="选择环境" style="width: 240px" @change="onEnvChange">
              <el-option v-for="e in store.environments" :key="e.id" :label="e.name" :value="e.id" />
            </el-select>
          </el-form-item>
          <el-form-item>
            <template #label>
              密钥对名称
              <el-tooltip content="验签用公钥所在密钥对的名称；留空默认第一对（与「环境编辑 → 加密配置」一致）" placement="top">
                <el-icon class="lbl-help"><QuestionFilled /></el-icon>
              </el-tooltip>
            </template>
            <el-select v-model="keyName" placeholder="第一对" clearable style="width: 200px">
              <el-option v-for="n in keyNames" :key="n" :label="n" :value="n" />
            </el-select>
          </el-form-item>
          <div class="grow" />
          <el-button type="primary" :loading="verifying" :disabled="!envId" @click="onVerify">验签</el-button>
        </div>
        <el-form-item>
          <template #label>
            回调报文（完整 JSON，含 sign / signType）
            <el-tooltip content="从对方推送请求体原样复制；数字/布尔/null 类型会参与规范化，请勿加引号转字符串" placement="top">
              <el-icon class="lbl-help"><QuestionFilled /></el-icon>
            </el-tooltip>
          </template>
          <el-input
            v-model="payloadText"
            type="textarea"
            :rows="12"
            class="mono-input"
            spellcheck="false"
            placeholder='{
  "batchNo": "CUS-B-1000",
  "items": [ { ... } ],
  "sign": "Base64 签名",
  "signType": "RSA2"
}'
          />
        </el-form-item>
      </el-form>

      <!-- 结果区 -->
      <template v-if="result">
        <el-alert
          :type="result.passed ? 'success' : 'error'"
          :closable="false"
          show-icon
          class="result-alert"
          :title="result.passed ? '验签通过：签名与重建原串匹配，报文未被篡改' : '验签不通过'"
          :description="result.passed ? '' : result.reason"
        />
        <div class="result-section">
          <div class="section-title">
            重建待签原串（顶层剔除 sign/signType，键字典序 k=v&amp;k=v 拼接）
            <CopyBtn v-if="result.canonical_string" :value="result.canonical_string" />
          </div>
          <pre class="mono-pre">{{ result.canonical_string || '（无法重建）' }}</pre>
          <p class="hint">
            排查思路：与对方调试报文逐字段比对重建原串；类型敏感——数字加了引号、null 写成 "null" 都会改变原串。
          </p>
        </div>
        <div v-if="result.items_json" class="result-section">
          <div class="section-title">
            items 规范化 JSON（Fastjson2 紧凑格式：递归字典序键、数组保序、嵌套 null 保持）
            <CopyBtn :value="result.items_json" />
          </div>
          <pre class="mono-pre">{{ result.items_json }}</pre>
        </div>
      </template>
      <EmptyState v-else-if="!payloadText" description="粘贴回调报文后点「验签」" :image-size="70" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { QuestionFilled } from '@element-plus/icons-vue'
import { envApi } from '@/api'
import EmptyState from '@/components/EmptyState.vue'
import CopyBtn from '@/components/CopyBtn.vue'
import { CALLBACK_PREFILL_KEY } from '@/constants/tools'
import { useAppStore } from '@/stores'

const store = useAppStore()

// 报告页「去验签」交接：sessionStorage 带入响应体报文（读后即焚）
onMounted(() => {
  const prefill = sessionStorage.getItem(CALLBACK_PREFILL_KEY)
  if (prefill) {
    sessionStorage.removeItem(CALLBACK_PREFILL_KEY)
    try {
      const obj = JSON.parse(prefill)
      if (obj && typeof obj === 'object') {
        payloadText.value = JSON.stringify(obj, null, 2)
        ElMessage.success('已带入报告响应体，选择环境后点「验签」')
      }
    } catch { /* 交接内容损坏则忽略，手工粘贴 */ }
  }
})

const envId = ref<number | null>(null)
const keyName = ref('')
const payloadText = ref('')
const verifying = ref(false)
const result = ref<{ passed: boolean; canonical_string: string; items_json?: string | null; reason: string } | null>(null)

// 选中环境密钥库的名称列表（密钥材料不入前端，验签在后端做）
const keyNames = computed(() => {
  const env = store.environments.find((e) => e.id === envId.value)
  const pairs = (env?.cipher_config as Record<string, any> | null | undefined)?.key_pairs || []
  return pairs.map((p: Record<string, any>) => p.name).filter(Boolean)
})

function onEnvChange() {
  // 环境切换后原名称大概率失效，清空回落「第一对」
  keyName.value = ''
  result.value = null
}

async function onVerify() {
  if (!envId.value) return
  const text = payloadText.value.trim()
  if (!text) {
    ElMessage.warning('请粘贴回调报文 JSON')
    return
  }
  let payload: Record<string, any>
  try {
    payload = JSON.parse(text)
  } catch (e: any) {
    ElMessage.error(`报文 JSON 解析失败：${e.message}`)
    return
  }
  if (typeof payload !== 'object' || payload === null || Array.isArray(payload)) {
    ElMessage.error('回调报文必须是 JSON 对象（{...}）')
    return
  }
  verifying.value = true
  try {
    result.value = await envApi.verifyCallback(envId.value, {
      key_name: keyName.value || '',
      payload,
    })
  } catch (e: any) {
    ElMessage.error(e.message || '验签请求失败')
  } finally {
    verifying.value = false
  }
}
</script>

<style scoped>
.callback-verify {
  padding: 16px;
  height: 100%;
  overflow: auto;
  background: var(--app-bg);
}
.main-card {
  max-width: 1100px;
  margin: 0 auto;
}
.card-head {
  display: flex;
  align-items: baseline;
  gap: 10px;
  flex-wrap: wrap;
}
.card-head .title {
  font-size: 15px;
  font-weight: 600;
  color: var(--app-text);
}
.card-head .sub {
  font-size: 12px;
  color: var(--app-text-muted);
}
.ctrl-row {
  display: flex;
  align-items: flex-end;
  gap: 16px;
  flex-wrap: wrap;
}
.ctrl-row .grow {
  flex: 1;
}
.lbl-help {
  font-size: 12px;
  color: var(--app-text-faint);
  cursor: help;
  margin-left: 2px;
  vertical-align: -1px;
}
.mono-input :deep(.el-textarea__inner) {
  font-family: var(--app-font-mono, Consolas, monospace);
  font-size: 12px;
  line-height: 1.6;
}
.result-alert {
  margin-top: 6px;
}
.result-section {
  margin-top: 14px;
}
.section-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--app-text);
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}
.mono-pre {
  background: var(--app-bg);
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius, 6px);
  padding: 10px 12px;
  font-size: 12px;
  font-family: var(--app-font-mono, Consolas, monospace);
  max-height: 200px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-all;
  margin: 0;
}
.hint {
  margin: 6px 0 0;
  font-size: 12px;
  color: var(--app-text-muted);
  line-height: 1.6;
}
</style>

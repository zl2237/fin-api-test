<template>
  <!-- 上手指南抽屉：从 Home 提取的自包含组件（defineModel 控制显隐；常量/首登逻辑/跳转全部内聚） -->
  <el-drawer v-model="visible" title="上手指南" size="480px" :close-on-click-modal="false">
    <div class="guide-body">
      <h4 class="guide-section">六步跑通第一个测试</h4>
      <ol class="guide-steps">
        <li v-for="(s, i) in guideSteps" :key="s.title">
          <span class="g-num" aria-hidden="true">{{ i + 1 }}</span>
          <div class="g-text">
            <b>{{ s.title }}</b>
            <p>{{ s.desc }}</p>
          </div>
          <el-button text type="primary" size="small" @click="router.push(s.to); visible = false">{{ s.go }}</el-button>
        </li>
      </ol>

      <h4 class="guide-section">核心能力</h4>
      <div class="guide-caps">
        <!-- 可跳转项用 button（键盘可达）；纯说明项用 div -->
        <template v-for="cap in guideCaps" :key="cap.title">
          <button
            v-if="cap.tab"
            type="button"
            class="cap-item clickable"
            @click="store.openCoreCapability(cap.tab)"
          >
            <b>{{ cap.title }}</b>
            <p>{{ cap.desc }}</p>
          </button>
          <div v-else class="cap-item">
            <b>{{ cap.title }}</b>
            <p>{{ cap.desc }}</p>
          </div>
        </template>
      </div>
    </div>
  </el-drawer>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAppStore } from '@/stores'

/** 显隐由父级持有（v-model），首登自动展示逻辑在组件内部完成 */
const visible = defineModel<boolean>({ default: false })

const router = useRouter()
const store = useAppStore()

// ===== 首登自动展示一次（localStorage 记忆） =====
const GUIDE_SEEN_KEY = 'fin_home_guide_seen'
onMounted(() => {
  if (!localStorage.getItem(GUIDE_SEEN_KEY)) {
    visible.value = true
    localStorage.setItem(GUIDE_SEEN_KEY, '1')
  }
})

const guideSteps = [
  { title: '建一个项目', desc: '项目把一个系统的接口和用例装在一起，右上角随时切换', go: '去创建', to: '/projects' },
  { title: '配置环境', desc: '被测系统地址、登录账号、数据库连接，可即时测试连通性', go: '去配置', to: '/envs' },
  { title: '录入接口', desc: '手动新建或粘贴 cURL 自动识别，参数像填表格一样配置', go: '去录入', to: '/apis' },
  { title: '编排用例', desc: '画布上把接口连成流程，双击节点添加断言', go: '去编排', to: '/cases' },
  // 数据驱动为主流程的可选第六步：从用例生成数据集，用例行内「数据」绑定
  { title: '绑定数据集（可选）', desc: '同一用例跑多组参数：从用例生成数据集，用例行内「数据」绑定，一行数据执行一次', go: '去看看', to: '/datasets' },
  { title: '执行看报告', desc: '选环境点执行，每一步请求与校验结果全留档', go: '去看', to: '/executions' },
]

const guideCaps = [
  { title: '数据驱动测试', desc: '用例生成数据集，改单元格即参数化：一行一执行，支持 Excel 导入导出与跨数据集覆盖合并', tab: 'dataset' as const },
  { title: '数据自动生成', desc: '随机手机号、日期加减、唯一单号，写一次 ${uuid()} 到处复用', tab: 'expression' as const },
  { title: '17 种结果校验', desc: 'JSONPath、状态码、DB 交叉校验，支持失败重试', tab: 'assertion' as const },
  { title: '批量导入接口', desc: 'cURL 粘贴即用，HAR 抓包文件、Swagger 文档批量导入', tab: null },
  { title: '数据库直查对账', desc: '测试时顺手执行 SQL 对账，不用开数据库客户端', tab: null },
]
</script>

<style scoped>
.guide-body { display: flex; flex-direction: column; gap: 6px; }
.guide-section { font-size: 14px; font-weight: 600; color: var(--app-text); margin: 8px 0 6px; }
.guide-steps { list-style: none; margin: 0; padding: 0; }
.guide-steps li {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 10px 0;
  border-bottom: 1px solid var(--app-border);
}
.guide-steps li:last-child { border-bottom: none; }
.g-num {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: color-mix(in srgb, var(--app-primary) 12%, transparent);
  color: var(--app-primary);
  font-size: 12px;
  font-weight: 700;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  margin-top: 1px;
}
.g-text { flex: 1; min-width: 0; }
.g-text b { font-size: 13px; font-weight: 600; color: var(--app-text); display: block; margin-bottom: 2px; }
.g-text p { font-size: 12px; line-height: 1.6; color: var(--app-text-muted); margin: 0; }
.guide-caps { display: flex; flex-direction: column; gap: 8px; }
.cap-item {
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius-sm);
  padding: 10px 12px;
  font: inherit;
  color: inherit;
  text-align: left;
  width: 100%;
  background: transparent;
}
.cap-item.clickable { cursor: pointer; transition: border-color 0.15s; }
.cap-item.clickable:hover { border-color: color-mix(in srgb, var(--app-primary) 45%, var(--app-border)); }
.cap-item.clickable:focus-visible { outline: 2px solid var(--app-primary); outline-offset: -2px; }
.cap-item b { font-size: 13px; font-weight: 600; color: var(--app-text); display: block; margin-bottom: 3px; }
.cap-item p { font-size: 12px; line-height: 1.6; color: var(--app-text-muted); margin: 0; }
</style>

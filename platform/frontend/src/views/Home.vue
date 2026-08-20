<template>
  <div class="home-page">
    <!-- ===== 项目横幅：DAG 节点主题插画 + 定位语 + 行动按钮 ===== -->
    <section class="hero">
      <div class="hero-text">
        <h1 class="hero-title">Fin API Test Platform</h1>
        <p class="hero-slogan">把接口测试从「一段代码」变成「一张看得懂的流程图」</p>
        <p class="hero-sub">
          像拼积木一样组合接口：点一点配好请求，拖一拖连出先后顺序，一键运行、自动出报告。
          测通了留档复用，测挂了三秒定位到哪一步、哪个字段出了问题。
        </p>
        <div class="hero-actions">
          <el-button type="primary" size="large" @click="router.push('/apis')">去管理接口</el-button>
          <el-button size="large" @click="router.push('/cases')">去编排用例</el-button>
        </div>
      </div>
      <!-- 纯 SVG 插画：三节点 DAG + 断言对勾，与 favicon/banner 同一视觉语言，暗色自动适配 -->
      <svg class="hero-art" viewBox="0 0 260 190" fill="none" aria-hidden="true">
        <defs>
          <marker id="home-arrow" viewBox="0 0 10 10" refX="8.5" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M0,0 L10,5 L0,10 z" class="hero-edge-head" />
          </marker>
        </defs>
        <!-- 连线 -->
        <path d="M62 55 C 92 55, 88 95, 118 95" class="hero-edge" marker-end="url(#home-arrow)" />
        <path d="M62 135 C 92 135, 88 95, 118 95" class="hero-edge" marker-end="url(#home-arrow)" />
        <path d="M178 95 C 205 95, 200 55, 228 55" class="hero-edge" marker-end="url(#home-arrow)" />
        <!-- 节点1：登录 -->
        <g>
          <rect x="10" y="32" width="52" height="46" rx="10" class="hero-node" />
          <text x="36" y="59" text-anchor="middle" class="hero-node-text">登录</text>
        </g>
        <!-- 节点2：下单 -->
        <g>
          <rect x="10" y="112" width="52" height="46" rx="10" class="hero-node" />
          <text x="36" y="139" text-anchor="middle" class="hero-node-text">下单</text>
        </g>
        <!-- 节点3：查询订单 -->
        <g>
          <rect x="118" y="72" width="60" height="46" rx="10" class="hero-node hero-node-main" />
          <text x="148" y="99" text-anchor="middle" class="hero-node-text">查订单</text>
        </g>
        <!-- 结果徽章：断言通过 -->
        <g>
          <rect x="228" y="32" width="24" height="46" rx="8" class="hero-badge" />
          <path d="M236 51 l4.5 5.5 l7.5 -9" class="hero-check" />
        </g>
      </svg>
    </section>

    <!-- ===== 这是什么：三张白话卡片 ===== -->
    <section class="about">
      <h2 class="section-title">这个平台帮你做什么</h2>
      <div class="about-grid">
        <div class="about-card">
          <svg viewBox="0 0 48 48" class="about-icon" aria-hidden="true">
            <rect x="6" y="8" width="36" height="30" rx="6" class="svg-stroke" />
            <path d="M14 20 h20 M14 27 h12" class="svg-stroke svg-thin" />
            <circle cx="32" cy="27" r="5" class="svg-fill-soft" />
            <path d="M29.5 27 l1.8 2 l3 -3.6" class="svg-check" />
          </svg>
          <h3>不用写代码就能测接口</h3>
          <p>每个接口要传什么参数、返回值对不对，都在表格里点选填写。常用数据（随机数、日期、单号）系统帮你生成。</p>
        </div>
        <div class="about-card">
          <svg viewBox="0 0 48 48" class="about-icon" aria-hidden="true">
            <rect x="5" y="6" width="16" height="13" rx="5" class="svg-stroke" />
            <rect x="5" y="29" width="16" height="13" rx="5" class="svg-stroke" />
            <rect x="30" y="17" width="13" height="13" rx="5" class="svg-stroke svg-accent" />
            <path d="M21 12.5 C 26 12.5, 24 23.5, 30 23.5" class="svg-edge" />
            <path d="M21 35.5 C 26 35.5, 24 23.5, 30 23.5" class="svg-edge" />
          </svg>
          <h3>多个接口连成一条业务链</h3>
          <p>真实的业务不止一步：登录 → 下单 → 查订单。在画布上把接口连起来，上一步的结果（订单号、token）下一步直接引用。</p>
        </div>
        <div class="about-card">
          <svg viewBox="0 0 48 48" class="about-icon" aria-hidden="true">
            <path d="M8 34 L18 22 L26 28 L40 12" class="svg-stroke" />
            <path d="M40 12 h-9 M40 12 v9" class="svg-stroke svg-thin" />
            <circle cx="18" cy="22" r="3" class="svg-fill" />
            <circle cx="26" cy="28" r="3" class="svg-fill" />
          </svg>
          <h3>跑完就有结果报告</h3>
          <p>每一步的请求、返回、校验结果全部留档。哪一步红了一眼看到，耗时长不长一目了然，还能导出报告发给同事。</p>
        </div>
      </div>
    </section>

    <!-- ===== 五步上手：白话流程 + 直达入口 ===== -->
    <section class="steps">
      <h2 class="section-title">五步跑通你的第一个测试</h2>
      <div class="steps-grid">
        <div v-for="(s, i) in steps" :key="s.title" class="step-card">
          <div class="step-head">
            <span class="step-num">{{ i + 1 }}</span>
            <h3>{{ s.title }}</h3>
          </div>
          <p class="step-desc">{{ s.desc }}</p>
          <el-button text type="primary" class="step-go" @click="router.push(s.to)">
            {{ s.go }}<el-icon class="step-go-icon"><ArrowRight /></el-icon>
          </el-button>
        </div>
      </div>
    </section>

    <!-- ===== 功能导航：核心四区 ===== -->
    <section class="nav">
      <h2 class="section-title">常用的四个地方</h2>
      <div class="nav-grid">
        <div v-for="n in navs" :key="n.title" class="nav-card" @click="router.push(n.to)">
          <el-icon class="nav-icon"><component :is="n.icon" /></el-icon>
          <div class="nav-body">
            <h3>{{ n.title }}<el-icon class="nav-arrow"><ArrowRight /></el-icon></h3>
            <p>{{ n.desc }}</p>
          </div>
        </div>
      </div>
    </section>

    <!-- ===== 核心能力（承接原使用说明弹窗；可点卡片打开详情） ===== -->
    <section class="caps">
      <h2 class="section-title">还有这些好用的能力<span class="section-sub">点击带箭头的卡片看详细用法</span></h2>
      <div class="caps-grid">
        <div class="cap-card" @click="store.openCoreCapability('expression')">
          <el-icon class="cap-icon"><DataLine /></el-icon>
          <div class="cap-body">
            <h3>数据自动生成<el-icon class="cap-arrow"><ArrowRight /></el-icon></h3>
            <p>随机手机号、日期加减、唯一单号……写一次 <code>${uuid()}</code> 到处复用，不用再手编测试数据</p>
          </div>
        </div>
        <div class="cap-card" @click="store.openCoreCapability('assertion')">
          <el-icon class="cap-icon"><Checked /></el-icon>
          <div class="cap-body">
            <h3>17 种结果校验<el-icon class="cap-arrow"><ArrowRight /></el-icon></h3>
            <p>「金额应该等于 100」「数据库里已经有这条记录」这类检查点，勾选规则即可，支持失败重试</p>
          </div>
        </div>
        <div class="cap-card">
          <el-icon class="cap-icon"><Upload /></el-icon>
          <div class="cap-body">
            <h3>接口一键搬进来</h3>
            <p>从浏览器复制一条 cURL 命令粘贴即用；也支持上传抓包文件（HAR）或粘贴 Swagger 文档批量导入</p>
          </div>
        </div>
        <div class="cap-card">
          <el-icon class="cap-icon"><Connection /></el-icon>
          <div class="cap-body">
            <h3>数据库直接查</h3>
            <p>测试时顺手查库对账：接口说下单成功？SQL 一查便知，不用再开数据库客户端</p>
          </div>
        </div>
      </div>
    </section>

    <!-- ===== 快捷键条 ===== -->
    <section class="kbd-bar">
      <span class="kbd-item"><kbd>Ctrl</kbd>/<kbd>⌘</kbd> + <kbd>K</kbd> 任意页面一秒直达</span>
      <span class="kbd-item"><kbd>Ctrl</kbd> + <kbd>Enter</kbd> 在用例列表快速执行选中的用例</span>
    </section>
  </div>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'
import { ArrowRight, Connection, Upload, DataLine, Checked, Folder, Share, Histogram, Setting } from '@element-plus/icons-vue'
import { useAppStore } from '@/stores'

const router = useRouter()
const store = useAppStore()

// 五步流程：白话文案（承接原「使用说明」弹窗并去术语化），每步带直达入口
const steps = [
  {
    title: '建一个项目',
    desc: '项目就像一个文件夹，把某个系统的接口和用例装在一起。第一次使用先建一个，之后在右上角随时切换。',
    go: '去建项目', to: '/projects',
  },
  {
    title: '填好测试地址',
    desc: '告诉平台被测系统在哪：网址、登录账号、数据库连接。填完点「测试连接」马上验证填得对不对。',
    go: '去配环境', to: '/envs',
  },
  {
    title: '把接口录进来',
    desc: '手动新建，或直接粘贴一条 cURL 命令自动识别。每个接口的参数像填表格一样配好就行。',
    go: '去录接口', to: '/apis',
  },
  {
    title: '拼出测试流程',
    desc: '在画布上把接口连成一条线：先登录、再下单、后查单。想检查什么结果，双击节点加一条校验。',
    go: '去拼流程', to: '/cases',
  },
  {
    title: '一键运行看报告',
    desc: '选好环境点「执行」，每一步做什么、返回什么、哪步失败全部展示。失败会直接标红告诉你原因。',
    go: '看执行记录', to: '/executions',
  },
]

// 核心四区导航（次要入口：字典/文件/用户/日志见侧边栏）
const navs = [
  { title: '接口管理', desc: '录入和维护要测的接口、参数', to: '/apis', icon: Folder },
  { title: '用例编排', desc: '把接口连成流程、加校验规则', to: '/cases', icon: Share },
  { title: '执行记录', desc: '历次运行结果与报告', to: '/executions', icon: Histogram },
  { title: '环境配置', desc: '测试地址、账号、数据库', to: '/envs', icon: Setting },
]
</script>

<style scoped>
.home-page {
  max-width: 1080px;
  margin: 0 auto;
  padding: 20px 24px 40px;
  display: flex;
  flex-direction: column;
  gap: 36px;
}

/* ===== 横幅 ===== */
.hero {
  display: flex;
  align-items: center;
  gap: 32px;
  padding: 36px 40px;
  border-radius: var(--app-radius-lg);
  background: linear-gradient(135deg, color-mix(in srgb, var(--app-primary) 10%, var(--app-card-solid)) 0%, var(--app-card-solid) 60%);
  border: 1px solid var(--app-border);
  box-shadow: var(--app-shadow-sm);
  overflow: hidden;
  position: relative;
}
.hero-text { flex: 1.2; min-width: 0; }
.hero-title {
  font-size: 26px;
  font-weight: 700;
  color: var(--app-text);
  margin: 0 0 6px;
  letter-spacing: 0.3px;
}
.hero-slogan {
  font-size: 16px;
  font-weight: 600;
  color: var(--app-primary);
  margin: 0 0 10px;
}
.hero-sub {
  font-size: 13.5px;
  line-height: 1.8;
  color: var(--app-text-muted);
  margin: 0 0 18px;
  max-width: 560px;
}
.hero-actions { display: flex; gap: 12px; }

/* 横幅 SVG 插画 */
.hero-art {
  flex: 0 0 300px;
  width: 300px;
  height: auto;
}
.hero-node {
  fill: color-mix(in srgb, var(--app-primary) 8%, var(--app-card-solid));
  stroke: var(--app-primary);
  stroke-width: 1.5;
}
.hero-node-main {
  fill: color-mix(in srgb, var(--app-primary) 16%, var(--app-card-solid));
}
.hero-node-text {
  font-size: 11px;
  fill: var(--app-text);
}
.hero-edge {
  stroke: var(--app-primary);
  stroke-width: 1.6;
  stroke-dasharray: 5 4;
  opacity: 0.65;
}
.hero-edge-head { fill: var(--app-primary); }
.hero-badge {
  fill: var(--app-success);
  opacity: 0.18;
}
.hero-check {
  stroke: var(--app-success);
  stroke-width: 2.4;
  stroke-linecap: round;
  stroke-linejoin: round;
  fill: none;
}

/* ===== 通用节标题 ===== */
.section-title {
  font-size: 17px;
  font-weight: 700;
  color: var(--app-text);
  margin: 0 0 16px;
  display: flex;
  align-items: baseline;
  gap: 10px;
}
.section-sub {
  font-size: 12px;
  font-weight: 400;
  color: var(--app-text-muted);
}

/* ===== 这是什么 ===== */
.about-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 14px;
}
.about-card {
  background: var(--app-card-solid);
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius);
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  transition: border-color 0.15s, box-shadow 0.15s;
}
.about-card:hover {
  border-color: color-mix(in srgb, var(--app-primary) 45%, var(--app-border));
  box-shadow: var(--app-shadow);
}
.about-icon {
  width: 44px;
  height: 44px;
  margin-bottom: 4px;
}
.about-card h3 {
  font-size: 14.5px;
  font-weight: 600;
  color: var(--app-text);
  margin: 0;
}
.about-card p {
  font-size: 12.5px;
  line-height: 1.7;
  color: var(--app-text-muted);
  margin: 0;
}

/* 共用 SVG 线条色（暗色自动跟随变量） */
.svg-stroke { stroke: var(--app-primary); stroke-width: 2.4; fill: none; stroke-linecap: round; stroke-linejoin: round; }
.svg-thin { stroke-width: 1.8; opacity: 0.55; }
.svg-accent { stroke: var(--app-success); }
.svg-edge { stroke: var(--app-primary); stroke-width: 1.8; fill: none; stroke-dasharray: 4 3; opacity: 0.65; }
.svg-fill { fill: var(--app-primary); }
.svg-fill-soft { fill: color-mix(in srgb, var(--app-success) 18%, transparent); }
.svg-check { stroke: var(--app-success); stroke-width: 2.6; fill: none; stroke-linecap: round; stroke-linejoin: round; }

/* ===== 五步 ===== */
.steps-grid {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 12px;
}
.step-card {
  background: var(--app-card-solid);
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius);
  padding: 16px 14px;
  display: flex;
  flex-direction: column;
  position: relative;
  transition: border-color 0.15s, box-shadow 0.15s;
}
.step-card:hover {
  border-color: color-mix(in srgb, var(--app-primary) 45%, var(--app-border));
  box-shadow: var(--app-shadow);
}
/* 步骤间衔接箭头（最后一步不加） */
.step-card:not(:last-child)::after {
  content: '›';
  position: absolute;
  right: -11px;
  top: 50%;
  transform: translateY(-50%);
  font-size: 18px;
  color: var(--app-text-muted);
  z-index: 1;
}
.step-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.step-num {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: color-mix(in srgb, var(--app-primary) 12%, transparent);
  color: var(--app-primary);
  font-size: 13px;
  font-weight: 700;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.step-card h3 {
  font-size: 13.5px;
  font-weight: 600;
  color: var(--app-text);
  margin: 0;
}
.step-desc {
  font-size: 12px;
  line-height: 1.7;
  color: var(--app-text-muted);
  margin: 0;
  flex: 1;
}
.step-go { padding: 4px 0; align-self: flex-start; }
.step-go-icon { margin-left: 2px; }

/* ===== 功能导航 ===== */
.nav-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 14px;
}
.nav-card {
  background: var(--app-card-solid);
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius);
  padding: 20px;
  display: flex;
  align-items: flex-start;
  gap: 14px;
  cursor: pointer;
  transition: border-color 0.15s, box-shadow 0.15s, transform 0.15s;
}
.nav-card:hover {
  border-color: color-mix(in srgb, var(--app-primary) 45%, var(--app-border));
  box-shadow: var(--app-shadow);
  transform: translateY(-2px);
}
.nav-icon {
  font-size: 26px;
  color: var(--app-primary);
  flex-shrink: 0;
  margin-top: 2px;
}
.nav-body { min-width: 0; flex: 1; }
.nav-card h3 {
  font-size: 14.5px;
  font-weight: 600;
  color: var(--app-text);
  margin: 0 0 6px;
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.nav-arrow {
  font-size: 14px;
  color: var(--app-text-muted);
  opacity: 0;
  transition: opacity 0.15s, transform 0.15s;
}
.nav-card:hover .nav-arrow { opacity: 1; transform: translateX(2px); }
.nav-card p {
  font-size: 12.5px;
  color: var(--app-text-muted);
  margin: 0;
  line-height: 1.6;
}

/* ===== 能力卡 ===== */
.caps-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 14px;
}
.cap-card {
  background: var(--app-card-solid);
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius);
  padding: 18px 20px;
  display: flex;
  align-items: flex-start;
  gap: 14px;
  transition: border-color 0.15s, box-shadow 0.15s;
}
.cap-card:hover {
  border-color: color-mix(in srgb, var(--app-primary) 45%, var(--app-border));
  box-shadow: var(--app-shadow);
}
.cap-icon {
  font-size: 24px;
  color: var(--app-primary);
  flex-shrink: 0;
  margin-top: 2px;
}
.cap-body { min-width: 0; flex: 1; }
.cap-card h3 {
  font-size: 14px;
  font-weight: 600;
  color: var(--app-text);
  margin: 0 0 6px;
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.cap-arrow { font-size: 14px; color: var(--app-primary); }
.cap-card p {
  font-size: 12.5px;
  line-height: 1.7;
  color: var(--app-text-muted);
  margin: 0;
}
.cap-card code {
  font-family: var(--app-font-mono);
  background: color-mix(in srgb, var(--app-primary) 8%, transparent);
  border-radius: 4px;
  padding: 1px 5px;
  font-size: 11.5px;
}

/* ===== 快捷键条 ===== */
.kbd-bar {
  display: flex;
  justify-content: center;
  gap: 28px;
  flex-wrap: wrap;
  padding: 14px 20px;
  background: var(--app-card-solid);
  border: 1px dashed var(--app-border);
  border-radius: var(--app-radius);
}
.kbd-item { font-size: 12.5px; color: var(--app-text-muted); }
kbd {
  font-family: var(--app-font-mono);
  font-size: 11px;
  background: var(--app-bg);
  border: 1px solid var(--app-border);
  border-bottom-width: 2px;
  border-radius: 5px;
  padding: 1px 6px;
  color: var(--app-text);
}

/* ===== 窄屏自适应 ===== */
@media (max-width: 960px) {
  .hero { flex-direction: column; text-align: center; }
  .hero-actions { justify-content: center; }
  .hero-sub { margin-left: auto; margin-right: auto; }
  .about-grid { grid-template-columns: 1fr; }
  .steps-grid { grid-template-columns: repeat(2, 1fr); }
  .step-card:not(:last-child)::after { display: none; }
  .nav-grid { grid-template-columns: repeat(2, 1fr); }
  .caps-grid { grid-template-columns: 1fr; }
}
@media (max-width: 600px) {
  .steps-grid, .nav-grid { grid-template-columns: 1fr; }
  .hero-art { flex-basis: auto; width: 240px; }
}
</style>

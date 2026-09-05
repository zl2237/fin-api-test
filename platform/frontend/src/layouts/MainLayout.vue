<template>
  <el-container class="layout">
    <el-aside class="sidebar" :width="collapsed ? '64px' : '220px'">
      <!-- 侧边栏品牌渐变背景装饰层 -->
      <div class="sidebar-bg-deco" aria-hidden="true">
        <svg viewBox="0 0 220 800" fill="none" xmlns="http://www.w3.org/2000/svg" preserveAspectRatio="xMidYMid slice">
          <!-- 顶部光晕 -->
          <ellipse cx="110" cy="60" rx="140" ry="80" fill="rgba(255,255,255,0.06)" />
          <!-- 底部 DAG 节点装饰 -->
          <path d="M60 620 L110 680 M110 680 L170 640 M110 680 L80 740 M110 680 L160 730" stroke="rgba(255,255,255,0.12)" stroke-width="1.5" stroke-linecap="round" stroke-dasharray="4 6" />
          <circle cx="60" cy="620" r="5" fill="rgba(255,255,255,0.25)" />
          <circle cx="110" cy="680" r="7" fill="rgba(255,255,255,0.3)" />
          <circle cx="170" cy="640" r="4" fill="rgba(255,255,255,0.2)" />
          <circle cx="80" cy="740" r="3.5" fill="rgba(255,255,255,0.2)" />
          <circle cx="160" cy="730" r="5" fill="rgba(255,255,255,0.25)" />
        </svg>
      </div>
      <!-- 品牌区可点击回首页（首页即工作台：最近执行+统计+快速执行） -->
      <el-tooltip content="回到首页" placement="top" popper-class="app-tip">
        <router-link to="/home" class="brand brand-link" aria-label="回到首页">
        <span class="brand-logo" aria-hidden="true">
          <svg viewBox="0 0 32 32" width="28" height="28" fill="none" xmlns="http://www.w3.org/2000/svg">
            <defs>
              <marker id="brandArrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="4" markerHeight="4" orient="auto">
                <polygon points="0 0, 10 5, 0 10" fill="#fff"/>
              </marker>
            </defs>
            <!-- 产品图标：DAG 节点汇聚 → 断言对勾（与 favicon 同构的白色版） -->
            <rect width="32" height="32" rx="2" fill="rgba(255,255,255,0.16)" />
            <g stroke="#fff" stroke-width="1" fill="none" stroke-linecap="round">
              <path d="M7.4 9 L11 12" marker-end="url(#brandArrow)" />
              <path d="M16 7.6 L16 11.5" marker-end="url(#brandArrow)" />
              <path d="M24.6 9 L21 12" marker-end="url(#brandArrow)" />
            </g>
            <g fill="rgba(255,255,255,0.18)" stroke="#fff" stroke-width="1.1">
              <circle cx="6.8" cy="8.2" r="1.9" />
              <circle cx="16" cy="6.5" r="1.9" />
              <circle cx="25.2" cy="8.2" r="1.9" />
            </g>
            <path d="M11 19.6 L14.6 23.4 L21.4 15.6" fill="none" stroke="#fff" stroke-width="2"
                  stroke-linecap="round" stroke-linejoin="round" />
          </svg>
        </span>
        <span v-if="!collapsed" class="brand-text">fin-api-test</span>
        </router-link>
      </el-tooltip>
      <el-menu
        :default-active="menuActive"
        router
        class="nav-menu"
        :collapse="collapsed"
      >
        <!-- 顺序 = 日常测试工作流：接口(素材) → 用例(编排/执行) → 数据集(参数化) → 执行记录(结果)；
             环境配置与字典/文件为低频准备项，管理员功能沉底 -->
        <el-menu-item index="/apis">
          <el-icon><Connection /></el-icon>
          <template #title><span>接口管理</span></template>
        </el-menu-item>
        <el-menu-item index="/cases">
          <el-icon><Share /></el-icon>
          <template #title><span>用例管理</span></template>
        </el-menu-item>
        <el-menu-item index="/datasets">
          <el-icon><Grid /></el-icon>
          <template #title><span>数据集</span></template>
        </el-menu-item>
        <el-menu-item index="/executions">
          <el-icon><Histogram /></el-icon>
          <template #title><span>执行记录</span></template>
        </el-menu-item>
        <el-menu-item index="/envs">
          <el-icon><Setting /></el-icon>
          <template #title><span>环境配置</span></template>
        </el-menu-item>
        <el-menu-item index="/dictionary">
          <el-icon><Collection /></el-icon>
          <template #title><span>字段字典</span></template>
        </el-menu-item>
        <el-menu-item index="/files">
          <el-icon><Files /></el-icon>
          <template #title><span>文件中心</span></template>
        </el-menu-item>
        <el-menu-item v-if="store.user?.role === 'admin'" index="/users">
          <el-icon><UserFilled /></el-icon>
          <template #title><span>用户管理</span></template>
        </el-menu-item>
        <el-menu-item v-if="store.user?.role === 'admin'" index="/operation-logs">
          <el-icon><List /></el-icon>
          <template #title><span>操作日志</span></template>
        </el-menu-item>
      </el-menu>
      <!-- 侧边栏底部：当前登录用户头像（持续涟漪特效，悬浮旋转保留） -->
      <div class="sidebar-foot">
        <div class="avatar-ripple">
          <!-- 用户本人头像：tooltip 显示用户名（开发者署名见登录页页脚） -->
          <el-tooltip
            v-if="currentAvatar"
            :content="store.user?.name || store.user?.username || '当前用户'"
            placement="top"
            popper-class="app-tip"
          >
            <img
              :src="currentAvatar"
              width="36"
              height="36"
              class="dev-avatar"
              :alt="store.user?.name || store.user?.username || '用户'"
            />
          </el-tooltip>
          <el-tooltip
            v-else
            :content="store.user?.name || store.user?.username || '当前用户'"
            placement="top"
            popper-class="app-tip"
          >
            <div class="dev-avatar dev-avatar-fallback">
              {{ fallbackInitial }}
            </div>
          </el-tooltip>
          <el-tooltip v-if="avatarUploading" content="头像上传中…" placement="top" popper-class="app-tip">
            <div class="avatar-uploading">…</div>
          </el-tooltip>
        </div>
      </div>
    </el-aside>

    <el-container>
      <el-header class="topbar">
        <div class="topbar-left">
          <el-tooltip :content="collapsed ? '展开侧边栏' : '收起侧边栏'" placement="top" popper-class="app-tip">
            <el-button text class="collapse-btn" :aria-label="collapsed ? '展开侧边栏' : '收起侧边栏'" @click="toggleSidebar">
              <el-icon><Fold v-if="!collapsed" /><Expand v-else /></el-icon>
            </el-button>
          </el-tooltip>
          <el-breadcrumb :separator-icon="ArrowRight" class="topbar-breadcrumb">
            <el-breadcrumb-item :to="{ path: '/' }">
              <el-icon><HomeFilled /></el-icon>
            </el-breadcrumb-item>
            <el-breadcrumb-item v-for="item in breadcrumbItems" :key="item.path" :to="item.path">
              {{ item.title }}
            </el-breadcrumb-item>
          </el-breadcrumb>
          <el-button text class="cmd-trigger" @click="cmdPaletteRef?.open()">
            <el-icon><Search /></el-icon>
            <span class="cmd-trigger-text">搜索</span>
            <el-tag size="small" effect="plain" round class="cmd-trigger-kbd">{{ isMac ? 'Cmd K' : 'Ctrl K' }}</el-tag>
          </el-button>
        </div>
        <div class="topbar-selectors">
          <el-select
            v-model="store.currentProjectId"
            :placeholder="store.projects.length ? '选择项目' : '暂无项目'"
            size="default"
            style="width: 180px"
            @change="onProjectChange"
          >
            <el-option
              v-for="p in store.projects"
              :key="p.id"
              :label="p.name"
              :value="p.id"
            />
          </el-select>
          <!-- 项目管理入口：低频配置不占侧栏，归宿是项目选择器旁（规范 interaction-guidelines §1） -->
          <el-tooltip content="项目管理" placement="top" popper-class="app-tip">
            <el-button text @click="router.push('/projects')">
              <el-icon><Folder /></el-icon>管理
            </el-button>
          </el-tooltip>
          <el-tooltip
            v-if="store.currentProjectId"
            content="项目版本管理"
            placement="top"
            popper-class="app-tip"
          >
            <el-button
              text
              @click="versionVisible = true"
            >
              <el-icon><DataLine /></el-icon>版本
            </el-button>
          </el-tooltip>
          <el-select
            v-model="store.currentEnvId"
            placeholder="选择环境"
            size="default"
            style="width: 160px"
          >
            <el-option
              v-for="e in store.environments"
              :key="e.id"
              :label="e.name"
              :value="e.id"
            />
          </el-select>
          <el-tooltip :content="isFullscreen ? '退出全屏' : '进入全屏'" placement="top" popper-class="app-tip">
            <el-button text @click="toggleFullscreen">
              <el-icon><FullScreen /></el-icon>
            </el-button>
          </el-tooltip>
          <!-- 常驻帮助入口：coreCap 三 tab（表达式/断言/数据集）随手可查 -->
          <el-tooltip content="帮助（表达式 / 断言 / 数据集）" placement="top" popper-class="app-tip">
            <el-button text aria-label="帮助" @click="store.openCoreCapability('expression')">
              <el-icon><QuestionFilled /></el-icon>
            </el-button>
          </el-tooltip>
          <!-- tooltip 必须包在 dropdown 外层：嵌在 dropdown 插槽内会与其触发器事件克隆互相覆盖，导致点击弹不出下拉 -->
          <el-tooltip :content="themeLabel" placement="top" popper-class="app-tip">
            <el-dropdown trigger="click" @command="onThemeCommand">
              <el-button text>
                <!-- 图标与当前主题模式一一对应：浅色太阳 / 深色月亮 / 跟随系统显示器 -->
                <el-icon>
                  <Monitor v-if="store.theme === 'auto'" />
                  <Sunny v-else-if="store.theme === 'light'" />
                  <Moon v-else />
                </el-icon>
              </el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="light" :class="{ 'theme-checked': store.theme === 'light' }">
                    <el-icon><Sunny /></el-icon>浅色
                    <el-icon v-if="store.theme === 'light'" class="theme-check"><Check /></el-icon>
                  </el-dropdown-item>
                  <el-dropdown-item command="dark" :class="{ 'theme-checked': store.theme === 'dark' }">
                    <el-icon><Moon /></el-icon>深色
                    <el-icon v-if="store.theme === 'dark'" class="theme-check"><Check /></el-icon>
                  </el-dropdown-item>
                  <el-dropdown-item command="auto" :class="{ 'theme-checked': store.theme === 'auto' }">
                    <el-icon><Monitor /></el-icon>跟随系统
                    <el-icon v-if="store.theme === 'auto'" class="theme-check"><Check /></el-icon>
                  </el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </el-tooltip>
          <el-dropdown trigger="click" @command="onUserCommand">
            <span class="user-chip">
              <img
                v-if="currentAvatar"
                :src="currentAvatar"
                class="user-avatar"
                :alt="store.user?.name || store.user?.username || '用户'"
              />
              <el-icon v-else><UserFilled /></el-icon>
              <span class="user-name">{{ store.user?.name || store.user?.username || '用户' }}</span>
              <el-tag v-if="store.user?.role === 'admin'" size="small" type="warning" effect="plain" round>管理员</el-tag>
            </span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="changeAvatar">
                  <el-icon><Avatar /></el-icon>修改头像
                </el-dropdown-item>
                <el-dropdown-item command="changePassword">
                  <el-icon><Lock /></el-icon>修改密码
                </el-dropdown-item>
                <el-dropdown-item command="logout">
                  <el-icon><SwitchButton /></el-icon>退出登录
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
          <input
            ref="avatarInputRef"
            type="file"
            accept="image/png,image/jpeg,image/webp"
            style="display: none"
            @change="onAvatarFileChange"
          />
        </div>
      </el-header>
      <!-- 标签页栏（TransitionGroup 开关动画 + 右键快捷菜单） -->
      <div class="tab-bar">
        <div class="tab-scroll">
          <TransitionGroup name="tab">
            <div
              v-for="tab in tabStore.tabs"
              :key="tab.path"
              class="tab-item"
              :class="{ active: tab.path === route.path }"
              @click="router.push(tab.path)"
              @mousedown="onTabMouseDown($event, tab)"
              @contextmenu.prevent="onTabContextMenu($event, tab)"
            >
              <span class="tab-title">{{ tab.title }}</span>
              <el-icon
                v-if="tab.closable"
                class="tab-close"
                @click.stop="onTabClose(tab.path)"
              >
                <Close />
              </el-icon>
            </div>
          </TransitionGroup>
        </div>
        <el-dropdown trigger="click" @command="onTabCommand" class="tab-actions">
          <el-button text size="small" class="tab-more-btn">
            <el-icon><ArrowDown /></el-icon>
          </el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="closeLeft">关闭左侧</el-dropdown-item>
              <el-dropdown-item command="closeRight">关闭右侧</el-dropdown-item>
              <el-dropdown-item command="closeOthers" divided>关闭其他</el-dropdown-item>
              <el-dropdown-item command="closeAll">关闭全部</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>

      <!-- 标签页右键菜单（关闭/关闭左侧/右侧/其他，浏览器 tab 式操作） -->
      <Teleport to="body">
        <div
          v-if="tabCtx.visible"
          class="tab-ctxmenu"
          :style="{ left: tabCtx.x + 'px', top: tabCtx.y + 'px' }"
          @click.stop
        >
          <div
            v-if="tabCtx.tab?.closable"
            class="ctx-item"
            @click="onCtxAction('close')"
          >关闭标签</div>
          <div class="ctx-item" @click="onCtxAction('closeLeft')">关闭左侧</div>
          <div class="ctx-item" @click="onCtxAction('closeRight')">关闭右侧</div>
          <div class="ctx-item" @click="onCtxAction('closeOthers')">关闭其他</div>
        </div>
      </Teleport>
      <el-main class="main">
        <router-view v-slot="{ Component }">
          <transition name="page-fade" mode="out-in">
            <keep-alive :max="15">
              <component :is="Component" :key="route.fullPath" />
            </keep-alive>
          </transition>
        </router-view>
      </el-main>
    </el-container>
  </el-container>

  <!-- 全局命令面板（Ctrl+K） -->
  <CommandPalette ref="cmdPaletteRef" />

  <!-- 核心能力详情弹窗：表达式引擎 / 17 种断言 / 数据集（状态来自全局 store，跨组件可触发） -->
  <el-dialog
    v-model="store.coreCapVisible"
    :title="coreCapTitle"
    width="860px"
    align-center
    class="corecap-dialog"
  >
    <el-tabs v-model="store.coreCapTab" class="corecap-tabs">
      <!-- ========== 表达式引擎 ========== -->
      <el-tab-pane label="表达式引擎" name="expression">
        <div class="corecap-intro">
          在请求字段、SQL、断言期望值中均可使用 <code>${...}</code> 表达式动态求值。
          整串为 <code>${func()}</code> 时返回原生类型（int/list 等），内嵌时做字符串替换。
        </div>
        <div class="corecap-group">
          <div class="corecap-group-title">变量引用</div>
          <div class="corecap-cards">
            <div v-for="fn in expressionData.variables" :key="fn.syntax" class="corecap-card">
              <div class="corecap-card-head">
                <code class="corecap-syntax">{{ fn.syntax }}</code>
                <span class="corecap-desc">{{ fn.desc }}</span>
              </div>
              <div class="corecap-example">示例：{{ fn.example }} → <span class="corecap-result">{{ fn.result }}</span></div>
            </div>
          </div>
        </div>
        <div class="corecap-group">
          <div class="corecap-group-title">时间与随机</div>
          <div class="corecap-cards">
            <div v-for="fn in expressionData.timeRandom" :key="fn.syntax" class="corecap-card">
              <div class="corecap-card-head">
                <code class="corecap-syntax">{{ fn.syntax }}</code>
                <span class="corecap-desc">{{ fn.desc }}</span>
              </div>
              <div class="corecap-example">示例：{{ fn.example }} → <span class="corecap-result">{{ fn.result }}</span></div>
            </div>
          </div>
        </div>
        <div class="corecap-group">
          <div class="corecap-group-title">字符串处理</div>
          <div class="corecap-cards">
            <div v-for="fn in expressionData.stringOps" :key="fn.syntax" class="corecap-card">
              <div class="corecap-card-head">
                <code class="corecap-syntax">{{ fn.syntax }}</code>
                <span class="corecap-desc">{{ fn.desc }}</span>
              </div>
              <div class="corecap-example">示例：{{ fn.example }} → <span class="corecap-result">{{ fn.result }}</span></div>
            </div>
          </div>
        </div>
        <div class="corecap-group">
          <div class="corecap-group-title">业务单号生成</div>
          <div class="corecap-cards">
            <div v-for="fn in expressionData.business" :key="fn.syntax" class="corecap-card">
              <div class="corecap-card-head">
                <code class="corecap-syntax">{{ fn.syntax }}</code>
                <span class="corecap-desc">{{ fn.desc }}</span>
              </div>
              <div class="corecap-example">示例：{{ fn.example }} → <span class="corecap-result">{{ fn.result }}</span></div>
            </div>
          </div>
        </div>
        <div class="corecap-group">
          <div class="corecap-group-title">数据库查询</div>
          <div class="corecap-cards">
            <div v-for="fn in expressionData.dbFuncs" :key="fn.syntax" class="corecap-card">
              <div class="corecap-card-head">
                <code class="corecap-syntax">{{ fn.syntax }}</code>
                <span class="corecap-desc">{{ fn.desc }}</span>
              </div>
              <div class="corecap-example">示例：{{ fn.example }} → <span class="corecap-result">{{ fn.result }}</span></div>
            </div>
          </div>
        </div>
      </el-tab-pane>

      <!-- ========== 17 种断言 ========== -->
      <el-tab-pane label="17 种断言规则" name="assertion">
        <div class="corecap-intro">
          在节点配置的「断言」中添加规则。DB 类断言支持 <code>retry_count</code> 和 <code>retry_interval</code> 参数应对异步落库。
        </div>
        <div class="corecap-group">
          <div class="corecap-group-title">JSONPath 响应断言（7 种）</div>
          <div class="corecap-cards">
            <div v-for="a in assertionData.jsonpath" :key="a.type" class="corecap-card">
              <div class="corecap-card-head">
                <code class="corecap-syntax">{{ a.type }}</code>
                <span class="corecap-desc">{{ a.desc }}</span>
              </div>
              <div class="corecap-example">配置：{{ a.example }}</div>
            </div>
          </div>
        </div>
        <div class="corecap-group">
          <div class="corecap-group-title">HTTP 响应断言（2 种）</div>
          <div class="corecap-cards">
            <div v-for="a in assertionData.http" :key="a.type" class="corecap-card">
              <div class="corecap-card-head">
                <code class="corecap-syntax">{{ a.type }}</code>
                <span class="corecap-desc">{{ a.desc }}</span>
              </div>
              <div class="corecap-example">配置：{{ a.example }}</div>
            </div>
          </div>
        </div>
        <div class="corecap-group">
          <div class="corecap-group-title">数据库断言（6 种）</div>
          <div class="corecap-cards">
            <div v-for="a in assertionData.db" :key="a.type" class="corecap-card">
              <div class="corecap-card-head">
                <code class="corecap-syntax">{{ a.type }}</code>
                <span class="corecap-desc">{{ a.desc }}</span>
              </div>
              <div class="corecap-example">配置：{{ a.example }}</div>
            </div>
          </div>
        </div>
        <div class="corecap-group">
          <div class="corecap-group-title">DB 与响应交叉校验（2 种）</div>
          <div class="corecap-cards">
            <div v-for="a in assertionData.cross" :key="a.type" class="corecap-card">
              <div class="corecap-card-head">
                <code class="corecap-syntax">{{ a.type }}</code>
                <span class="corecap-desc">{{ a.desc }}</span>
              </div>
              <div class="corecap-example">配置：{{ a.example }}</div>
            </div>
          </div>
        </div>
      </el-tab-pane>

      <!-- ========== 数据驱动 · 数据集 ========== -->
      <el-tab-pane label="数据驱动 · 数据集" name="dataset">
        <div class="corecap-intro">
          数据集 = 同一用例的多组参数。用例绑定数据集后，执行一次会按数据行展开为 N 次执行；
          每行执行时同名列覆盖请求参数，嵌套字段用点号路径，跨列引用用 <code>${列名}</code>。
        </div>
        <div class="corecap-group">
          <div class="corecap-group-title">核心概念</div>
          <div class="corecap-cards">
            <div class="corecap-card">
              <div class="corecap-card-head">
                <code class="corecap-syntax">列 key = 请求参数名</code>
                <span class="corecap-desc">同名即自动覆盖写死的参数值</span>
              </div>
              <div class="corecap-example">示例：列 <code>order_id</code> 覆盖请求体中的 <code>order_id</code></div>
            </div>
            <div class="corecap-card">
              <div class="corecap-card-head">
                <code class="corecap-syntax">a.b.c / a.0.b</code>
                <span class="corecap-desc">点号写嵌套对象与数组下标</span>
              </div>
              <div class="corecap-example">示例：<code>to_customer.put_amount</code>、<code>supplier.0.order_id</code></div>
            </div>
            <div class="corecap-card">
              <div class="corecap-card-head">
                <code class="corecap-syntax">${列名}</code>
                <span class="corecap-desc">跨字段引用同行的其他列值</span>
              </div>
              <div class="corecap-example">示例：默认值 <code>${bl_no}-A</code> 拼接同行的运单号</div>
            </div>
            <div class="corecap-card">
              <div class="corecap-card-head">
                <code class="corecap-syntax">节点配置快照</code>
                <span class="corecap-desc">执行按快照跑；保存用例自动同步，执行前检测过期可一键同步</span>
              </div>
              <div class="corecap-example">场景：改了编排忘了同步 → 执行确认面板会提示 drift</div>
            </div>
          </div>
        </div>
        <div class="corecap-group">
          <div class="corecap-group-title">工作流</div>
          <div class="corecap-cards">
            <div class="corecap-card">
              <div class="corecap-card-head">
                <code class="corecap-syntax">从用例生成</code>
                <span class="corecap-desc">扫描用例写死的请求参数成列，附 1 行原值快照</span>
              </div>
              <div class="corecap-example">入口：数据集页 → 选中用例 → 「从用例生成」</div>
            </div>
            <div class="corecap-card">
              <div class="corecap-card-head">
                <code class="corecap-syntax">绑定</code>
                <span class="corecap-desc">用例私有数据集，在用例行内「数据」入口绑定/更换/解绑</span>
              </div>
              <div class="corecap-example">跨用例复用：在数据集页复制一份再改</div>
            </div>
            <div class="corecap-card">
              <div class="corecap-card-head">
                <code class="corecap-syntax">执行确认面板</code>
                <span class="corecap-desc">绑定后执行弹出：临时换数据集、勾选部分行、快照过期一键同步</span>
              </div>
              <div class="corecap-example">N 行 = N 次执行（并行，并发上限 4）</div>
            </div>
            <div class="corecap-card">
              <div class="corecap-card-head">
                <code class="corecap-syntax">Excel/CSV 导入</code>
                <span class="corecap-desc">先解析预览（列对齐告警）再确认替换全部行；可导出 xlsx</span>
              </div>
              <div class="corecap-example">适合批量造数与外部数据回灌</div>
            </div>
          </div>
        </div>
      </el-tab-pane>
    </el-tabs>
    <template #footer>
      <el-button type="primary" @click="store.setCoreCapVisible(false)">关闭</el-button>
    </template>
  </el-dialog>

  <!-- 项目版本管理 -->
  <ProjectVersionHistory
    v-model="versionVisible"
    :project-id="store.currentProjectId"
    @rollback="onVersionRollback"
  />
</template>

<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref, computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessageBox, ElMessage } from 'element-plus'
import { Connection, Share, Setting, Histogram, UserFilled, SwitchButton, List, Folder, Files, Expand, Fold, Sunny, Moon, Monitor, Search, HomeFilled, ArrowRight, Lock, DataLine, Close, ArrowDown, Avatar, FullScreen, Check, Collection, Grid, QuestionFilled } from '@element-plus/icons-vue'
import { useAppStore } from '@/stores'
import { useTabStore, type TabItem } from '@/stores/tabs'
import { authApi } from '@/api'
import CommandPalette from '@/components/CommandPalette.vue'
import ProjectVersionHistory from '@/components/ProjectVersionHistory.vue'
import { resolveMenuActive } from '@/utils/ui'

const route = useRoute()
const router = useRouter()
const store = useAppStore()
const tabStore = useTabStore()
const cmdPaletteRef = ref<InstanceType<typeof CommandPalette> | null>(null)
const versionVisible = ref(false)

// 核心能力弹窗标题按 tab 映射（三个 tab 后不再用内联三元）
const CORE_CAP_TITLES: Record<string, string> = {
  expression: '表达式引擎 · 内置函数与变量',
  assertion: '17 种断言规则 · 用法示例',
  dataset: '数据驱动 · 数据集用法',
}
const coreCapTitle = computed(() => CORE_CAP_TITLES[store.coreCapTab] || CORE_CAP_TITLES.expression)

// 侧边菜单项（与模板 el-menu-item index 一一对应；项目管理为低频配置，入口在顶栏项目选择器旁）
const MENU_PATHS = [
  '/envs', '/apis', '/cases', '/datasets', '/executions',
  '/dictionary', '/files', '/users', '/operation-logs',
]
// 子路由（如 /envs/edit/:id）下按段前缀匹配激活父菜单，避免导航上下文丢失
const menuActive = computed(() => resolveMenuActive(route.path, MENU_PATHS))
// Mac 用户快捷键标签按平台显示（实际监听 Ctrl/Cmd 双键）
const isMac = /mac|iphone|ipad/i.test(navigator.userAgent)

// 表达式引擎数据：与后端 expression.py 的 14 个内置函数 + 变量引用 + DB 函数对齐
const expressionData = {
  variables: [
    { syntax: '${var_name}', desc: '引用上下文中已提取的变量', example: '${order_id}', result: '10293' },
    { syntax: '${context.var}', desc: '兼容旧写法，等价于 ${var}', example: '${context.bl_no}', result: 'SMOK20260810' },
    { syntax: '${env.key}', desc: '引用环境变量', example: '${env.base_url}', result: 'https://api.example.com' },
  ],
  timeRandom: [
    { syntax: '${now()}', desc: '当前时间 ISO 字符串', example: '${now()}', result: '2026-08-10T14:25:07.353066' },
    { syntax: '${now(format=\'%Y-%m-%d\')}', desc: '按指定格式输出时间', example: "${now(format='%Y-%m-%d %H:%M')}", result: '2026-08-10 14:25' },
    { syntax: '${timestamp()}', desc: '当前 Unix 时间戳（秒，整数）', example: '${timestamp()}', result: '1786291200' },
    { syntax: '${date_add(days=1)}', desc: '当前日期加 N 天，默认 %Y-%m-%d', example: '${date_add(days=7)}', result: '2026-08-17' },
    { syntax: '${date_add(days=-1, format=\'%Y%m%d\')}', desc: '昨天，自定义格式', example: "${date_add(days=-1, format='%Y%m%d')}", result: '20260809' },
    { syntax: '${random_int(min=1, max=100)}', desc: '指定区间随机整数', example: '${random_int(min=1000, max=9999)}', result: '5623' },
    { syntax: '${random_string(length=8)}', desc: '随机字符串（字母+数字）', example: '${random_string(length=16)}', result: 'aB3kM9xZ2pQ7vN1w' },
    { syntax: '${uuid()}', desc: 'UUID 字符串（小写带横杠）', example: '${uuid()}', result: '550e8400-e29b-41d4-a716-446655440000' },
  ],
  stringOps: [
    { syntax: '${upper(s=\'abc\')}', desc: '转大写', example: "${upper(s='hello')}", result: 'HELLO' },
    { syntax: '${lower(s=\'ABC\')}', desc: '转小写', example: "${lower(s='WORLD')}", result: 'world' },
    { syntax: '${md5(s=\'abc\')}', desc: 'MD5 哈希', example: "${md5(s='123456')}", result: 'e10adc3949ba59abbe56e057f20f883e' },
  ],
  business: [
    { syntax: '${generate_bl_no()}', desc: '生成提单号', example: '${generate_bl_no()}', result: 'SMOK20260810143052' },
    { syntax: '${generate_bl_no(prefix=\'TEST\')}', desc: '指定前缀生成提单号', example: "${generate_bl_no(prefix='TEST')}", result: 'TEST20260810143052' },
    { syntax: '${generate_invoice_number()}', desc: '生成发票号', example: '${generate_invoice_number()}', result: 'INV202608101430527823' },
    { syntax: '${generate_invoice_number(prefix=\'TEST\')}', desc: '指定前缀生成发票号', example: "${generate_invoice_number(prefix='TEST')}", result: 'TEST202608101430527823' },
    { syntax: '${generate_unique_id()}', desc: '生成唯一 ID', example: '${generate_unique_id()}', result: 'a1b2c3d4e5f6' },
  ],
  dbFuncs: [
    { syntax: '${db.query_value(sql, field)}', desc: '执行 SQL 返回标量值', example: "${db.query_value('SELECT order_id FROM sys_order WHERE bl_no=\\'${bl_no}\\'', field='order_id')}", result: '10293' },
    { syntax: '${db.query_one(sql)}', desc: '执行 SQL 返回第一行 dict', example: "${db.query_one('SELECT * FROM sys_order WHERE id=1')}", result: '{id: 1, status: "paid"}' },
    { syntax: '${db.query(sql)}', desc: '执行 SQL 返回全部行', example: "${db.query('SELECT id, name FROM sys_user LIMIT 5')}", result: '[{id:1,...}, {id:2,...}]' },
  ],
}

// 17 种断言数据：与后端 assertion_engine.py 对齐
const assertionData = {
  jsonpath: [
    { type: 'json_path_equals', desc: 'JSONPath 取值等于期望', example: "{type:'json_path_equals', path:'$.data.status', expected:'success'}" },
    { type: 'json_path_not_equals', desc: 'JSONPath 取值不等于期望', example: "{type:'json_path_not_equals', path:'$.data.status', expected:'error'}" },
    { type: 'json_path_contains', desc: '取值包含期望（字符串/列表）', example: "{type:'json_path_contains', path:'$.data.name', expected:'订单'}" },
    { type: 'json_path_exists', desc: 'JSONPath 路径存在', example: "{type:'json_path_exists', path:'$.data.order_id'}" },
    { type: 'json_path_not_empty', desc: '取值非空', example: "{type:'json_path_not_empty', path:'$.data.items'}" },
    { type: 'json_path_match_regex', desc: '取值匹配正则', example: "{type:'json_path_match_regex', path:'$.data.phone', pattern:'^1[3-9]\\d{9}$'}" },
    { type: 'json_path_type_equals', desc: '取值类型校验', example: "{type:'json_path_type_equals', path:'$.data.amount', expected:'int'} (string/int/bool/array/object/null)" },
  ],
  http: [
    { type: 'response_status_equals', desc: 'HTTP 状态码等于期望', example: "{type:'response_status_equals', expected:200}" },
    { type: 'response_time_less_than', desc: '响应时间小于期望(ms)', example: "{type:'response_time_less_than', expected:2000}" },
  ],
  db: [
    { type: 'db_query_equals', desc: 'DB 查询字段等于期望', example: "{type:'db_query_equals', sql:'SELECT status FROM sys_order WHERE bl_no=\\'${bl_no}\\'', field:'status', expected:'paid'}" },
    { type: 'db_query_not_equals', desc: 'DB 查询字段不等于期望', example: "{type:'db_query_not_equals', sql:'...', field:'status', expected:'deleted'}" },
    { type: 'db_query_not_empty', desc: 'DB 查询结果非空', example: "{type:'db_query_not_empty', sql:'SELECT id FROM sys_order WHERE bl_no=\\'${bl_no}\\''}" },
    { type: 'db_query_count_equals', desc: '查询行数等于期望', example: "{type:'db_query_count_equals', sql:'SELECT id FROM sys_order WHERE user_id=${uid}', expected:3}" },
    { type: 'db_query_count_greater_than', desc: '查询行数大于期望', example: "{type:'db_query_count_greater_than', sql:'...', expected:0}" },
    { type: 'db_query_count_less_than', desc: '查询行数小于期望', example: "{type:'db_query_count_less_than', sql:'...', expected:100}" },
  ],
  cross: [
    { type: 'db_vs_jsonpath_equals', desc: 'DB 值等于响应 JSONPath 取值', example: "{type:'db_vs_jsonpath_equals', sql:'SELECT status FROM sys_order WHERE bl_no=\\'${bl_no}\\'', field:'status', path:'$.data.status'}" },
    { type: 'db_vs_jsonpath_not_equals', desc: 'DB 值不等于响应 JSONPath 取值', example: "{type:'db_vs_jsonpath_not_equals', sql:'...', field:'status', path:'$.data.status'}" },
  ],
}
// 侧边栏折叠状态：localStorage 记忆，默认展开
const SIDEBAR_KEY = 'fin_sidebar_collapsed'
const collapsed = ref(localStorage.getItem(SIDEBAR_KEY) === '1')
function toggleSidebar() {
  collapsed.value = !collapsed.value
  localStorage.setItem(SIDEBAR_KEY, collapsed.value ? '1' : '0')
}

// 项目版本回滚后，项目下所有接口/用例数据已变化，刷新当前页面确保数据一致
function onVersionRollback() {
  ElMessage.success('项目已回滚，正在刷新页面...')
  setTimeout(() => window.location.reload(), 800)
}

// ===== 头像 =====
// 侧边栏底部与顶部用户菜单共用当前登录用户头像
const currentAvatar = ref<string | null>(null)
const avatarInputRef = ref<HTMLInputElement | null>(null)
const avatarUploading = ref(false)
// 无头像时的 fallback 首字母：优先显示名，其次用户名
const fallbackInitial = computed(() =>
  (store.user?.name || store.user?.username || 'U').charAt(0).toUpperCase()
)

async function loadCurrentAvatar() {
  if (!store.user) return
  // has_avatar=false 时无需请求，避免 404 噪音
  if (store.user.has_avatar === false) {
    currentAvatar.value = null
    return
  }
  try {
    const res = await authApi.getAvatar(store.user.id)
    currentAvatar.value = res.avatar ?? null
  } catch {
    currentAvatar.value = null
  }
}

// canvas 压缩图片到 256x256，输出 jpeg base64 data URL
function compressImage(file: File, size = 256, quality = 0.85): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => {
      const img = new Image()
      img.onload = () => {
        const canvas = document.createElement('canvas')
        canvas.width = size
        canvas.height = size
        const ctx = canvas.getContext('2d')!
        // 居中裁剪为正方形
        const min = Math.min(img.width, img.height)
        const sx = (img.width - min) / 2
        const sy = (img.height - min) / 2
        ctx.drawImage(img, sx, sy, min, min, 0, 0, size, size)
        resolve(canvas.toDataURL('image/jpeg', quality))
      }
      img.onerror = () => reject(new Error('图片加载失败'))
      img.src = reader.result as string
    }
    reader.onerror = () => reject(new Error('文件读取失败'))
    reader.readAsDataURL(file)
  })
}

async function onAvatarFileChange(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  if (file.size > 5 * 1024 * 1024) {
    ElMessage.warning('图片不能超过 5MB')
    input.value = ''
    return
  }
  avatarUploading.value = true
  try {
    const dataUrl = await compressImage(file)
    await authApi.updateAvatar(dataUrl)
    currentAvatar.value = dataUrl
    ElMessage.success('已更新')
  } catch (err: any) {
    ElMessage.error(err.message || '头像上传失败')
  } finally {
    avatarUploading.value = false
    input.value = ''
  }
}

const themeLabel = computed(() => {
  if (store.theme === 'light') return '浅色模式'
  if (store.theme === 'dark') return '深色模式'
  return '跟随系统'
})
function onThemeCommand(cmd: 'light' | 'dark' | 'auto') {
  // 圆形扩散过渡：从右上角主题按钮附近扩散（按钮在顶栏右侧）
  const x = window.innerWidth - 60
  const y = 40
  document.documentElement.style.setProperty('--theme-x', `${x}px`)
  document.documentElement.style.setProperty('--theme-y', `${y}px`)
  const apply = () => store.applyTheme(cmd)
  // 不支持 View Transitions API 的浏览器直接切换
  if (!document.startViewTransition) {
    apply()
  } else {
    // 切换前冻结全站 CSS 过渡：主题变量变化会触发 body/按钮/输入框等大量元素的
    // 颜色过渡，与扩散动画并行时抢占主线程导致掉帧，且新快照可能拍到过渡中间色
    const root = document.documentElement
    root.classList.add('theme-switching')
    const transition = document.startViewTransition(() => apply())
    // 扩散动画结束后解冻，恢复正常交互过渡
    transition.finished.finally(() => root.classList.remove('theme-switching'))
  }
  ElMessage.success(`已切换为${cmd === 'light' ? '浅色' : cmd === 'dark' ? '深色' : '跟随系统'}模式`)
}

function onProjectChange(id: number) {
  store.setProject(id)
}

// ===== 浏览器全屏切换 =====
const isFullscreen = ref(false)

function toggleFullscreen() {
  if (!document.fullscreenElement) {
    document.documentElement.requestFullscreen?.()
  } else {
    document.exitFullscreen?.()
  }
}

// 监听全屏状态变化（含 Esc 退出），同步按钮提示
function onFsChange() {
  isFullscreen.value = !!document.fullscreenElement
}
onMounted(() => {
  document.addEventListener('fullscreenchange', onFsChange)
})
onBeforeUnmount(() => {
  document.removeEventListener('fullscreenchange', onFsChange)
})

// 面包屑：取路由 matched 链中带 title 的项（排除根布局）
const breadcrumbItems = computed(() => {
  return route.matched
    .filter((r) => r.meta.title && !r.redirect)
    .map((r) => ({ path: r.path, title: r.meta.title as string }))
})

async function onUserCommand(cmd: string) {
  if (cmd === 'changeAvatar') {
    avatarInputRef.value?.click()
    return
  }
  if (cmd === 'changePassword') {
    router.push('/change-password')
    return
  }
  if (cmd === 'logout') {
    await ElMessageBox.confirm('确定退出登录吗？', '提示', { type: 'warning' })
    store.logout()
    tabStore.reset()
    ElMessage.success('已退出登录')
    router.replace('/login')
  }
}

// ===== 标签页操作 =====
/**
 * 关闭标签。关闭当前页面时须「先导航、成功后再移除」：
 * 页面级 onBeforeRouteLeave（未保存确认）可能取消导航，若先移除标签，
 * 取消后会出现「人还在页面、标签却没了 + 高亮错位」。vue-router 4 的 push
 * 被守卫拒绝时 resolve NavigationFailure（非 undefined），以此判定是否移除。
 */
async function onTabClose(path: string) {
  if (route.path !== path) {
    // 关闭非当前标签：无导航，直接移除
    tabStore.removeTab(path)
    return
  }
  const idx = tabStore.tabs.findIndex((t) => t.path === path)
  if (idx === -1) return
  // 是否还有其他标签（不能用 tabs[0] 兜底——最后一个标签正是 tabs[0]，会自己兜住自己，
  // 导致「最后一个标签」分支永不触发、push 自身路径返回 duplicated、removeTab 被跳过、点击无反应）
  const others = tabStore.tabs.filter((t) => t.path !== path)
  if (!others.length) {
    // 最后一个标签（所有标签均可关）：删除后回首页。
    // 若删除前已在 /home，push 是 duplicated、路由 watcher 不触发，由 ensureHomeTab 手动重建标签
    tabStore.removeTab(path)
    await router.push('/home')
    tabStore.ensureHomeTab()
    return
  }
  // 相邻目标：优先右侧，其次左侧（others 非空时必存在）
  const next = tabStore.tabs[idx + 1] || tabStore.tabs[idx - 1]!
  const failure = await router.push(next.path)
  // 导航成功（含守卫放行后由页面守卫自行 removeTab 的重入，此处为幂等空操作）才收尾
  if (!failure) tabStore.removeTab(path)
}

/** 中键关闭标签（浏览器 tab 习惯）：mousedown 时 button===1，preventDefault 阻止自动滚动 */
function onTabMouseDown(e: MouseEvent, tab: TabItem) {
  if (e.button === 1) {
    e.preventDefault()
    if (tab.closable) onTabClose(tab.path)
  }
}

function onTabCommand(cmd: string) {
  if (cmd === 'closeLeft') {
    tabStore.removeLeft(route.path)
  } else if (cmd === 'closeRight') {
    tabStore.removeRight(route.path)
  } else if (cmd === 'closeOthers') {
    tabStore.removeOthers(route.path)
  } else if (cmd === 'closeAll') {
    const next = tabStore.removeAll()
    if (next && next !== route.path) {
      router.push(next)
    }
  }
}

// ===== 标签页右键菜单 =====
const tabCtx = ref<{ visible: boolean; x: number; y: number; tab: TabItem | null }>({
  visible: false, x: 0, y: 0, tab: null,
})

function onTabContextMenu(e: MouseEvent, tab: TabItem) {
  tabCtx.value = { visible: true, x: e.clientX, y: e.clientY, tab }
}

function hideTabCtx() {
  tabCtx.value.visible = false
}

function onCtxAction(action: 'close' | 'closeLeft' | 'closeRight' | 'closeOthers') {
  const tab = tabCtx.value.tab
  hideTabCtx()
  if (!tab) return
  if (action === 'close') {
    onTabClose(tab.path)
  } else if (action === 'closeLeft') {
    tabStore.removeLeft(tab.path)
  } else if (action === 'closeRight') {
    tabStore.removeRight(tab.path)
  } else if (action === 'closeOthers') {
    tabStore.removeOthers(tab.path)
    if (route.path !== tab.path) router.push(tab.path)
  }
}

// 点击任意处/滚动/右键其他位置时关闭菜单
onMounted(() => {
  window.addEventListener('click', hideTabCtx)
  window.addEventListener('scroll', hideTabCtx, true)
})
onBeforeUnmount(() => {
  window.removeEventListener('click', hideTabCtx)
  window.removeEventListener('scroll', hideTabCtx, true)
})

// 路由变化时自动添加标签
watch(() => route.fullPath, () => {
  if (route.path !== '/' && route.path !== '/login' && route.path !== '/change-password') {
    tabStore.addTab(route)
  }
}, { immediate: true })

onMounted(async () => {
  // 主题已在 App.vue 初始化，这里无需重复
  await store.loadUser()
  if (!store.user) return
  await store.loadProjects()
  if (store.currentProjectId) {
    await store.loadEnvironments()
    await store.loadFieldDict()
  } else if (route.path !== '/projects') {
    // 无项目时自动引导到项目管理页，避免后续页面因 currentProjectId 为空而卡死
    router.replace('/projects')
  }
  // 加载当前用户头像（侧边栏底部与顶部共用）
  loadCurrentAvatar()
})
</script>

<style scoped>
.layout {
  height: 100%;
}
.sidebar {
  position: relative;
  /* 实底深墨青（与登录页品牌区同色，审计青同族）：工程面板，不做渐变 */
  background: #0e2a33;
  border-right: none;
  padding: 16px 12px;
  transition: width 0.25s ease;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}
/* 背景装饰层 */
.sidebar-bg-deco {
  position: absolute;
  inset: 0;
  pointer-events: none;
  z-index: 0;
  opacity: 0.9;
}
.sidebar-bg-deco svg {
  width: 100%;
  height: 100%;
}
/* 内容层置于装饰之上 */
.sidebar > .brand,
.sidebar > .nav-menu,
.sidebar > .sidebar-foot {
  position: relative;
  z-index: 1;
}
.sidebar :deep(.nav-menu) {
  flex: 1;
  min-height: 0;
  background: transparent;
}
.sidebar-foot {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 12px 16px 4px;
  margin-top: 8px;
  border-top: 1px solid rgba(255, 255, 255, 0.12);
}
/* 头像定位容器（原持续涟漪装饰已删：动效只留功能反馈） */
.avatar-ripple {
  position: relative;
  width: 36px;
  height: 36px;
  flex-shrink: 0;
}
/* 头像上传中角标（原 avatarUploading 状态从未在模板使用） */
.avatar-uploading {
  position: absolute;
  right: -4px;
  bottom: -4px;
  min-width: 14px;
  height: 14px;
  line-height: 14px;
  text-align: center;
  font-size: 9px;
  color: #fff;
  background: var(--app-primary);
  border-radius: 7px;
  animation: avatar-uploading-blink 1s ease-in-out infinite;
}
@keyframes avatar-uploading-blink {
  0%, 100% { opacity: 0.4; }
  50% { opacity: 1; }
}
/* 减少动画偏好：上传角标停止闪烁，保持常亮 */
@media (prefers-reduced-motion: reduce) {
  .avatar-uploading {
    animation: none;
    opacity: 1;
  }
}
.dev-avatar {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  object-fit: cover;
  flex-shrink: 0;
  border: 2px solid rgba(255, 255, 255, 0.3);
  cursor: pointer;
  transition: transform 3s cubic-bezier(0.25, 0.8, 0.25, 1), box-shadow 0.3s ease, border-color 0.3s ease;
}
.dev-avatar:hover {
  transform: scale(1.15) rotate(360deg);
  box-shadow: 0 6px 16px rgba(0, 0, 0, 0.35);
  border-color: #fff;
}
.dev-avatar-fallback {
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(255, 255, 255, 0.2);
  color: #fff;
  font-weight: 600;
  font-size: 15px;
}
/* 顶部用户菜单头像 */
.user-avatar {
  width: 26px;
  height: 26px;
  border-radius: 50%;
  object-fit: cover;
  border: 1px solid var(--app-border);
}
.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px 18px;
  font-weight: 600;
  font-size: 16px;
  white-space: nowrap;
  color: #fff;
}
/* 品牌区可点击回首页：hover 亮起 + 键盘可达 */
.brand-link {
  cursor: pointer;
  border-radius: var(--app-radius-sm);
  transition: background 0.15s ease;
}
.brand-link:hover,
.brand-link:focus-visible {
  background: rgba(255, 255, 255, 0.1);
  outline: none;
}
/* 键盘焦点环：背景变化之外补内侧描边，深色底上保证可见性 */
.brand-link:focus-visible {
  box-shadow: inset 0 0 0 2px rgba(255, 255, 255, 0.45);
}
.brand-text {
  color: #fff;
}
.brand-logo {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  line-height: 0;
}
.nav-menu {
  border-right: none;
  background: transparent;
}
:deep(.nav-menu .el-menu-item) {
  border-radius: var(--app-radius-sm);
  margin-bottom: 4px;
  color: rgba(255, 255, 255, 0.75);
  transition: background 0.18s ease, color 0.18s ease;
}
:deep(.nav-menu .el-menu-item:hover) {
  background: rgba(255, 255, 255, 0.1);
  color: #fff;
}
:deep(.nav-menu .el-menu-item.is-active) {
  background: rgba(255, 255, 255, 0.18);
  color: #fff;
  font-weight: 500;
  /* 票据切角签名：与主按钮同构的右上切口 */
  clip-path: polygon(
    0 0,
    calc(100% - var(--app-chamfer)) 0,
    100% var(--app-chamfer),
    100% 100%,
    0 100%
  );
}
/* 折叠态：菜单项居中，tooltip 由 el-menu 原生提供 */
:deep(.nav-menu.el-menu--collapse) {
  width: 40px;
}
:deep(.nav-menu.el-menu--collapse .el-menu-item) {
  display: flex;
  justify-content: center;
  padding: 0 !important;
}
.topbar {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 52px; /* 工具密度：顶栏收紧（EP 默认 60px） */
  background: var(--app-card);
  border-bottom: 1px solid var(--app-border);
}
/* topbar 底部品牌色渐变线 */
.topbar::after {
  content: '';
  position: absolute;
  left: 0;
  right: 0;
  bottom: -1px;
  height: 1px;
  background: linear-gradient(90deg, transparent, color-mix(in srgb, var(--app-primary) 40%, transparent) 30%, color-mix(in srgb, var(--app-primary) 40%, transparent) 70%, transparent);
  pointer-events: none;
}
.topbar-left {
  display: flex;
  align-items: center;
  gap: 8px;
}
.collapse-btn {
  padding: 6px 8px;
  font-size: 18px;
  color: var(--app-text);
}
.topbar-breadcrumb {
  font-size: 15px;
  font-weight: 500;
  line-height: 1;
}
:deep(.topbar-breadcrumb .el-breadcrumb__inner) {
  color: var(--app-text-muted);
  font-weight: 500;
}
:deep(.topbar-breadcrumb .el-breadcrumb__item:last-child .el-breadcrumb__inner) {
  color: var(--app-text);
  font-weight: 600;
}
.cmd-trigger {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px !important;
  background: var(--app-chip-bg);
  border-radius: var(--app-radius-lg);
}
.cmd-trigger-text {
  font-size: 13px;
  color: var(--app-text-muted);
}
.cmd-trigger-kbd {
  font-size: 11px;
}
.topbar-selectors {
  display: flex;
  gap: 12px;
  align-items: center;
}
.user-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: var(--app-radius-lg);
  background: var(--app-chip-bg);
  cursor: pointer;
  font-size: 13px;
  outline: none;
}
/* 键盘焦点可见：outline:none 的替换焦点环 */
.user-chip:focus-visible {
  outline: 2px solid var(--app-primary);
  outline-offset: 2px;
}
.user-chip .user-name {
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.main {
  padding: 20px;
  overflow: auto;
  /* 极淡品牌色渐变：从顶部微蓝过渡到背景色，营造层次感 */
  background: linear-gradient(180deg, color-mix(in srgb, var(--app-primary) 4%, transparent) 0%, var(--app-bg) 180px);
}

/* ===== 标签页栏 ===== */
.tab-bar {
  display: flex;
  align-items: center;
  height: 38px;
  background: var(--app-sidebar);
  border-bottom: 1px solid var(--app-border);
  padding: 0 8px;
  flex-shrink: 0;
}
.tab-scroll {
  position: relative; /* tab leave 动画脱离布局流时的定位基准 */
  flex: 1;
  display: flex;
  align-items: center;
  gap: 4px;
  overflow-x: auto;
  overflow-y: hidden;
  height: 100%;
  scrollbar-width: none;
}
.tab-scroll::-webkit-scrollbar {
  display: none;
}
.tab-item {
  position: relative;
  display: flex;
  align-items: center;
  gap: 4px;
  height: 28px;
  padding: 0 10px;
  border-radius: var(--app-radius-sm);
  font-size: 13px;
  color: var(--app-text-muted);
  cursor: pointer;
  white-space: nowrap;
  flex-shrink: 0;
  transition: background 0.15s, color 0.15s;
}
/* ===== 标签页开关动画（TransitionGroup name="tab"；仅过渡 opacity/transform 合成器属性） ===== */
.tab-enter-active,
.tab-leave-active {
  transition: opacity 0.18s ease, transform 0.18s ease;
}
.tab-enter-from {
  opacity: 0;
  transform: translateY(6px) scale(0.92);
}
.tab-leave-to {
  opacity: 0;
  transform: scale(0.85);
}
.tab-leave-active {
  /* 移除中脱离布局流，其余标签平滑补位 */
  position: absolute;
}
/* 减少动画偏好：关闭开关动画 */
@media (prefers-reduced-motion: reduce) {
  .tab-enter-active,
  .tab-leave-active {
    transition: none;
  }
}
/* ===== 标签页右键菜单 ===== */
.tab-ctxmenu {
  position: fixed;
  z-index: 3000;
  min-width: 120px;
  padding: 4px;
  background: var(--app-card);
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius);
  box-shadow: var(--app-shadow-lg);
}
.tab-ctxmenu .ctx-item {
  padding: 6px 12px;
  font-size: 13px;
  color: var(--app-text);
  border-radius: 5px;
  cursor: pointer;
}
.tab-ctxmenu .ctx-item:hover {
  background: var(--app-hover, rgba(0, 0, 0, 0.05));
  color: var(--app-primary);
}
.tab-item:hover {
  background: var(--app-hover, rgba(0, 0, 0, 0.04));
}
.tab-item.active {
  /* 主色派生统一走 color-mix，消除与主题主色并存的第二种蓝 */
  background: color-mix(in srgb, var(--app-primary) 10%, transparent);
  color: var(--app-primary);
  font-weight: 500;
}
/* active 态底部品牌色下划线 */
.tab-item.active::after {
  content: '';
  position: absolute;
  left: 8px;
  right: 8px;
  bottom: -1px;
  height: 2px;
  background: var(--app-primary);
  border-radius: 1px;
}
.tab-item.active .tab-close:hover {
  background: color-mix(in srgb, var(--app-primary) 15%, transparent);
}
.tab-title {
  max-width: 160px;
  overflow: hidden;
  text-overflow: ellipsis;
}
.tab-close {
  font-size: 12px;
  border-radius: 50%;
  padding: 2px;
  transition: background 0.15s;
}
.tab-close:hover {
  background: rgba(0, 0, 0, 0.1);
}
.tab-actions {
  flex-shrink: 0;
  margin-left: 4px;
}
.tab-more-btn {
  padding: 4px 6px;
}


/* ===== 核心能力详情弹窗（Element Plus 内部类样式见全局 style 块）===== */
.corecap-intro {
  font-size: 12px;
  color: var(--app-text-muted);
  line-height: 1.6;
  padding: 10px 14px;
  margin-bottom: 16px;
  background: color-mix(in srgb, var(--app-primary) 6%, var(--app-card));
  border-left: 3px solid var(--app-primary);
  border-radius: 0 var(--app-radius-sm) var(--app-radius-sm) 0;
}
.corecap-intro code {
  font-family: var(--app-font-mono);
  font-size: 11px;
  color: var(--app-primary);
  background: var(--app-chip-bg);
  padding: 1px 4px;
  border-radius: 3px;
}
.corecap-group {
  margin-bottom: 18px;
}
.corecap-group-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--app-text);
  margin-bottom: 8px;
  padding-left: 10px;
  border-left: 3px solid var(--app-primary);
}
.corecap-cards {
  display: grid;
  grid-template-columns: 1fr;
  gap: 8px;
}
.corecap-card {
  padding: 10px 14px;
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius-sm);
  transition: border-color 0.18s ease, background 0.18s ease;
}
.corecap-card:hover {
  border-color: var(--app-primary);
  background: color-mix(in srgb, var(--app-primary) 4%, transparent);
}
.corecap-card-head {
  display: flex;
  align-items: baseline;
  gap: 10px;
  flex-wrap: wrap;
}
.corecap-syntax {
  font-family: var(--app-font-mono);
  font-size: 12px;
  font-weight: 600;
  color: var(--app-primary);
  background: color-mix(in srgb, var(--app-primary) 10%, transparent);
  padding: 2px 8px;
  border-radius: 4px;
  white-space: nowrap;
}
.corecap-desc {
  font-size: 12px;
  color: var(--app-text-muted);
}
.corecap-example {
  margin-top: 6px;
  font-size: 11px;
  color: var(--app-text-muted);
  font-family: var(--app-font-mono);
  line-height: 1.6;
  word-break: break-all;
}
.corecap-result {
  color: var(--app-success);
  font-weight: 500;
}

/* ===== 主题下拉当前项标记（原 is-active 类对 el-dropdown-item 无样式定义，标记从未生效） ===== */
:deep(.theme-checked) {
  color: var(--app-primary);
  background: color-mix(in srgb, var(--app-primary) 8%, transparent);
}
.theme-check {
  margin-left: auto;
  font-size: 12px;
  color: var(--app-primary);
}
</style>

<!-- 全局样式：el-dialog 默认 teleport 到 body，scoped 无法命中外层元素，需用全局样式 -->
<style>
/* ===== 核心能力详情弹窗：弹窗固定在视口内 ===== */
.corecap-dialog.el-dialog {
  margin-top: 0 !important;
  margin-bottom: 0;
  max-height: 86vh;
  display: flex;
  flex-direction: column;
}
.corecap-dialog .el-dialog__header {
  flex-shrink: 0;
  margin-right: 0;
  border-bottom: 1px solid var(--app-border);
}
.corecap-dialog .el-dialog__body {
  flex: 1;
  min-height: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  padding: 0 20px 8px;
}
.corecap-dialog .el-dialog__footer {
  flex-shrink: 0;
  border-top: 1px solid var(--app-border);
}
/* tabs 占满 body，header 固定，content 区滚动 */
.corecap-tabs {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
}
.corecap-tabs .el-tabs__header {
  margin-bottom: 12px;
  flex-shrink: 0;
}
.corecap-tabs .el-tabs__content {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding-right: 4px;
}
.corecap-tabs .el-tabs__item.is-active {
  color: var(--app-primary);
}
.corecap-tabs .el-tabs__active-bar {
  background-color: var(--app-primary);
}
.corecap-tabs .el-tabs__content::-webkit-scrollbar {
  width: 8px;
}
.corecap-tabs .el-tabs__content::-webkit-scrollbar-track {
  background: transparent;
}
.corecap-tabs .el-tabs__content::-webkit-scrollbar-thumb {
  background: var(--app-border);
  border-radius: 4px;
}
.corecap-tabs .el-tabs__content::-webkit-scrollbar-thumb:hover {
  background: var(--app-text-muted);
}

/* ===== 主题切换性能：切换瞬间冻结全站 CSS 过渡 ===== */
/* 主题变量变化会触发大量元素的颜色过渡，与扩散动画并行时抢占主线程导致卡顿；
   JS 在 startViewTransition 前加类、finished 后移除 */
html.theme-switching,
html.theme-switching *,
html.theme-switching *::before,
html.theme-switching *::after {
  transition: none !important;
}

/* ===== 主题切换圆形扩散过渡（View Transitions API）===== */
/* 不支持的浏览器自动降级为无动画切换 */
::view-transition-old(root),
::view-transition-new(root) {
  animation: none;
  mix-blend-mode: normal;
}
::view-transition-old(root) {
  z-index: 1;
}
::view-transition-new(root) {
  z-index: 9999;
  animation: theme-circle-reveal 0.55s cubic-bezier(0.25, 0.8, 0.25, 1);
}
@keyframes theme-circle-reveal {
  from {
    clip-path: circle(0% at var(--theme-x, 50%) var(--theme-y, 50%));
  }
  to {
    clip-path: circle(150% at var(--theme-x, 50%) var(--theme-y, 50%));
  }
}
/* 尊重用户「减少动态效果」偏好 */
@media (prefers-reduced-motion: reduce) {
  ::view-transition-new(root) {
    animation: none;
  }
}

/* ===== 路由切换过渡：淡入 + 轻微上滑 ===== */
.page-fade-enter-active,
.page-fade-leave-active {
  transition: opacity 0.2s ease, transform 0.2s ease;
}
.page-fade-enter-from {
  opacity: 0;
  transform: translateY(8px);
}
.page-fade-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}
@media (prefers-reduced-motion: reduce) {
  .page-fade-enter-active,
  .page-fade-leave-active {
    transition: none;
  }
}
</style>

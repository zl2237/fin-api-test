import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus, { ElTooltip } from 'element-plus'
import 'element-plus/dist/index.css'
import 'element-plus/theme-chalk/dark/css-vars.css'
import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'
import '@vue-flow/controls/dist/style.css'
import '@vue-flow/minimap/dist/style.css'

import App from './App.vue'
import router from './router'
import './style.css'
import { setupRipple } from '@/utils/ripple'

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.use(ElementPlus)
// 悬浮提示统一体感：悬浮 400ms 才出现（防鼠标扫过连环误触），
// 显示 4 秒自动关闭（防残留）。显式传 show-after 的组件不受影响。
;(ElTooltip.props as Record<string, { default?: unknown }>).showAfter.default = 400
;(ElTooltip.props as Record<string, { default?: unknown }>).autoClose.default = 4000
app.mount('#app')
// 全局按钮点击涟漪效果（零侵入，自动应用于 .el-button）
setupRipple()

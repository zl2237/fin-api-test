import { createRouter, createWebHistory } from 'vue-router'
import { getToken } from '@/api'

const routes = [
  { path: '/login', name: 'Login', component: () => import('@/views/Login.vue'), meta: { title: '登录', public: true } },
  { path: '/change-password', name: 'ChangePassword', component: () => import('@/views/ChangePassword.vue'), meta: { title: '修改密码' } },
  // 兜底 404：public 保证未登录访问未知路径也能看到友好提示而非空白
  { path: '/:pathMatch(.*)*', name: 'NotFound', component: () => import('@/views/NotFound.vue'), meta: { title: '页面不存在', public: true } },
  {
    path: '/',
    component: () => import('@/layouts/MainLayout.vue'),
    children: [
      { path: '', redirect: '/home' },
      { path: 'home', name: 'Home', component: () => import('@/views/Home.vue'), meta: { title: '首页' } },
      { path: 'projects', name: 'ProjectManage', component: () => import('@/views/ProjectManage.vue'), meta: { title: '项目管理' } },
      { path: 'apis', name: 'ApiManage', component: () => import('@/views/ApiManage.vue'), meta: { title: '接口管理' } },
      { path: 'apis/edit/:id?', name: 'ApiEdit', component: () => import('@/views/ApiEdit.vue'), meta: { title: '接口编辑' } },
      { path: 'cases', name: 'CaseList', component: () => import('@/views/CaseList.vue'), meta: { title: '用例管理' } },
      { path: 'cases/designer/:id?', name: 'CaseDesigner', component: () => import('@/views/CaseDesigner.vue'), meta: { title: '用例编排' } },
      { path: 'cases/suite-designer/:id', name: 'SuiteDesigner', component: () => import('@/views/SuiteDesigner.vue'), meta: { title: '套件编排' } },
      { path: 'datasets', name: 'DatasetManage', component: () => import('@/views/DatasetManage.vue'), meta: { title: '数据集' } },
      { path: 'envs', name: 'EnvManage', component: () => import('@/views/EnvManage.vue'), meta: { title: '环境配置' } },
      { path: 'envs/edit/:id?', name: 'EnvEdit', component: () => import('@/views/EnvEdit.vue'), meta: { title: '环境编辑' } },
      { path: 'executions', name: 'Execution', component: () => import('@/views/Execution.vue'), meta: { title: '执行记录' } },
      { path: 'reports/:id', name: 'ReportDetail', component: () => import('@/views/ReportDetail.vue'), meta: { title: '执行报告' } },
      { path: 'suite-reports/:id', name: 'SuiteReportDetail', component: () => import('@/views/SuiteReportDetail.vue'), meta: { title: '套件报告' } },
      { path: 'dictionary', name: 'DictManage', component: () => import('@/views/DictManage.vue'), meta: { title: '字段字典' } },
      { path: 'files', name: 'FileCenter', component: () => import('@/views/FileCenter.vue'), meta: { title: '文件中心' } },
      { path: 'users', name: 'UserManage', component: () => import('@/views/UserManage.vue'), meta: { title: '用户管理', requireAdmin: true } },
      { path: 'operation-logs', name: 'OperationLog', component: () => import('@/views/OperationLog.vue'), meta: { title: '操作日志', requireAdmin: true } },
    ],
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

// 全局守卫：未登录跳转登录页；首次登录强制改密；需要管理员权限的页面校验角色
router.beforeEach(async (to, _from, next) => {
  const isPublic = to.meta.public === true
  if (isPublic) {
    next()
    return
  }
  if (!getToken()) {
    next({ path: '/login', query: { redirect: to.fullPath } })
    return
  }
  const { useAppStore } = await import('@/stores')
  const store = useAppStore()
  // 确保用户信息已加载（守卫需读取 must_change_password 标记）
  if (!store.user) {
    await store.loadUser()
  }
  // 首次登录强制改密：未改密时只能访问改密页，其他页面一律拦截
  if (store.user?.must_change_password && to.name !== 'ChangePassword') {
    next({ path: '/change-password' })
    return
  }
  // 需要管理员权限的页面校验角色（非管理员回落首页）
  if (to.meta.requireAdmin && store.user?.role !== 'admin') {
    next({ path: '/home' })
    return
  }
  next()
})

// 动态标签标题：index.html 的静态标题仅作首屏兜底
router.afterEach((to) => {
  const title = to.meta.title
  document.title = typeof title === 'string' ? `${title} - fin-api-test 测试平台` : 'fin-api-test 测试平台'
})

export default router

import { createRouter, createWebHistory } from 'vue-router'
import { getToken } from '@/api'

const routes = [
  { path: '/login', name: 'Login', component: () => import('@/views/Login.vue'), meta: { title: '登录', public: true } },
  {
    path: '/',
    component: () => import('@/layouts/MainLayout.vue'),
    children: [
      { path: '', redirect: '/apis' },
      { path: 'projects', name: 'ProjectManage', component: () => import('@/views/ProjectManage.vue'), meta: { title: '项目管理' } },
      { path: 'apis', name: 'ApiManage', component: () => import('@/views/ApiManage.vue'), meta: { title: '接口管理' } },
      { path: 'apis/edit/:id?', name: 'ApiEdit', component: () => import('@/views/ApiEdit.vue'), meta: { title: '接口编辑' } },
      { path: 'cases', name: 'CaseList', component: () => import('@/views/CaseList.vue'), meta: { title: '用例列表' } },
      { path: 'cases/designer/:id?', name: 'CaseDesigner', component: () => import('@/views/CaseDesigner.vue'), meta: { title: '用例编排' } },
      { path: 'envs', name: 'EnvManage', component: () => import('@/views/EnvManage.vue'), meta: { title: '环境配置' } },
      { path: 'envs/edit/:id?', name: 'EnvEdit', component: () => import('@/views/EnvEdit.vue'), meta: { title: '环境编辑' } },
      { path: 'executions', name: 'Execution', component: () => import('@/views/Execution.vue'), meta: { title: '执行记录' } },
      { path: 'reports/:id', name: 'ReportDetail', component: () => import('@/views/ReportDetail.vue'), meta: { title: '执行报告' } },
      { path: 'users', name: 'UserManage', component: () => import('@/views/UserManage.vue'), meta: { title: '用户管理', requireAdmin: true } },
      { path: 'operation-logs', name: 'OperationLog', component: () => import('@/views/OperationLog.vue'), meta: { title: '操作日志', requireAdmin: true } },
    ],
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

// 全局守卫：未登录跳转登录页；需要管理员权限的页面校验角色
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
  // 需要管理员权限的页面，确保用户信息已加载
  if (to.meta.requireAdmin) {
    const { useAppStore } = await import('@/stores')
    const store = useAppStore()
    if (!store.user) {
      await store.loadUser()
    }
    if (store.user?.role !== 'admin') {
      next({ path: '/apis' })
      return
    }
  }
  next()
})

export default router

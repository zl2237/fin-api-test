import { describe, it, expect, beforeEach, vi } from 'vitest'
import { createApp } from 'vue'
import { createPinia, setActivePinia } from 'pinia'

/**
 * 复现调查：流水线部署后（用户刷新页面）数据集页「上次访问记忆」失效，
 * 总是回落到列表首个用例（后端 id 倒序 = 最大 ID 用例）。
 * 两种时序：A) SPA 导航（projectId 已就绪再挂载）；B) F5 直开（projectId 迟到，
 * 先挂载 early-return，后由 MainLayout loadProjects 触发 watch 再 load）。
 */

const CASES = [
  { id: 10, project_id: 1, group_id: null, name: '最大ID用例', dag_config: { nodes: [], edges: [] } },
  { id: 5, project_id: 1, group_id: null, name: '我的用例', dag_config: { nodes: [], edges: [] } },
]
const DS = [
  { id: 8, case_id: 10, name: '数据集8', rows: [{ data: { nodes: {} } }] },
  { id: 9, case_id: 5, name: '数据集9', rows: [{ data: { nodes: {} } }] },
]

vi.mock('@/api', () => ({
  getToken: () => memStore.get('fin_api_test_token') ?? null,
  setToken: (t: string) => void memStore.set('fin_api_test_token', t),
  clearToken: () => void memStore.delete('fin_api_test_token'),
  authApi: { me: vi.fn(async () => ({ id: 1, username: 'u', role: 'admin', must_change_password: false })) },
  projectApi: { list: vi.fn(async () => [{ id: 1, name: 'P1' }]) },
  envApi: { list: vi.fn(async () => []) },
  dictApi: { getMap: vi.fn(async () => ({})) },
  caseApi: { list: vi.fn(async () => CASES), get: vi.fn() },
  caseGroupApi: { list: vi.fn(async () => []) },
  datasetApi: {
    list: vi.fn(async () => DS),
    paramsView: vi.fn(async () => ({ nodes: [], edges: [], orphan_node_ids: [] })),
  },
  apiApi: { contractImpact: vi.fn(async () => []), list: vi.fn(async () => []) },
  fileApi: { list: vi.fn(async () => []) },
  projectVersionApi: { list: vi.fn(async () => ({ items: [] })), },
}))

// element-plus 组件树在 jsdom 下的最小环境
// Node 22 实验性 localStorage 覆盖了 jsdom 实现（undefined），用内存版替换
const memStore = new Map<string, string>()
vi.stubGlobal('localStorage', {
  getItem: (k: string) => memStore.get(k) ?? null,
  setItem: (k: string, v: string) => void memStore.set(k, String(v)),
  removeItem: (k: string) => void memStore.delete(k),
  clear: () => memStore.clear(),
})

beforeEach(() => {
  ;(global as any).ResizeObserver = class { observe() {} unobserve() {} disconnect() {} }
  if (!window.matchMedia) {
    ;(window as any).matchMedia = (q: string) => ({ matches: false, media: q, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {} })
  }
  memStore.clear()
  memStore.set('fin_dataset_last', JSON.stringify({ projectId: 1, caseId: 5, datasetId: 9, nodeId: '' }))
})

async function flushAsync() {
  for (let i = 0; i < 8; i++) await new Promise((r) => setTimeout(r, 0))
}

async function mountView(projectIdAtMount: number | null) {
  const { default: DatasetManage } = await import('../DatasetManage.vue')
  const ElementPlus = (await import('element-plus')).default
  const { useAppStore } = await import('@/stores')
  const pinia = createPinia()
  setActivePinia(pinia)
  const store = useAppStore()
  store.currentProjectId = projectIdAtMount as any
  const app = createApp(DatasetManage as any)
  app.use(pinia)
  app.use(ElementPlus)
  const vm: any = app.mount(document.createElement('div'))
  await flushAsync()
  return { vm, store }
}

describe('DatasetManage 上次访问记忆恢复', () => {
  it('A) 旧单槽格式迁移：localStorage 存旧 {projectId,...} 形状 → 仍可恢复', async () => {
    const { vm } = await mountView(1)
    expect(vm.$.setupState.currentCase?.id).toBe(5)
    expect(vm.$.setupState.current?.id).toBe(9)
  })

  it('B) F5 直开：projectId 迟到（null → 1）→ 仍应恢复记忆', async () => {
    const { vm, store } = await mountView(null)
    // 模拟 MainLayout onMounted 里 loadProjects 完成后 projectId 就位
    store.currentProjectId = 1
    await flushAsync()
    expect(vm.$.setupState.currentCase?.id).toBe(5)
    expect(vm.$.setupState.current?.id).toBe(9)
  })

  it('C) 全链路启动：真实 App + router + MainLayout，F5 直开 /datasets → 仍应恢复记忆', async () => {
    // 登录态 + 项目记忆 + 数据集记忆（模拟用户浏览器里已存在的 localStorage）
    memStore.set('fin_api_test_token', 'tok')
    memStore.set('fin_current_project_id', '1')
    const { createApp } = await import('vue')
    const { createPinia } = await import('pinia')
    const ElementPlus = (await import('element-plus')).default
    const { default: App } = await import('@/App.vue')
    const { default: router } = await import('@/router')
    const app = createApp(App as any)
    app.use(createPinia())
    app.use(router)
    app.use(ElementPlus)
    const div = document.createElement('div')
    document.body.appendChild(div)
    await app.mount(div) // App.mount 返回根实例；await 等初始导航完成
    await router.isReady()
    await router.push('/datasets')
    await flushAsync()
    // 选中节点应是记忆的「我的用例」，而不是列表首位（最大ID）用例
    const on = div.querySelector('.side-node.on')
    expect(on?.textContent).toContain('我的用例')
    expect(on?.textContent).not.toContain('最大ID用例')
  })

  it('D) 新分槽格式：{slots: {"user|project": {...}}} → 按当前槽恢复', async () => {
    memStore.clear()
    memStore.set('fin_dataset_last', JSON.stringify({
      slots: { '|1': { caseId: 5, datasetId: 9, nodeId: '' }, '|9': { caseId: 10, datasetId: 8, nodeId: '' } },
    }))
    const { vm } = await mountView(1)
    expect(vm.$.setupState.currentCase?.id).toBe(5)
    expect(vm.$.setupState.current?.id).toBe(9)
  })

  it('E) 跨项目隔离：切到其他项目再切回 → 本项目记忆不被清掉（单槽自毁缺陷回归）', async () => {
    memStore.clear()
    memStore.set('fin_dataset_last', JSON.stringify({
      slots: { '|1': { caseId: 5, datasetId: 9, nodeId: '' } },
    }))
    const { vm, store } = await mountView(1)
    expect(vm.$.setupState.currentCase?.id).toBe(5)
    // 切去项目 2（view 内部落到列表首位并写 |2 槽），再切回项目 1
    store.currentProjectId = 2
    await flushAsync()
    expect(vm.$.setupState.currentCase?.id).toBe(10) // 项目 2 无记忆 → 列表首位
    store.currentProjectId = 1
    await flushAsync()
    // 关键断言：|1 槽未被项目 2 的写入覆盖/清除
    expect(vm.$.setupState.currentCase?.id).toBe(5)
    expect(vm.$.setupState.current?.id).toBe(9)
  })
})

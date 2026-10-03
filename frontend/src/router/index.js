import { createRouter, createWebHistory } from 'vue-router'

import { useAuthStore } from '../stores/auth'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', name: 'login', component: () => import('../views/LoginView.vue'), meta: { public: true, title: '登录' } },
    { path: '/register', name: 'register', component: () => import('../views/RegisterView.vue'), meta: { public: true, title: '注册' } },
    { path: '/', name: 'dashboard', component: () => import('../views/DashboardView.vue'), meta: { title: 'Dashboard' } },
    { path: '/datasets', name: 'datasets', component: () => import('../views/DatasetListView.vue'), meta: { title: '数据集' } },
    { path: '/datasets/upload', name: 'dataset-upload', component: () => import('../views/DatasetUploadView.vue'), meta: { title: '上传数据' } },
    { path: '/datasets/:datasetId', name: 'dataset-detail', component: () => import('../views/DatasetDetailView.vue'), meta: { title: '数据集详情' }, props: true },
    { path: '/analysis/:sessionId?', name: 'analysis', component: () => import('../views/AnalysisWorkspaceView.vue'), meta: { title: '智能分析' } },
    { path: '/sessions', name: 'sessions', component: () => import('../views/SessionsView.vue'), meta: { title: '分析会话' } },
    { path: '/history', name: 'history', component: () => import('../views/HistoryView.vue'), meta: { title: '分析历史' } },
    { path: '/history/:recordId', name: 'history-detail', component: () => import('../views/HistoryDetailView.vue'), props: true, meta: { title: '分析记录详情' } },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
  scrollBehavior() {
    return { top: 0 }
  },
})

router.beforeEach(async (to) => {
  const auth = useAuthStore()
  await auth.initialize()

  if (!to.meta.public && auth.authStatus !== 'authenticated') {
    return { name: 'login', query: { redirect: to.fullPath } }
  }
  if (to.meta.public && auth.authStatus === 'authenticated') return { name: 'dashboard' }
  return true
})

router.afterEach((to) => {
  document.title = `${to.meta.title || '页面'} — DataLens Agent`
})

export default router

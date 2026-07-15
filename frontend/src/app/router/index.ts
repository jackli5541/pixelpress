import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import ProjectUploadPage from '@/features/project-upload/pages/ProjectUploadPage.vue'
import AlbumResumePage from '@/features/project-upload/pages/AlbumResumePage.vue'
import PhotoCleaningPage from '@/features/photo-cleaning/pages/PhotoCleaningPage.vue'
import ChapterClusteringPage from '@/features/chapter-clustering/pages/ChapterClusteringPage.vue'
import PagePlanningPage from '@/features/page-planning/pages/PagePlanningPage.vue'
import ExportOrderPage from '@/features/export-order/pages/ExportOrderPage.vue'
import LoginPage from '@/features/auth/pages/LoginPage.vue'
import AdminLayout from '@/modules/admin/AdminLayout.vue'
import AdminProjectsPage from '@/modules/admin/pages/AdminProjectsPage.vue'
import AdminProjectFormPage from '@/modules/admin/pages/AdminProjectFormPage.vue'
import AdminModelsPage from '@/modules/admin/pages/AdminModelsPage.vue'
import AdminTasksPage from '@/modules/admin/pages/AdminTasksPage.vue'
import AdminAuditLogsPage from '@/modules/admin/pages/AdminAuditLogsPage.vue'
import { authResolved, currentUser, loadCurrentUser } from '@/shared/auth'
import { hasAccessToken } from '@/shared/api/http'

const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'login',
    component: LoginPage,
    meta: { guestOnly: true },
  },
  {
    path: '/',
    name: 'home',
    component: ProjectUploadPage,
  },
  {
    path: '/albums/create',
    name: 'album-create',
    component: ProjectUploadPage,
    meta: { requiresAuth: true },
  },
  {
    path: '/albums/:id/resume',
    name: 'album-resume',
    component: AlbumResumePage,
    meta: { requiresAuth: true },
  },
  {
    path: '/albums/:id/upload',
    name: 'project-upload',
    component: ProjectUploadPage,
    meta: { requiresAuth: true },
  },
  {
    path: '/albums/:id/cleaning',
    name: 'photo-cleaning',
    component: PhotoCleaningPage,
    meta: { requiresAuth: true },
  },
  {
    path: '/albums/:id/chapters',
    name: 'chapter-clustering',
    component: ChapterClusteringPage,
    meta: { requiresAuth: true },
  },
  {
    path: '/albums/:id/planning',
    name: 'page-planning',
    component: PagePlanningPage,
    meta: { requiresAuth: true },
  },
  {
    path: '/albums/:id/export',
    name: 'export-order',
    component: ExportOrderPage,
    meta: { requiresAuth: true },
  },
  {
    path: '/admin',
    component: AdminLayout,
    meta: { requiresAuth: true, requiresRole: 'admin' },
    children: [
      { path: '', redirect: '/admin/projects' },
      { path: 'projects', name: 'admin-projects', component: AdminProjectsPage },
      { path: 'projects/:id', name: 'admin-project-detail', component: AdminProjectFormPage },
      { path: 'models', name: 'admin-models', component: AdminModelsPage },
      { path: 'audit-logs', name: 'admin-audit-logs', component: AdminAuditLogsPage },
      { path: 'tasks', name: 'admin-tasks', component: AdminTasksPage },
    ],
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

function normalizeRedirectTarget(target: unknown) {
  return typeof target === 'string' && target.startsWith('/') ? target : '/'
}

router.beforeEach(async (to) => {
  if (!authResolved.value && !currentUser.value && hasAccessToken()) {
    await loadCurrentUser()
  }

  const requiresAuth = Boolean(to.meta.requiresAuth)
  const guestOnly = Boolean(to.meta.guestOnly)
  const requiresRole = typeof to.meta.requiresRole === 'string' ? to.meta.requiresRole : null
  const isLoggedIn = Boolean(currentUser.value)

  if (requiresAuth && !isLoggedIn) {
    return {
      name: 'login',
      query: { redirect: to.fullPath },
    }
  }

  if (guestOnly && isLoggedIn) {
    return normalizeRedirectTarget(to.query.redirect)
  }

  if (requiresRole && currentUser.value?.role !== requiresRole) {
    return '/'
  }

  return true
})

export default router

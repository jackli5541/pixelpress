import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import ProjectUploadPage from '@/features/project-upload/pages/ProjectUploadPage.vue'
import AlbumResumePage from '@/features/project-upload/pages/AlbumResumePage.vue'
import PhotoCleaningPage from '@/features/photo-cleaning/pages/PhotoCleaningPage.vue'
import ChapterClusteringPage from '@/features/chapter-clustering/pages/ChapterClusteringPage.vue'
import PagePlanningPage from '@/features/page-planning/pages/PagePlanningPage.vue'
import ExportOrderPage from '@/features/export-order/pages/ExportOrderPage.vue'
import LoginPage from '@/features/auth/pages/LoginPage.vue'
import AdminTasksPage from '@/modules/admin/pages/AdminTasksPage.vue'
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
    redirect: '/admin/projects',
  },
  {
    path: '/admin/projects',
    name: 'admin-projects',
    component: AdminTasksPage,
    meta: { requiresAuth: true, requiresRole: 'admin' },
  },
  {
    path: '/admin/models',
    name: 'admin-models',
    component: AdminTasksPage,
    meta: { requiresAuth: true, requiresRole: 'admin' },
  },
  {
    path: '/admin/audit-logs',
    name: 'admin-audit-logs',
    component: AdminTasksPage,
    meta: { requiresAuth: true, requiresRole: 'admin' },
  },
  {
    path: '/admin/tasks',
    name: 'admin-tasks',
    component: AdminTasksPage,
    meta: { requiresAuth: true, requiresRole: 'admin' },
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

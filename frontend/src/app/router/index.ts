import { createRouter, createWebHistory } from 'vue-router'
import ProjectUploadPage from '@/features/project-upload/pages/ProjectUploadPage.vue'
import PhotoCleaningPage from '@/features/photo-cleaning/pages/PhotoCleaningPage.vue'
import ChapterClusteringPage from '@/features/chapter-clustering/pages/ChapterClusteringPage.vue'
import PagePlanningPage from '@/features/page-planning/pages/PagePlanningPage.vue'
import ExportOrderPage from '@/features/export-order/pages/ExportOrderPage.vue'
import AdminTasksPage from '@/modules/admin/pages/AdminTasksPage.vue'

const routes = [
  {
    path: '/',
    name: 'home',
    component: ProjectUploadPage,
  },
  {
    path: '/albums/create',
    name: 'album-create',
    component: ProjectUploadPage,
  },
  {
    path: '/albums/:id/upload',
    name: 'project-upload',
    component: ProjectUploadPage,
  },
  {
    path: '/albums/:id/cleaning',
    name: 'photo-cleaning',
    component: PhotoCleaningPage,
  },
  {
    path: '/albums/:id/chapters',
    name: 'chapter-clustering',
    component: ChapterClusteringPage,
  },
  {
    path: '/albums/:id/planning',
    name: 'page-planning',
    component: PagePlanningPage,
  },
  {
    path: '/albums/:id/export',
    name: 'export-order',
    component: ExportOrderPage,
  },
  {
    path: '/admin/tasks',
    name: 'admin-tasks',
    component: AdminTasksPage,
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router

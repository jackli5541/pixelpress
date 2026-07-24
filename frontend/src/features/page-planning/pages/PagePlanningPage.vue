<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import SectionCard from '@/shared/components/SectionCard.vue'
import StoryHero from '@/shared/components/StoryHero.vue'
import WorkflowStepper from '@/shared/components/WorkflowStepper.vue'
import ProtectedImage from '@/shared/components/ProtectedImage.vue'
import { httpDelete, httpGet, httpPatch, httpPost } from '@/shared/api/http'
import { usePhotoDrag } from '@/shared/composables/usePhotoDrag'
import AlbumTaskStatusCard from '@/shared/components/AlbumTaskStatusCard.vue'
import { useAlbumTaskMonitor } from '@/shared/composables/useAlbumTaskMonitor'
import type { TaskItem } from '@/shared/types/album'
import PageSpreadEditor, { type PageLayoutMeta } from '@/features/page-planning/components/PageSpreadEditor.vue'

interface PhotoItem {
  id: string
  filename: string
  size: number
  url: string
}

interface PageItem {
  id: string
  page_number: number
  template: string
  photo_ids: string[]
  photo_count: number
  chapter_id: string | null
  preview_snippet?: string
  preview_available?: boolean
  status: string
  meta: PageLayoutMeta
}

interface ChapterItem {
  id: string
  name: string
  description: string
  photo_ids: string[]
}

const ORPHAN_ID = '__orphan__'
const route = useRoute()
const router = useRouter()

const pages = ref<PageItem[]>([])
const allPhotos = ref<PhotoItem[]>([])
const chapters = ref<ChapterItem[]>([])
const albumStatus = ref('draft')
const bookSize = ref('A4')
const loading = ref(false)
const actionLoading = ref(false)
const errorMessage = ref('')
const successMessage = ref('')
const showPreview = ref(false)
const savingPageId = ref('')
const expandedChapter = ref<string | null>(null)
const activeTaskType = ref<'plan_pages' | 'render_layout' | null>(null)

const albumId = computed(() => {
  const id = route.params.id
  return typeof id === 'string' ? id : ''
})

const needChapters = computed(() => ['draft', 'uploaded', 'cleaned'].includes(albumStatus.value))
const pageAspectRatio = computed(() => bookSize.value === 'square_10inch' ? 1 : bookSize.value === 'A5' ? 148 / 210 : 210 / 297)

const templateLabels: Record<string, string> = {
  full_page: '整页',
  half_half: '对半',
  two_column: '双栏',
  grid_3: '三图',
  grid_4: '四图',
  one_large_two_small: '一大两小',
}
const templateKeysByPhotoCount: Record<number, string[]> = {
  1: ['full_page'],
  2: ['half_half', 'two_column'],
  3: ['grid_3', 'one_large_two_small'],
  4: ['grid_4'],
}

function templateOptions(page: PageItem) {
  const count = getPhotos(page.photo_ids || []).length
  const keys = templateKeysByPhotoCount[count] || [page.template]
  return keys.map((key) => ({ key, label: templateLabels[key] || key }))
}

interface ChapterPageGroup {
  chapter: ChapterItem
  pages: PageItem[]
  photos: PhotoItem[]
  unassignedPhotos: PhotoItem[]
}

const chapterGroups = computed<ChapterPageGroup[]>(() =>
  chapters.value.map((chapter) => {
    const chapterPages = pages.value.filter((page) => page.chapter_id === chapter.id).sort((a, b) => (a.page_number || 0) - (b.page_number || 0))
    const pagePhotoIds = new Set<string>()
    chapterPages.forEach((page) => (page.photo_ids || []).forEach((id) => pagePhotoIds.add(id)))
    const chapterPhotos = getPhotos(chapter.photo_ids || [])
    const unassignedPhotos = chapterPhotos.filter((photo) => !pagePhotoIds.has(photo.id))
    return {
      chapter,
      pages: chapterPages,
      photos: chapterPhotos,
      unassignedPhotos,
    }
  }),
)

const orphanPages = computed(() => pages.value.filter((page) => !page.chapter_id).sort((a, b) => (a.page_number || 0) - (b.page_number || 0)))

const allPagePhotoIds = computed(() => {
  const ids = new Set<string>()
  pages.value.forEach((page) => (page.photo_ids || []).forEach((id) => ids.add(id)))
  return ids
})

const totalUnassignedPhotos = computed(() => allPhotos.value.filter((photo) => !allPagePhotoIds.value.has(photo.id)))
const taskTypeLabels: Record<string, string> = {
  plan_pages: '页面规划',
  render_layout: '排版渲染',
}
const { latestTask, refreshTask, startPolling, stopPolling } = useAlbumTaskMonitor({
  albumId,
  matches: (task) => (activeTaskType.value ? task.task_type === activeTaskType.value : ['plan_pages', 'render_layout'].includes(task.task_type)),
})

async function applyPlanningTaskOutcome(successText: string, task = latestTask.value) {
  await loadData()
  if (task?.task_status === 'succeeded') {
    successMessage.value = successText
    setTimeout(() => {
      successMessage.value = ''
    }, 3000)
  }
}
const activeTask = computed(() => latestTask.value ?? null)
const activeTaskLabel = computed(() => {
  if (!activeTask.value) return ''
  return taskTypeLabels[activeTask.value.task_type] || activeTask.value.task_type
})

function getPhotos(idList: string[]) {
  const idSet = new Set(idList)
  return allPhotos.value.filter((photo) => idSet.has(photo.id))
}

async function loadLatestTask(taskType: 'plan_pages' | 'render_layout', taskId?: string) {
  activeTaskType.value = taskType
  return await refreshTask(taskId)
}

function startTaskPolling(
  taskType: 'plan_pages' | 'render_layout',
  taskId?: string,
  onTerminal?: (task?: TaskItem | null) => void | Promise<void>,
) {
  activeTaskType.value = taskType
  startPolling(taskId, async (task) => {
    await onTerminal?.(task)
  })
}

async function loadData() {
  if (!albumId.value) return
  loading.value = true
  errorMessage.value = ''
  try {
    const [pageResponse, photoResponse, albumResponse, chapterResponse] = await Promise.all([
      httpGet<PageItem[]>(`/albums/${albumId.value}/pages`),
      httpGet<{ items: PhotoItem[] }>(`/albums/${albumId.value}/photos?recommendation=keep`),
      httpGet<any>(`/albums/${albumId.value}`),
      httpGet<ChapterItem[]>(`/albums/${albumId.value}/chapters`),
    ])
    pages.value = (pageResponse.data || []).sort((a, b) => (a.page_number || 0) - (b.page_number || 0))
    allPhotos.value = photoResponse.data.items || []
    chapters.value = chapterResponse.data || []
    albumStatus.value = albumResponse.data?.status || 'draft'
    bookSize.value = albumResponse.data?.book_size || 'A4'
  } catch (error: any) {
    errorMessage.value = error.message
  } finally {
    loading.value = false
  }
}

function goBack() {
  void router.push(`/albums/${albumId.value}/chapters`)
}

async function startPlan() {
  if (!albumId.value) return
  actionLoading.value = true
  errorMessage.value = ''
  successMessage.value = ''
  try {
    const response = await httpPost<{ task: { id: string } }>(`/albums/${albumId.value}/plan`)
    const taskId = response.data.task.id
    await loadLatestTask('plan_pages', taskId)
    startTaskPolling('plan_pages', taskId, async (task) => {
      await applyPlanningTaskOutcome('页面规划完成。', task ?? latestTask.value)
    })
  } catch (error: any) {
    errorMessage.value = error.message
    await refreshTask()
  } finally {
    actionLoading.value = false
  }
}

async function startRender() {
  if (!albumId.value) return
  actionLoading.value = true
  errorMessage.value = ''
  successMessage.value = ''
  try {
    const response = await httpPost<{ task: { id: string } }>(`/albums/${albumId.value}/render`)
    const taskId = response.data.task.id
    await loadLatestTask('render_layout', taskId)
    startTaskPolling('render_layout', taskId, async (task) => {
      await applyPlanningTaskOutcome('书页渲染完成。', task ?? latestTask.value)
    })
  } catch (error: any) {
    errorMessage.value = error.message
    await refreshTask()
  } finally {
    actionLoading.value = false
  }
}

async function changeTemplate(page: PageItem, template: string) {
  if (template === page.template) return
  if (!confirm('切换模板会重置本页已经手工调整的位置和大小，确定继续吗？')) return
  try {
    const response = await httpPatch<PageItem>(`/albums/${albumId.value}/pages/${page.id}`, { template })
    page.template = response.data.template
    await loadData()
  } catch (error: any) {
    errorMessage.value = error.message
  }
}

async function movePhoto(photoId: string, targetPageId: string) {
  if (targetPageId === ORPHAN_ID) {
    errorMessage.value = '当前版本暂不支持直接拖回未分配区，可通过删除页面释放照片。'
    return
  }
  try {
    await httpPost(`/albums/${albumId.value}/pages/move-photos`, { photo_ids: [photoId], target_page_id: targetPageId })
    await loadData()
  } catch (error: any) {
    errorMessage.value = error.message
  }
}

async function createPage(chapterId: string | null = null) {
  try {
    await httpPost(`/albums/${albumId.value}/pages`, { template: 'grid_3', photo_ids: [], chapter_id: chapterId })
    await loadData()
  } catch (error: any) {
    errorMessage.value = error.message
  }
}

async function deletePage(id: string) {
  if (!confirm('删除该页面后，其中照片会重新回到未分配状态。确定继续吗？')) return
  try {
    await httpDelete(`/albums/${albumId.value}/pages/${id}`)
    await loadData()
  } catch (error: any) {
    errorMessage.value = error.message
  }
}

function loadPreview() {
  showPreview.value = !showPreview.value
}

async function savePageLayout(page: PageItem, meta: PageLayoutMeta) {
  savingPageId.value = page.id
  errorMessage.value = ''
  try {
    const response = await httpPatch<PageItem>(`/albums/${albumId.value}/pages/${page.id}`, { meta })
    page.meta = response.data.meta
    page.status = response.data.status
    albumStatus.value = 'planned'
  } catch (error: any) {
    errorMessage.value = `排版未保存：${error.message}`
    await loadData()
  } finally {
    if (savingPageId.value === page.id) savingPageId.value = ''
  }
}

function goNext() {
  void router.push(`/albums/${albumId.value}/export`)
}

const { isDragging, onDragStart, onDragOver, onDragLeave, onDrop, onDragEnd, getDragPhotoClass, getDropTargetClass } = usePhotoDrag({
  onPhotoMove: movePhoto,
  orphanAreaId: ORPHAN_ID,
})

onMounted(async () => {
  await loadData()
  await refreshTask()
})
watch(
  () => albumId.value,
  async () => {
    stopPolling()
    activeTaskType.value = null
    await loadData()
    await refreshTask()
  },
)
</script>

<template>
  <WorkflowStepper v-if="albumId" :album-id="albumId" :album-status="albumStatus" />

  <div class="space-y-6">
    <StoryHero
      eyebrow="Book Layout"
      title="把章节编排成真正可翻阅的书页"
      description="这一阶段不只是塞满照片，而是安排每一页的呼吸、轻重与节奏。你可以自动规划，也可以人工微调模板和照片归属。"
    >
      <div class="grid gap-4 md:grid-cols-4">
        <div class="story-panel rounded-[24px] px-4 py-4">
          <p class="font-story text-3xl text-[var(--story-gold-soft)]">{{ chapters.length }}</p>
          <p class="mt-2 text-sm text-[var(--story-text)]">章节</p>
        </div>
        <div class="story-panel rounded-[24px] px-4 py-4">
          <p class="font-story text-3xl text-[var(--story-gold-soft)]">{{ pages.length }}</p>
          <p class="mt-2 text-sm text-[var(--story-text)]">书页</p>
        </div>
        <div class="story-panel rounded-[24px] px-4 py-4">
          <p class="font-story text-3xl text-[var(--story-gold-soft)]">{{ totalUnassignedPhotos.length }}</p>
          <p class="mt-2 text-sm text-[var(--story-text)]">未排版镜头</p>
        </div>
        <div class="story-panel rounded-[24px] px-4 py-4">
          <p class="font-story text-3xl text-[var(--story-gold-soft)]">{{ albumStatus }}</p>
          <p class="mt-2 text-sm text-[var(--story-text)]">当前状态</p>
        </div>
      </div>
    </StoryHero>

    <SectionCard
      title="页面编排"
      description="每个章节都可以独立生成书页。你可以拖动照片到目标页面，也可以为不同页面调整模板。"
      tone="film"
      eyebrow="Step 4"
    >
      <div v-if="!loading && needChapters" class="rounded-[22px] border border-[#8e6732] bg-[rgba(170,120,44,0.14)] px-4 py-4 text-sm text-[var(--story-muted)]">
        请先完成章节整理，再进入页面编排。
        <button class="story-button-secondary ml-3 px-4 py-2 text-sm" @click="goBack">返回章节页</button>
      </div>

      <div class="mt-4 flex flex-wrap items-center gap-3">
        <button class="story-button px-6 py-3 text-sm" :disabled="!albumId || actionLoading" @click="startPlan">
          自动规划书页
        </button>
        <button class="story-button-secondary px-6 py-3 text-sm" :disabled="!albumId || actionLoading" @click="startRender">
          渲染整册
        </button>
        <button class="story-button-secondary px-6 py-3 text-sm" :disabled="!albumId || !pages.length" @click="loadPreview">
          {{ showPreview ? '收起直接编辑' : '直接编辑双页预览' }}
        </button>
        <button v-if="pages.length > 0" class="story-button-secondary ml-auto px-6 py-3 text-sm" @click="goNext">
          进入导出 →
        </button>
      </div>

      <div class="mt-4">
        <AlbumTaskStatusCard
          :task="activeTask"
          :title="activeTaskLabel || '页面任务'"
          running-hint="任务进行中，页面会自动轮询最新状态。"
          empty-text="执行自动规划或渲染后，这里会显示最近一次页面任务状态与结果摘要。"
        />
      </div>

      <div v-if="successMessage || errorMessage" class="mt-4 flex flex-col gap-3">
        <p v-if="successMessage" class="rounded-[18px] bg-[#dcead5] px-4 py-3 text-sm text-[#47673d]">{{ successMessage }}</p>
        <p v-if="errorMessage" class="rounded-[18px] bg-[#f6d9d3] px-4 py-3 text-sm text-[#8b4339]">{{ errorMessage }}</p>
      </div>

      <p v-if="isDragging" class="mt-4 text-xs text-[var(--story-faint)]">拖动照片到目标页面，即可调整排版归属。</p>
    </SectionCard>

    <div v-if="chapterGroups.length > 0" class="space-y-4">
      <article v-for="group in chapterGroups" :key="group.chapter.id" class="story-panel overflow-hidden rounded-[28px]">
        <div class="flex flex-wrap items-center justify-between gap-4 px-5 py-5">
          <div>
            <p class="font-story text-4xl text-[var(--story-gold-soft)]">{{ group.chapter.name }}</p>
            <p class="mt-2 text-sm text-[var(--story-muted)]">
              {{ group.pages.length }} 页 | {{ group.photos.length }} 张章节照片 | {{ group.unassignedPhotos.length }} 张待排版
            </p>
          </div>
          <div class="flex gap-2">
            <button class="story-button-secondary px-4 py-2 text-sm" @click="expandedChapter = expandedChapter === group.chapter.id ? null : group.chapter.id">
              {{ expandedChapter === group.chapter.id ? '收起章节' : '展开章节' }}
            </button>
            <button class="story-button-secondary px-4 py-2 text-sm" @click="createPage(group.chapter.id)">新增页面</button>
          </div>
        </div>

        <div v-if="expandedChapter === group.chapter.id" class="border-t border-[rgba(224,177,106,0.14)] px-5 py-5">
          <div v-if="group.pages.length > 0" class="grid gap-4 lg:grid-cols-2 xl:grid-cols-3">
            <article
              v-for="page in group.pages"
              :key="page.id"
              class="overflow-hidden rounded-[24px] border border-[rgba(224,177,106,0.16)] bg-[rgba(255,255,255,0.03)]"
              :class="getDropTargetClass(page.id)"
              @dragover.prevent="(event: DragEvent) => onDragOver(event, page.id)"
              @dragleave="() => onDragLeave(page.id)"
              @drop="(event: DragEvent) => onDrop(event, page.id)"
            >
              <div class="flex items-center justify-between gap-3 px-4 py-4">
                <div>
                  <p class="text-xs uppercase tracking-[0.22em] text-[var(--story-faint)]">Page {{ page.page_number }}</p>
                  <p class="mt-2 text-sm text-[var(--story-text)]">{{ getPhotos(page.photo_ids || []).length }} 张照片</p>
                </div>
                <div class="flex items-center gap-2">
                  <select
                    :value="page.template"
                    :disabled="templateOptions(page).length < 2"
                    class="rounded-full border border-[rgba(224,177,106,0.18)] bg-[rgba(255,255,255,0.06)] px-3 py-2 text-xs text-[var(--story-text)] outline-none"
                    @change="changeTemplate(page, ($event.target as HTMLSelectElement).value)"
                  >
                    <option v-for="option in templateOptions(page)" :key="option.key" :value="option.key">{{ option.label }}</option>
                  </select>
                  <button class="rounded-full bg-[#f2d8d2] px-3 py-2 text-xs text-[#8b4339]" @click="deletePage(page.id)">删除</button>
                </div>
              </div>

              <div
                v-if="page.preview_available && page.preview_snippet"
                class="border-y border-[rgba(224,177,106,0.12)] bg-white/80"
                style="max-height: 140px; overflow: hidden"
                v-html="page.preview_snippet"
              />

              <div class="px-4 py-4">
                <div v-if="getPhotos(page.photo_ids || []).length === 0" class="rounded-[18px] border border-dashed border-[rgba(224,177,106,0.18)] px-4 py-8 text-center text-sm text-[var(--story-muted)]">
                  把章节照片拖到这里
                </div>
                <div v-else class="grid grid-cols-4 gap-2">
                  <div
                    v-for="photo in getPhotos(page.photo_ids || [])"
                    :key="photo.id"
                    class="overflow-hidden rounded-[16px]"
                    :class="getDragPhotoClass(photo.id)"
                    draggable="true"
                    @dragstart="(event: DragEvent) => onDragStart(event, photo.id, page.id)"
                    @dragend="onDragEnd"
                  >
                    <ProtectedImage :src="photo.url" :alt="photo.filename" class="h-20 w-full object-cover pointer-events-none" />
                  </div>
                </div>
              </div>
            </article>
          </div>

          <div v-else class="rounded-[22px] border border-dashed border-[rgba(224,177,106,0.18)] px-5 py-10 text-center text-sm text-[var(--story-muted)]">
            这个章节还没有页面。点击“新增页面”或先执行自动规划。
          </div>

          <div v-if="group.unassignedPhotos.length > 0" class="mt-5 rounded-[22px] border border-[rgba(224,177,106,0.16)] bg-[rgba(255,255,255,0.03)] px-4 py-4">
            <p class="text-sm text-[var(--story-text)]">章节内待排版镜头</p>
            <div class="mt-3 flex flex-wrap gap-2">
              <div
                v-for="photo in group.unassignedPhotos"
                :key="photo.id"
                class="overflow-hidden rounded-[16px]"
                :class="getDragPhotoClass(photo.id)"
                draggable="true"
                @dragstart="(event: DragEvent) => onDragStart(event, photo.id, group.chapter.id)"
                @dragend="onDragEnd"
              >
                <ProtectedImage :src="photo.url" :alt="photo.filename" class="h-20 w-20 object-cover pointer-events-none" />
              </div>
            </div>
          </div>
        </div>
      </article>
    </div>

    <SectionCard
      v-if="orphanPages.length > 0"
      title="未归属章节的书页"
      :description="`${orphanPages.length} 个书页尚未归入任何章节，但已经完成分页。`"
      tone="film"
      eyebrow="Ungrouped Pages"
    >
      <div class="mb-4 flex justify-end">
        <button class="story-button-secondary px-4 py-2 text-sm" @click="createPage()">新增空白页面</button>
      </div>

      <div class="grid gap-4 lg:grid-cols-2 xl:grid-cols-3">
        <article
          v-for="page in orphanPages"
          :key="page.id"
          class="overflow-hidden rounded-[24px] border border-[rgba(224,177,106,0.16)] bg-[rgba(255,255,255,0.03)]"
          :class="getDropTargetClass(page.id)"
          @dragover.prevent="(event: DragEvent) => onDragOver(event, page.id)"
          @dragleave="() => onDragLeave(page.id)"
          @drop="(event: DragEvent) => onDrop(event, page.id)"
        >
          <div class="flex items-center justify-between gap-3 px-4 py-4">
            <div>
              <p class="text-xs uppercase tracking-[0.22em] text-[var(--story-faint)]">Page {{ page.page_number }}</p>
              <p class="mt-2 text-sm text-[var(--story-text)]">{{ getPhotos(page.photo_ids || []).length }} 张照片</p>
            </div>
            <div class="flex items-center gap-2">
              <select
                :value="page.template"
                :disabled="templateOptions(page).length < 2"
                class="rounded-full border border-[rgba(224,177,106,0.18)] bg-[rgba(255,255,255,0.06)] px-3 py-2 text-xs text-[var(--story-text)] outline-none"
                @change="changeTemplate(page, ($event.target as HTMLSelectElement).value)"
              >
                <option v-for="option in templateOptions(page)" :key="option.key" :value="option.key">{{ option.label }}</option>
              </select>
              <button class="rounded-full bg-[#f2d8d2] px-3 py-2 text-xs text-[#8b4339]" @click="deletePage(page.id)">删除</button>
            </div>
          </div>

          <div
            v-if="page.preview_available && page.preview_snippet"
            class="border-y border-[rgba(224,177,106,0.12)] bg-white/80"
            style="max-height: 140px; overflow: hidden"
            v-html="page.preview_snippet"
          />

          <div class="px-4 py-4">
            <div v-if="getPhotos(page.photo_ids || []).length === 0" class="rounded-[18px] border border-dashed border-[rgba(224,177,106,0.18)] px-4 py-8 text-center text-sm text-[var(--story-muted)]">
              把照片拖到这里
            </div>
            <div v-else class="grid grid-cols-4 gap-2">
              <div
                v-for="photo in getPhotos(page.photo_ids || [])"
                :key="photo.id"
                class="overflow-hidden rounded-[16px]"
                :class="getDragPhotoClass(photo.id)"
                draggable="true"
                @dragstart="(event: DragEvent) => onDragStart(event, photo.id, page.id)"
                @dragend="onDragEnd"
              >
                <ProtectedImage :src="photo.url" :alt="photo.filename" class="h-20 w-full object-cover pointer-events-none" />
              </div>
            </div>
          </div>
        </article>
      </div>
    </SectionCard>

    <SectionCard
      v-if="totalUnassignedPhotos.length > 0 && pages.length > 0"
      title="未进入书页的镜头"
      :description="`${totalUnassignedPhotos.length} 张照片还没有排版到任何页面。`"
      tone="accent"
      eyebrow="Loose Frames"
    >
      <div class="flex flex-wrap gap-3">
        <div
          v-for="photo in totalUnassignedPhotos"
          :key="photo.id"
          class="overflow-hidden rounded-[18px] border border-dashed border-[rgba(79,59,42,0.22)] bg-white/70"
          :class="getDragPhotoClass(photo.id)"
          draggable="true"
          @dragstart="(event: DragEvent) => onDragStart(event, photo.id, ORPHAN_ID)"
          @dragend="onDragEnd"
        >
          <ProtectedImage :src="photo.url" :alt="photo.filename" class="h-20 w-20 object-cover pointer-events-none" />
        </div>
      </div>
    </SectionCard>

    <div v-if="!loading && !pages.length && albumId" class="story-panel rounded-[28px] px-6 py-12 text-center">
      <p class="font-story text-4xl text-[var(--story-gold-soft)]">No Pages Yet</p>
      <p class="mt-3 text-sm text-[var(--story-muted)]">先运行自动规划，或按章节手动新增页面。</p>
    </div>

    <div v-if="showPreview && pages.length" class="fixed inset-0 z-50 flex flex-col bg-[#171411]">
      <header class="flex shrink-0 flex-wrap items-center justify-between gap-4 border-b border-white/10 bg-[#211d19] px-5 py-4 text-white shadow-xl md:px-8">
        <div>
          <p class="text-xs uppercase tracking-[0.24em] text-[#d6b47c]">Live Book Editor</p>
          <h2 class="mt-1 font-story text-3xl">双页直接编辑</h2>
          <p class="mt-1 text-xs text-white/60">拖动照片或描述框调整位置，修改会自动保存；页码固定在底部中央。</p>
        </div>
        <div class="flex items-center gap-3">
          <span v-if="savingPageId" class="text-xs text-[#d6b47c]">正在保存…</span>
          <button class="rounded-full border border-white/15 bg-white/10 px-5 py-2.5 text-sm transition hover:bg-white/20" @click="showPreview = false">
            关闭预览
          </button>
        </div>
      </header>
      <main class="min-h-0 flex-1 overflow-auto px-3 py-5 md:px-8 md:py-8">
        <PageSpreadEditor :pages="pages" :photos="allPhotos" :saving-page-id="savingPageId" :page-aspect-ratio="pageAspectRatio" @save="savePageLayout" />
      </main>
    </div>
  </div>
</template>

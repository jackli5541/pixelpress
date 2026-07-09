<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import SectionCard from '@/shared/components/SectionCard.vue'
import StoryHero from '@/shared/components/StoryHero.vue'
import WorkflowStepper from '@/shared/components/WorkflowStepper.vue'
import ProtectedImage from '@/shared/components/ProtectedImage.vue'
import AlbumTaskStatusCard from '@/shared/components/AlbumTaskStatusCard.vue'
import { httpDelete, httpGet, httpPatch, httpPost } from '@/shared/api/http'
import { usePhotoDrag } from '@/shared/composables/usePhotoDrag'
import { useAlbumTaskMonitor } from '@/shared/composables/useAlbumTaskMonitor'

interface PhotoItem {
  id: string
  filename: string
  size: number
  url: string
}

interface ChapterItem {
  id: string
  name: string
  description: string
  order: number
  photo_ids: string[]
}

const ORPHAN_ID = '__orphan__'

const route = useRoute()
const router = useRouter()

const chapters = ref<ChapterItem[]>([])
const allPhotos = ref<PhotoItem[]>([])
const albumStatus = ref('draft')
const loading = ref(false)
const actionLoading = ref(false)
const errorMessage = ref('')
const successMessage = ref('')
const expandedChapter = ref<string | null>(null)
const editingChapter = ref<string | null>(null)
const editName = ref('')
const newChapterName = ref('')

const albumId = computed(() => {
  const id = route.params.id
  return typeof id === 'string' ? id : ''
})

const needCleaning = computed(() => ['draft', 'uploaded'].includes(albumStatus.value))
const { latestTask, refreshTask, startPolling } = useAlbumTaskMonitor({
  albumId,
  matches: (task) => task.task_type === 'cluster_chapters',
})

async function applyClusterTaskOutcome(task = latestTask.value) {
  await loadData()
  if (task?.task_status === 'succeeded') {
    successMessage.value = '自动章节整理完成。'
    setTimeout(() => {
      successMessage.value = ''
    }, 3000)
  }
}

function getPhotos(idList: string[]) {
  const idSet = new Set(idList)
  return allPhotos.value.filter((photo) => idSet.has(photo.id))
}

function getOrphans() {
  const assigned = new Set<string>()
  chapters.value.forEach((chapter) => (chapter.photo_ids || []).forEach((id) => assigned.add(id)))
  return allPhotos.value.filter((photo) => !assigned.has(photo.id))
}

async function loadData() {
  if (!albumId.value) return
  loading.value = true
  errorMessage.value = ''
  try {
    const [chapterResponse, photoResponse, albumResponse] = await Promise.all([
      httpGet<ChapterItem[]>(`/albums/${albumId.value}/chapters`),
      httpGet<{ items: PhotoItem[] }>(`/albums/${albumId.value}/photos?recommendation=keep`),
      httpGet<any>(`/albums/${albumId.value}`),
    ])
    chapters.value = chapterResponse.data || []
    allPhotos.value = photoResponse.data.items || []
    albumStatus.value = albumResponse.data?.status || 'draft'
  } catch (error: any) {
    errorMessage.value = error.message
  } finally {
    loading.value = false
  }
}

function goBack() {
  void router.push(`/albums/${albumId.value}/cleaning`)
}

async function startCluster() {
  if (!albumId.value) return
  actionLoading.value = true
  errorMessage.value = ''
  successMessage.value = ''
  try {
    const response = await httpPost<{ task: { id: string } }>(`/albums/${albumId.value}/cluster`)
    const taskId = response.data.task.id
    await refreshTask(taskId)
    startPolling(taskId, async (task) => {
      await applyClusterTaskOutcome(task)
    })
  } catch (error: any) {
    errorMessage.value = error.message
    await refreshTask()
  } finally {
    actionLoading.value = false
  }
}

async function createChapter() {
  if (!newChapterName.value.trim()) return
  try {
    await httpPost(`/albums/${albumId.value}/chapters`, { name: newChapterName.value.trim(), photo_ids: [] })
    newChapterName.value = ''
    await loadData()
  } catch (error: any) {
    errorMessage.value = error.message
  }
}

async function renameChapter(chapter: ChapterItem) {
  try {
    await httpPatch(`/albums/${albumId.value}/chapters/${chapter.id}`, { name: editName.value })
    chapter.name = editName.value
    editingChapter.value = null
  } catch (error: any) {
    errorMessage.value = error.message
  }
}

async function deleteChapter(id: string) {
  if (!confirm('删除该章节后，其中照片会回到未分配区。确定继续吗？')) return
  try {
    await httpDelete(`/albums/${albumId.value}/chapters/${id}`)
    await loadData()
  } catch (error: any) {
    errorMessage.value = error.message
  }
}

async function movePhoto(photoId: string, targetChapterId: string) {
  if (targetChapterId === ORPHAN_ID) {
    errorMessage.value = '当前版本暂不支持直接拖回未分配区，可通过删除章节释放照片。'
    return
  }
  try {
    await httpPost(`/albums/${albumId.value}/chapters/move-photos`, { photo_ids: [photoId], target_chapter_id: targetChapterId })
    await loadData()
  } catch (error: any) {
    errorMessage.value = error.message
  }
}

function goNext() {
  void router.push(`/albums/${albumId.value}/planning`)
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
    await loadData()
    await refreshTask()
  },
)
</script>

<template>
  <WorkflowStepper v-if="albumId" :album-id="albumId" :album-status="albumStatus" />

  <div class="space-y-6">
    <StoryHero
      eyebrow="Chapter Assembly"
      title="把镜头整理成可以阅读的故事章节"
      description="系统会尝试自动聚类，但最终章节结构仍由你把控。每个章节更像一本书里的段落，而不是机械标签。"
    >
      <div class="grid gap-4 md:grid-cols-3">
        <div class="story-panel rounded-[24px] px-4 py-4">
          <p class="font-story text-3xl text-[var(--story-gold-soft)]">{{ allPhotos.length }}</p>
          <p class="mt-2 text-sm text-[var(--story-text)]">可用镜头</p>
        </div>
        <div class="story-panel rounded-[24px] px-4 py-4">
          <p class="font-story text-3xl text-[var(--story-gold-soft)]">{{ chapters.length }}</p>
          <p class="mt-2 text-sm text-[var(--story-text)]">已成形章节</p>
        </div>
        <div class="story-panel rounded-[24px] px-4 py-4">
          <p class="font-story text-3xl text-[var(--story-gold-soft)]">{{ getOrphans().length }}</p>
          <p class="mt-2 text-sm text-[var(--story-text)]">未分配镜头</p>
        </div>
      </div>
    </StoryHero>

    <SectionCard
      title="章节整理"
      description="你可以先自动聚类，再手动重命名章节、调整照片归属，让叙事结构更符合你的想法。"
      tone="film"
      eyebrow="Step 3"
    >
      <div v-if="!loading && needCleaning" class="rounded-[22px] border border-[#8e6732] bg-[rgba(170,120,44,0.14)] px-4 py-4 text-sm text-[var(--story-muted)]">
        请先完成镜头筛选，再进入章节整理。
        <button class="story-button-secondary ml-3 px-4 py-2 text-sm" @click="goBack">返回筛选页</button>
      </div>

      <div class="mt-4 flex flex-wrap items-center gap-3">
        <button class="story-button px-6 py-3 text-sm" :disabled="!albumId || actionLoading" @click="startCluster">
          {{ actionLoading ? '整理中...' : '自动整理章节' }}
        </button>
        <div class="flex flex-wrap items-center gap-2">
          <input
            v-model="newChapterName"
            type="text"
            placeholder="新章节名称"
            class="rounded-full border border-[rgba(224,177,106,0.18)] bg-[rgba(255,255,255,0.05)] px-4 py-3 text-sm text-[var(--story-text)] outline-none placeholder:text-[var(--story-faint)]"
            @keyup.enter="createChapter"
          />
          <button class="story-button-secondary px-4 py-3 text-sm" @click="createChapter">新增章节</button>
        </div>
        <button v-if="chapters.length > 0" class="story-button-secondary ml-auto px-6 py-3 text-sm" @click="goNext">
          进入页面编排 →
        </button>
      </div>

      <div class="mt-4">
        <AlbumTaskStatusCard
          :task="latestTask"
          title="章节整理任务"
          running-hint="系统正在整理章节结构，页面会自动轮询最新状态。"
          empty-text="点击“自动整理章节”后，这里会显示任务状态、AI 回退信息和章节结果摘要。"
        />
      </div>

      <div v-if="successMessage || errorMessage" class="mt-4 flex flex-col gap-3">
        <p v-if="successMessage" class="rounded-[18px] bg-[#dcead5] px-4 py-3 text-sm text-[#47673d]">{{ successMessage }}</p>
        <p v-if="errorMessage" class="rounded-[18px] bg-[#f6d9d3] px-4 py-3 text-sm text-[#8b4339]">{{ errorMessage }}</p>
      </div>

      <p v-if="isDragging" class="mt-4 text-xs text-[var(--story-faint)]">拖动照片到目标章节，即可调整故事归属。</p>
    </SectionCard>

    <div v-if="chapters.length > 0" class="space-y-4">
      <article
        v-for="chapter in chapters"
        :key="chapter.id"
        class="story-panel overflow-hidden rounded-[28px]"
        :class="getDropTargetClass(chapter.id)"
        @dragover.prevent="(event: DragEvent) => onDragOver(event, chapter.id)"
        @dragleave="() => onDragLeave(chapter.id)"
        @drop="(event: DragEvent) => onDrop(event, chapter.id)"
      >
        <div class="flex flex-wrap items-center justify-between gap-4 px-5 py-5">
          <div class="flex-1">
            <div v-if="editingChapter === chapter.id">
              <input
                v-model="editName"
                class="w-full rounded-[18px] border border-[rgba(224,177,106,0.24)] bg-[rgba(255,255,255,0.05)] px-4 py-3 text-lg text-[var(--story-text)] outline-none"
                autofocus
                @keyup.enter="renameChapter(chapter)"
                @blur="renameChapter(chapter)"
              />
            </div>
            <div v-else>
              <p class="font-story text-4xl text-[var(--story-gold-soft)]">{{ chapter.name }}</p>
              <p class="mt-2 text-sm text-[var(--story-muted)]">{{ chapter.description || '这一章正在等待你填入更明确的叙事重点。' }}</p>
              <p class="mt-2 text-xs uppercase tracking-[0.22em] text-[var(--story-faint)]">
                {{ (chapter.photo_ids || []).length }} Frames
              </p>
            </div>
          </div>

          <div class="flex flex-wrap gap-2">
            <button class="story-button-secondary px-4 py-2 text-sm" @click="expandedChapter = expandedChapter === chapter.id ? null : chapter.id">
              {{ expandedChapter === chapter.id ? '收起' : '展开章节' }}
            </button>
            <button class="story-button-secondary px-4 py-2 text-sm" @click="editName = chapter.name; editingChapter = chapter.id">重命名</button>
            <button class="rounded-full bg-[#f2d8d2] px-4 py-2 text-sm text-[#8b4339] hover:brightness-95" @click="deleteChapter(chapter.id)">删除</button>
          </div>
        </div>

        <div v-if="expandedChapter === chapter.id" class="border-t border-[rgba(224,177,106,0.14)] px-5 py-5">
          <div v-if="getPhotos(chapter.photo_ids || []).length === 0" class="rounded-[22px] border border-dashed border-[rgba(224,177,106,0.18)] px-5 py-10 text-center text-sm text-[var(--story-muted)]">
            这个章节还没有镜头。把照片拖拽到这里，或先运行自动整理。
          </div>
          <div v-else class="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <article
              v-for="photo in getPhotos(chapter.photo_ids || [])"
              :key="photo.id"
              class="film-frame overflow-hidden rounded-[22px] bg-[rgba(255,255,255,0.04)]"
              :class="getDragPhotoClass(photo.id)"
              draggable="true"
              @dragstart="(event: DragEvent) => onDragStart(event, photo.id, chapter.id)"
              @dragend="onDragEnd"
            >
              <ProtectedImage :src="photo.url" :alt="photo.filename" class="h-44 w-full object-cover pointer-events-none" />
              <div class="px-3 py-3">
                <p class="truncate text-sm text-[var(--story-text)]">{{ photo.filename }}</p>
              </div>
            </article>
          </div>
        </div>
      </article>
    </div>

    <SectionCard
      v-if="getOrphans().length > 0"
      title="待归档镜头"
      :description="`${getOrphans().length} 张照片还没有进入任何章节。`"
      tone="accent"
      eyebrow="Unassigned"
    >
      <div class="grid gap-3 sm:grid-cols-3 lg:grid-cols-5">
        <article
          v-for="photo in getOrphans()"
          :key="photo.id"
          class="overflow-hidden rounded-[22px] border border-dashed border-[rgba(79,59,42,0.22)] bg-white/60"
          :class="getDragPhotoClass(photo.id)"
          draggable="true"
          @dragstart="(event: DragEvent) => onDragStart(event, photo.id, ORPHAN_ID)"
          @dragend="onDragEnd"
        >
          <ProtectedImage :src="photo.url" :alt="photo.filename" class="h-36 w-full object-cover pointer-events-none" />
          <div class="px-3 py-3">
            <p class="truncate text-sm text-[#241c16]">{{ photo.filename }}</p>
          </div>
        </article>
      </div>
    </SectionCard>

    <div v-if="!loading && chapters.length === 0 && albumId" class="story-panel rounded-[28px] px-6 py-12 text-center">
      <p class="font-story text-4xl text-[var(--story-gold-soft)]">No Chapters Yet</p>
      <p class="mt-3 text-sm text-[var(--story-muted)]">先点击“自动整理章节”，或者手动新建第一章。</p>
    </div>
  </div>
</template>

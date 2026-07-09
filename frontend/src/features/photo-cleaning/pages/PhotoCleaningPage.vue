<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import SectionCard from '@/shared/components/SectionCard.vue'
import StoryHero from '@/shared/components/StoryHero.vue'
import WorkflowStepper from '@/shared/components/WorkflowStepper.vue'
import ProtectedImage from '@/shared/components/ProtectedImage.vue'
import AlbumTaskStatusCard from '@/shared/components/AlbumTaskStatusCard.vue'
import { httpGet, httpPatch, httpPost } from '@/shared/api/http'
import { useAlbumTaskMonitor } from '@/shared/composables/useAlbumTaskMonitor'

interface PhotoItem {
  id: string
  filename: string
  size: number
  url: string
  quality_score?: number | null
  cleaning_recommendation?: string | null
  cleaning_issues?: string[] | null
}

const route = useRoute()
const router = useRouter()

const album = ref<any>(null)
const photos = ref<PhotoItem[]>([])
const loading = ref(false)
const actionLoading = ref(false)
const errorMessage = ref('')
const successMessage = ref('')
const selectedIds = ref<Set<string>>(new Set())
const showRemoved = ref(false)

const albumId = computed(() => {
  const id = route.params.id
  return typeof id === 'string' ? id : ''
})

const keepPhotos = computed(() => photos.value.filter((photo) => photo.cleaning_recommendation !== 'remove'))
const removedPhotos = computed(() => photos.value.filter((photo) => photo.cleaning_recommendation === 'remove'))
const unscoredPhotos = computed(() => photos.value.filter((photo) => photo.quality_score == null))
const { latestTask, refreshTask, startPolling } = useAlbumTaskMonitor({
  albumId,
  matches: (task) => task.task_type === 'clean_photos',
})

async function applyCleaningTaskOutcome(task = latestTask.value) {
  await loadData()
  if (task?.task_status === 'succeeded') {
    successMessage.value = '镜头筛选分析完成。'
    setTimeout(() => {
      successMessage.value = ''
    }, 3000)
  }
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function toggleSelect(photoId: string) {
  const next = new Set(selectedIds.value)
  if (next.has(photoId)) next.delete(photoId)
  else next.add(photoId)
  selectedIds.value = next
}

function toggleSelectAll() {
  selectedIds.value = selectedIds.value.size === keepPhotos.value.length ? new Set() : new Set(keepPhotos.value.map((photo) => photo.id))
}

async function loadData() {
  if (!albumId.value) return
  loading.value = true
  errorMessage.value = ''
  try {
    const [albumResponse, photoResponse] = await Promise.all([
      httpGet<any>(`/albums/${albumId.value}`),
      httpGet<{ items: PhotoItem[] }>(`/albums/${albumId.value}/photos`),
    ])
    album.value = albumResponse.data
    photos.value = photoResponse.data.items || []
  } catch (error: any) {
    errorMessage.value = error.message
  } finally {
    loading.value = false
  }
}

async function startCleaning() {
  if (!albumId.value) return
  actionLoading.value = true
  errorMessage.value = ''
  successMessage.value = ''
  try {
    const response = await httpPost<{ task: { id: string } }>(`/albums/${albumId.value}/clean`)
    const taskId = response.data.task.id
    await refreshTask(taskId)
    startPolling(taskId, async (task) => {
      await applyCleaningTaskOutcome(task)
    })
  } catch (error: any) {
    errorMessage.value = error.message
    await refreshTask()
  } finally {
    actionLoading.value = false
  }
}

async function updateDecision(photo: PhotoItem, decision: 'keep' | 'remove') {
  try {
    await httpPatch(`/albums/${albumId.value}/photos/${photo.id}`, { cleaning_recommendation: decision })
    photo.cleaning_recommendation = decision
  } catch (error: any) {
    errorMessage.value = error.message
  }
}

async function batchUpdate(decision: 'keep' | 'remove') {
  let count = 0
  for (const photoId of selectedIds.value) {
    try {
      await httpPatch(`/albums/${albumId.value}/photos/${photoId}`, { cleaning_recommendation: decision })
      const target = photos.value.find((photo) => photo.id === photoId)
      if (target) {
        target.cleaning_recommendation = decision
      }
      count += 1
    } catch {
      continue
    }
  }
  selectedIds.value = new Set()
  successMessage.value = `已将 ${count} 张照片标记为${decision === 'keep' ? '保留' : '移除'}。`
  setTimeout(() => {
    successMessage.value = ''
  }, 3000)
}

function goNext() {
  if (album.value?.status === 'draft') {
    errorMessage.value = '请先上传照片，再进入镜头筛选。'
    return
  }
  void router.push(`/albums/${albumId.value}/chapters`)
}

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
  <WorkflowStepper v-if="albumId" :album-id="albumId" :album-status="album?.status" />

  <div class="space-y-6">
    <StoryHero
      eyebrow="Frame Selection"
      title="先筛镜头，再让故事成章"
      description="这里的重点不是机械打分，而是帮助你把可用镜头和需要舍弃的素材分开，为后续章节编排留出节奏。"
    >
      <div class="grid gap-4 md:grid-cols-4">
        <div class="story-panel rounded-[24px] px-4 py-4">
          <p class="font-story text-3xl text-[var(--story-gold-soft)]">{{ photos.length }}</p>
          <p class="mt-2 text-sm text-[var(--story-text)]">总素材</p>
        </div>
        <div class="story-panel rounded-[24px] px-4 py-4">
          <p class="font-story text-3xl text-[var(--story-gold-soft)]">{{ keepPhotos.length }}</p>
          <p class="mt-2 text-sm text-[var(--story-text)]">建议保留</p>
        </div>
        <div class="story-panel rounded-[24px] px-4 py-4">
          <p class="font-story text-3xl text-[var(--story-gold-soft)]">{{ removedPhotos.length }}</p>
          <p class="mt-2 text-sm text-[var(--story-text)]">建议移除</p>
        </div>
        <div class="story-panel rounded-[24px] px-4 py-4">
          <p class="font-story text-3xl text-[var(--story-gold-soft)]">{{ unscoredPhotos.length }}</p>
          <p class="mt-2 text-sm text-[var(--story-text)]">待分析</p>
        </div>
      </div>
    </StoryHero>

    <SectionCard
      title="镜头筛选"
      :description="album ? `当前正在处理《${album.name}》的素材。完成后即可进入章节编排。` : '系统会根据素材质量给出建议，但最终选择仍然由你决定。'"
      tone="film"
      eyebrow="Step 2"
    >
      <div v-if="album?.status === 'draft'" class="rounded-[22px] border border-[#8e6732] bg-[rgba(170,120,44,0.14)] px-4 py-4 text-sm text-[var(--story-muted)]">
        这本相册还没有照片。请先返回上传页收集素材，再开始镜头筛选。
      </div>

      <div class="mt-4 flex flex-wrap items-center gap-3">
        <button class="story-button px-6 py-3 text-sm" :disabled="!albumId || actionLoading" @click="startCleaning">
          {{ actionLoading ? '分析中...' : '开始分析素材' }}
        </button>
        <button
          v-if="keepPhotos.length > 0"
          class="story-button-secondary px-6 py-3 text-sm"
          @click="goNext"
        >
          进入章节编排 →
        </button>
      </div>

      <div class="mt-4">
        <AlbumTaskStatusCard
          :task="latestTask"
          title="镜头筛选任务"
          running-hint="系统正在分析照片质量，页面会自动刷新最新状态。"
          empty-text="点击“开始分析素材”后，这里会显示任务状态和结果摘要。"
        />
      </div>

      <div v-if="successMessage || errorMessage" class="mt-4 flex flex-col gap-3">
        <p v-if="successMessage" class="rounded-[18px] bg-[#dcead5] px-4 py-3 text-sm text-[#47673d]">{{ successMessage }}</p>
        <p v-if="errorMessage" class="rounded-[18px] bg-[#f6d9d3] px-4 py-3 text-sm text-[#8b4339]">{{ errorMessage }}</p>
      </div>
    </SectionCard>

    <SectionCard
      v-if="keepPhotos.length > 0"
      title="保留镜头"
      :description="`这些镜头会进入后续章节聚类与书页编排。当前已选择 ${selectedIds.size} 张。`"
      tone="accent"
      eyebrow="Keep"
    >
      <div class="mb-4 flex flex-wrap items-center gap-3">
        <button class="rounded-full bg-[rgba(43,31,24,0.08)] px-4 py-2 text-sm text-[#4a3d33] hover:bg-[rgba(43,31,24,0.12)]" @click="toggleSelectAll">
          {{ selectedIds.size === keepPhotos.length ? '取消全选' : '全选保留镜头' }}
        </button>
        <button
          class="rounded-full bg-[#f2d8d2] px-4 py-2 text-sm text-[#8b4339] hover:brightness-95 disabled:opacity-40"
          :disabled="selectedIds.size === 0"
          @click="batchUpdate('remove')"
        >
          批量移除
        </button>
      </div>

      <div class="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        <article
          v-for="photo in keepPhotos"
          :key="photo.id"
          class="overflow-hidden rounded-[24px] border border-[rgba(79,59,42,0.14)] bg-white/70 shadow-[0_12px_30px_rgba(0,0,0,0.08)]"
        >
          <div class="relative">
            <ProtectedImage :src="photo.url" :alt="photo.filename" class="h-64 w-full object-cover" />
            <label class="absolute left-3 top-3 rounded-full bg-[rgba(15,17,21,0.7)] px-3 py-1 text-xs text-white">
              <input type="checkbox" class="mr-2" :checked="selectedIds.has(photo.id)" @change="toggleSelect(photo.id)" />
              选中
            </label>
            <span class="absolute right-3 top-3 rounded-full bg-white/85 px-3 py-1 text-xs text-[#5f5347]">
              评分 {{ photo.quality_score?.toFixed(1) ?? '-' }}
            </span>
          </div>
          <div class="space-y-3 px-4 py-4">
            <div>
              <p class="truncate text-sm font-medium text-[#241c16]">{{ photo.filename }}</p>
              <p class="mt-1 text-xs text-[#78695c]">{{ formatFileSize(photo.size) }}</p>
            </div>
            <div v-if="photo.cleaning_issues?.length" class="flex flex-wrap gap-2">
              <span v-for="issue in photo.cleaning_issues" :key="issue" class="rounded-full bg-[#f7e7cc] px-3 py-1 text-xs text-[#946c2f]">
                {{ issue }}
              </span>
            </div>
            <div class="flex items-center gap-2">
              <button class="story-button-secondary px-4 py-2 text-sm !text-[#241c16] !bg-[rgba(43,31,24,0.08)]" @click="updateDecision(photo, 'remove')">
                标记移除
              </button>
            </div>
          </div>
        </article>
      </div>
    </SectionCard>

    <SectionCard
      v-if="removedPhotos.length > 0"
      title="待舍弃镜头"
      :description="`这些镜头不会进入后续流程。你仍然可以恢复其中任何一张。`"
      tone="film"
      eyebrow="Remove"
    >
      <button class="rounded-full border border-[rgba(224,177,106,0.18)] px-4 py-2 text-sm text-[var(--story-muted)] hover:bg-[rgba(255,255,255,0.05)]" @click="showRemoved = !showRemoved">
        {{ showRemoved ? '收起' : '展开已移除镜头' }}
      </button>
      <div v-if="showRemoved" class="mt-4 grid gap-3 sm:grid-cols-3 lg:grid-cols-5">
        <article v-for="photo in removedPhotos" :key="photo.id" class="overflow-hidden rounded-[22px] border border-[rgba(224,177,106,0.16)] bg-[rgba(255,255,255,0.04)] opacity-75 transition hover:opacity-100">
          <ProtectedImage :src="photo.url" :alt="photo.filename" class="h-36 w-full object-cover grayscale" />
          <div class="space-y-3 px-3 py-3">
            <p class="truncate text-sm text-[var(--story-text)]">{{ photo.filename }}</p>
            <button class="story-button-secondary w-full px-4 py-2 text-sm" @click="updateDecision(photo, 'keep')">恢复到保留区</button>
          </div>
        </article>
      </div>
    </SectionCard>

    <div v-if="!loading && photos.length === 0 && albumId" class="story-panel rounded-[28px] px-6 py-12 text-center">
      <p class="font-story text-4xl text-[var(--story-gold-soft)]">No Frames Yet</p>
      <p class="mt-3 text-sm text-[var(--story-muted)]">这本相册还没有照片，请先返回上传页收集素材。</p>
      <button class="story-button mt-6 px-6 py-3 text-sm" @click="router.push(`/albums/${albumId}/upload`)">
        返回上传页
      </button>
    </div>
  </div>
</template>

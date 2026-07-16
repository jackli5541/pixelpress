<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Check, ChevronRight, ImageOff, RotateCcw, ScanSearch, ShieldCheck, X } from 'lucide-vue-next'
import AlbumTaskStatusCard from '@/shared/components/AlbumTaskStatusCard.vue'
import ProtectedImage from '@/shared/components/ProtectedImage.vue'
import SectionCard from '@/shared/components/SectionCard.vue'
import WorkflowStepper from '@/shared/components/WorkflowStepper.vue'
import { httpGet, httpPatch, httpPost } from '@/shared/api/http'
import { useAlbumTaskMonitor } from '@/shared/composables/useAlbumTaskMonitor'

type Suggestion = 'keep' | 'review' | 'remove' | null
type Decision = 'keep' | 'remove' | null
type ReviewStatus = 'pending_review' | 'included' | 'kept' | 'removed' | 'unanalyzed'
type ViewMode = 'duplicates' | 'review' | 'all' | 'excluded'

interface CleaningFeatures {
  fallback_used?: boolean
  sharpness?: { variance?: number; score?: number; severity?: string }
  exposure?: { mean?: number; score?: number; severity?: string }
  resolution?: { width?: number; height?: number; min_side?: number; score?: number; severity?: string }
  composition?: { orientation?: string; aspect_ratio?: number }
}

interface PhotoItem {
  id: string
  filename: string
  size: number
  url: string
  width?: number | null
  height?: number | null
  quality_score?: number | null
  cleaning_issues?: string[] | null
  cleaning: {
    suggestion: Suggestion
    review_status: ReviewStatus
    confidence?: number | null
    decision: Decision
    decision_source?: string | null
    excluded: boolean
    analysis_version?: string | null
    features?: CleaningFeatures | null
  }
}

interface DuplicateMember {
  photo_id: string
  relation_type: string
  hamming_distance?: number | null
  burst_time_delta_ms?: number | null
  preferred_score: number
  rank: number
  is_preferred: boolean
  auto_excluded: boolean
  factors?: Record<string, number | null>
}

interface DuplicateGroup {
  id: string
  group_type: string
  confidence: number
  preferred_photo_id: string
  thresholds?: { near_phash?: number; burst_phash?: number; burst_window_ms?: number }
  members: DuplicateMember[]
}

interface CleaningResults {
  album_id: string
  analysis_version?: string | null
  summary: {
    total: number
    keep: number
    review: number
    remove: number
    excluded: number
    pending_review: number
    included: number
    kept: number
    removed: number
    duplicate_groups: number
    analysis_failures: number
  }
  groups: DuplicateGroup[]
  items: PhotoItem[]
}

interface UndoState {
  label: string
  decisions: Map<string, Decision>
}

const route = useRoute()
const router = useRouter()
const album = ref<any>(null)
const results = ref<CleaningResults | null>(null)
const loading = ref(false)
const actionLoading = ref(false)
const errorMessage = ref('')
const successMessage = ref('')
const viewMode = ref<ViewMode>('duplicates')
const orientationFilter = ref('all')
const selectedIds = ref<Set<string>>(new Set())
const undoState = ref<UndoState | null>(null)
const viewOptions: Array<[ViewMode, string]> = [
  ['duplicates', '重复组'],
  ['review', '待复核'],
  ['all', '全部'],
  ['excluded', '已移出'],
]

const albumId = computed(() => (typeof route.params.id === 'string' ? route.params.id : ''))
const photos = computed(() => results.value?.items ?? [])
const groups = computed(() => results.value?.groups ?? [])
const photoMap = computed(() => new Map(photos.value.map((photo) => [photo.id, photo])))
const summary = computed(() => results.value?.summary ?? {
  total: photos.value.length,
  keep: 0,
  review: 0,
  remove: 0,
  excluded: 0,
  pending_review: 0,
  included: 0,
  kept: 0,
  removed: 0,
  duplicate_groups: 0,
  analysis_failures: 0,
})
const hasAnalysis = computed(() => Boolean(results.value?.analysis_version))
const pendingReviewCount = computed(() => summary.value.pending_review)
const reviewPhotos = computed(() => photos.value.filter((photo) => photo.cleaning.review_status === 'pending_review'))
const excludedPhotos = computed(() => photos.value.filter((photo) => photo.cleaning.excluded))
const filteredPhotos = computed(() => {
  const source = viewMode.value === 'review' ? reviewPhotos.value : viewMode.value === 'excluded' ? excludedPhotos.value : photos.value
  return source.filter((photo) => orientationFilter.value === 'all' || photo.cleaning.features?.composition?.orientation === orientationFilter.value)
})

const { latestTask, refreshTask, startPolling } = useAlbumTaskMonitor({
  albumId,
  matches: (task) => task.task_type === 'clean_photos',
})

function formatFileSize(bytes: number) {
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function formatPercent(value?: number | null) {
  return value == null ? '-' : `${Math.round(value * 100)}%`
}

function relationLabel(type: string) {
  return ({ preferred: '首选', exact: '完全相同', near: '近似重复', burst: '连拍相似' } as Record<string, string>)[type] ?? type
}

function groupLabel(type: string) {
  return ({ exact: '精确重复', near: '近似重复', burst: '连拍相似', mixed: '混合重复' } as Record<string, string>)[type] ?? type
}

function issueLabel(issue: string) {
  return ({
    sharpness_warning: '清晰度偏低',
    sharpness_severe: '严重模糊',
    exposure_warning: '曝光需检查',
    exposure_severe: '曝光异常',
    resolution_warning: '分辨率偏低',
    resolution_severe: '分辨率过低',
    analysis_failed: '分析回退',
  } as Record<string, string>)[issue] ?? issue
}

function suggestionLabel(suggestion: Suggestion) {
  return suggestion === 'remove' ? '建议移除' : suggestion === 'review' ? '需要复核' : suggestion === 'keep' ? '建议保留' : '待分析'
}

function reviewStatusLabel(status: ReviewStatus) {
  return ({
    pending_review: '需要复核',
    included: '建议保留',
    kept: '已确认保留',
    removed: '已移出',
    unanalyzed: '待分析',
  } as Record<ReviewStatus, string>)[status]
}

function reviewStatusClass(status: ReviewStatus) {
  return ({
    pending_review: 'bg-[#956d32]',
    included: 'bg-[#4f7048]',
    kept: 'bg-[#5b714d]',
    removed: 'bg-[#9b4e43]',
    unanalyzed: 'bg-[#78695c]',
  } as Record<ReviewStatus, string>)[status]
}

function toggleSelect(photoId: string) {
  const next = new Set(selectedIds.value)
  next.has(photoId) ? next.delete(photoId) : next.add(photoId)
  selectedIds.value = next
}

function flash(message: string) {
  successMessage.value = message
  window.setTimeout(() => {
    successMessage.value = ''
  }, 4000)
}

async function loadData() {
  if (!albumId.value) return
  loading.value = true
  errorMessage.value = ''
  try {
    const [albumResponse, resultResponse] = await Promise.all([
      httpGet<any>(`/albums/${albumId.value}`),
      httpGet<CleaningResults>(`/albums/${albumId.value}/clean/results`),
    ])
    album.value = albumResponse.data
    results.value = resultResponse.data
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
  undoState.value = null
  try {
    const response = await httpPost<{ task: { id: string } }>(`/albums/${albumId.value}/clean`)
    const taskId = response.data.task.id
    await refreshTask(taskId)
    startPolling(taskId, async (task) => {
      await loadData()
      if (task.task_status === 'succeeded') flash('照片分析已完成')
    })
  } catch (error: any) {
    errorMessage.value = error.message
    await refreshTask()
  } finally {
    actionLoading.value = false
  }
}

async function applyDecision(photoIds: string[], decision: Decision, label: string, remember = true) {
  if (!photoIds.length) return
  actionLoading.value = true
  errorMessage.value = ''
  if (remember) {
    undoState.value = {
      label,
      decisions: new Map(photoIds.map((id) => [id, photoMap.value.get(id)?.cleaning.decision ?? null])),
    }
  }
  try {
    await httpPatch(`/albums/${albumId.value}/clean/decisions`, { photo_ids: photoIds, decision })
    selectedIds.value = new Set()
    await loadData()
    flash(label)
  } catch (error: any) {
    errorMessage.value = error.message
  } finally {
    actionLoading.value = false
  }
}

async function acceptPreferred(group: DuplicateGroup) {
  const previous = new Map(group.members.map((member) => [member.photo_id, photoMap.value.get(member.photo_id)?.cleaning.decision ?? null]))
  actionLoading.value = true
  errorMessage.value = ''
  try {
    await httpPost(`/albums/${albumId.value}/clean/groups/${group.id}/accept-preferred`)
    undoState.value = { label: '已采用重复组首选图', decisions: previous }
    await loadData()
    flash('已保留首选图并移出其余照片')
  } catch (error: any) {
    errorMessage.value = error.message
  } finally {
    actionLoading.value = false
  }
}

async function undoLastAction() {
  const state = undoState.value
  if (!state) return
  actionLoading.value = true
  errorMessage.value = ''
  try {
    const buckets = new Map<Decision, string[]>()
    for (const [photoId, decision] of state.decisions) {
      buckets.set(decision, [...(buckets.get(decision) ?? []), photoId])
    }
    for (const [decision, photoIds] of buckets) {
      await httpPatch(`/albums/${albumId.value}/clean/decisions`, { photo_ids: photoIds, decision })
    }
    undoState.value = null
    await loadData()
    flash('上一步操作已撤销')
  } catch (error: any) {
    errorMessage.value = error.message
  } finally {
    actionLoading.value = false
  }
}

function goNext() {
  if (pendingReviewCount.value) {
    viewMode.value = 'review'
    errorMessage.value = `请先处理剩余 ${pendingReviewCount.value} 张待复核照片`
    return
  }
  void router.push(`/albums/${albumId.value}/chapters`)
}

onMounted(async () => {
  await loadData()
  await refreshTask()
})

watch(albumId, async () => {
  await loadData()
  await refreshTask()
})
</script>

<template>
  <WorkflowStepper v-if="albumId" :album-id="albumId" :album-status="album?.status" />

  <div class="space-y-6">
    <section class="story-panel overflow-hidden rounded-[28px] px-5 py-6 md:px-8">
      <div class="flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p class="text-xs uppercase text-[var(--story-gold-soft)]">Stage B · Photo Cleaning</p>
          <h1 class="font-story mt-2 text-4xl text-[var(--story-text)]">照片清洗</h1>
          <p class="mt-2 text-sm text-[var(--story-muted)]">{{ album?.name ?? '当前相册' }} · {{ results?.analysis_version ?? '尚未分析' }}</p>
        </div>
        <div class="flex flex-wrap gap-2">
          <button v-if="undoState" class="story-button-secondary inline-flex items-center gap-2 px-4 py-2 text-sm" :disabled="actionLoading" @click="undoLastAction">
            <RotateCcw :size="16" /> 撤销
          </button>
          <button class="story-button inline-flex items-center gap-2 px-5 py-2.5 text-sm" :disabled="actionLoading || !photos.length" @click="startCleaning">
            <ScanSearch :size="17" /> {{ actionLoading ? '处理中' : hasAnalysis ? '重新分析' : '开始分析' }}
          </button>
          <button class="story-button-secondary inline-flex items-center gap-2 px-5 py-2.5 text-sm" :disabled="!photos.length || Boolean(pendingReviewCount)" :title="pendingReviewCount ? `还需复核 ${pendingReviewCount} 张照片` : undefined" @click="goNext">
            进入分章 <ChevronRight :size="17" />
          </button>
          <span v-if="pendingReviewCount" class="self-center text-xs text-[var(--story-muted)]">还需复核 {{ pendingReviewCount }} 张</span>
        </div>
      </div>

      <div class="mt-6 grid grid-cols-2 gap-px overflow-hidden rounded-lg bg-[rgba(224,177,106,0.18)] md:grid-cols-5">
        <button class="bg-[rgba(24,20,18,0.92)] px-4 py-4 text-left" @click="viewMode = 'all'">
          <span class="block text-2xl text-white">{{ summary.total }}</span><span class="text-xs text-[var(--story-muted)]">全部照片</span>
        </button>
        <button class="bg-[rgba(24,20,18,0.92)] px-4 py-4 text-left" @click="viewMode = 'duplicates'">
          <span class="block text-2xl text-white">{{ summary.duplicate_groups }}</span><span class="text-xs text-[var(--story-muted)]">重复组</span>
        </button>
        <button class="bg-[rgba(24,20,18,0.92)] px-4 py-4 text-left" @click="viewMode = 'review'">
          <span class="block text-2xl text-[#e7b56e]">{{ summary.pending_review }}</span><span class="text-xs text-[var(--story-muted)]">待复核</span>
        </button>
        <button class="bg-[rgba(24,20,18,0.92)] px-4 py-4 text-left" @click="viewMode = 'excluded'">
          <span class="block text-2xl text-[#dc8b7e]">{{ summary.excluded }}</span><span class="text-xs text-[var(--story-muted)]">已移出</span>
        </button>
        <div class="col-span-2 bg-[rgba(24,20,18,0.92)] px-4 py-4 md:col-span-1">
          <span class="block text-2xl text-white">{{ summary.analysis_failures }}</span><span class="text-xs text-[var(--story-muted)]">分析回退</span>
        </div>
      </div>
    </section>

    <AlbumTaskStatusCard
      :task="latestTask"
      title="照片清洗任务"
      running-hint="正在提取图像特征并建立重复组，完成后页面会自动刷新。"
      empty-text=""
    />

    <div v-if="successMessage || errorMessage" class="sticky top-3 z-20 flex flex-col gap-2">
      <div v-if="successMessage" class="flex items-center gap-2 rounded-lg bg-[#e2eddf] px-4 py-3 text-sm text-[#42643a]"><Check :size="17" /> {{ successMessage }}</div>
      <div v-if="errorMessage" class="flex items-center gap-2 rounded-lg bg-[#f5d9d3] px-4 py-3 text-sm text-[#8b4339]"><X :size="17" /> {{ errorMessage }}</div>
    </div>

    <SectionCard v-if="photos.length" title="复核工作区" description="" tone="accent" eyebrow="Review">
      <div class="flex flex-col gap-4 border-b border-[rgba(79,59,42,0.12)] pb-5 md:flex-row md:items-center md:justify-between">
        <div class="inline-flex w-full overflow-x-auto rounded-lg bg-[rgba(43,31,24,0.07)] p-1 md:w-auto">
          <button v-for="option in viewOptions" :key="option[0]" class="min-w-20 rounded-md px-4 py-2 text-sm" :class="viewMode === option[0] ? 'bg-white text-[#241c16] shadow-sm' : 'text-[#78695c]'" @click="viewMode = option[0]">
            {{ option[1] }}
          </button>
        </div>
        <select v-model="orientationFilter" class="rounded-lg border border-[rgba(79,59,42,0.18)] bg-white px-3 py-2 text-sm text-[#4f4339]">
          <option value="all">全部方向</option><option value="landscape">横图</option><option value="portrait">竖图</option><option value="square">方图</option>
        </select>
      </div>

      <div v-if="viewMode === 'duplicates'" class="divide-y divide-[rgba(79,59,42,0.14)]">
        <article v-for="(group, index) in groups" :key="group.id" class="py-6 first:pt-1">
          <div class="mb-4 flex flex-wrap items-center justify-between gap-3">
            <div>
              <div class="flex items-center gap-2"><ShieldCheck :size="18" class="text-[#8a612b]" /><h2 class="text-base font-semibold text-[#241c16]">{{ groupLabel(group.group_type) }} {{ index + 1 }}</h2></div>
              <p class="mt-1 text-xs text-[#78695c]">{{ group.members.length }} 张 · 组置信度 {{ formatPercent(group.confidence) }}</p>
            </div>
            <button class="story-button inline-flex items-center gap-2 px-4 py-2 text-sm" :disabled="actionLoading" @click="acceptPreferred(group)"><Check :size="16" /> 采用首选图</button>
          </div>
          <div class="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <div v-for="member in group.members" :key="member.photo_id" class="overflow-hidden rounded-lg border bg-white" :class="member.is_preferred ? 'border-[#b8843d] ring-1 ring-[#b8843d]' : 'border-[rgba(79,59,42,0.14)]'">
              <div class="relative aspect-[4/3] bg-[#eee9e3]">
                <ProtectedImage :src="photoMap.get(member.photo_id)?.url ?? ''" :alt="photoMap.get(member.photo_id)?.filename ?? ''" class="h-full w-full object-cover" />
                <span class="absolute left-2 top-2 rounded bg-[rgba(20,18,16,0.78)] px-2 py-1 text-xs text-white">{{ relationLabel(member.relation_type) }}</span>
                <span v-if="photoMap.get(member.photo_id)?.cleaning.excluded" class="absolute right-2 top-2 rounded bg-[#9b4e43] px-2 py-1 text-xs text-white">已移出</span>
              </div>
              <div class="space-y-2 p-3">
                <p class="truncate text-sm font-medium text-[#241c16]">{{ photoMap.get(member.photo_id)?.filename }}</p>
                <div class="grid grid-cols-2 gap-2 text-xs text-[#78695c]"><span>质量 {{ member.preferred_score.toFixed(1) }}</span><span>pHash 距离 {{ member.hamming_distance ?? '-' }}</span></div>
                <p v-if="!member.is_preferred" class="text-xs text-[#8a612b]">判定阈值 {{ member.relation_type === 'burst' ? group.thresholds?.burst_phash : group.thresholds?.near_phash }}</p>
                <button v-if="photoMap.get(member.photo_id)?.cleaning.excluded" class="inline-flex items-center gap-1 text-xs text-[#5b714d]" @click="applyDecision([member.photo_id], 'keep', '照片已恢复')"><RotateCcw :size="14" /> 恢复</button>
              </div>
            </div>
          </div>
        </article>
        <div v-if="!groups.length" class="py-12 text-center text-sm text-[#78695c]">{{ hasAnalysis ? '没有发现重复或连拍相似组' : '运行分析后将在这里显示重复组' }}</div>
      </div>

      <div v-else>
        <div v-if="selectedIds.size" class="my-4 flex flex-wrap items-center gap-2 rounded-lg bg-[#f2eee8] px-4 py-3">
          <span class="mr-2 text-sm text-[#4f4339]">已选 {{ selectedIds.size }} 张</span>
          <button class="story-button px-3 py-1.5 text-xs" @click="applyDecision([...selectedIds], 'keep', '已批量保留')">保留</button>
          <button class="rounded-md bg-[#9b4e43] px-3 py-1.5 text-xs text-white" @click="applyDecision([...selectedIds], 'remove', '已批量移出')">移出</button>
        </div>
        <div class="mt-5 grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          <article v-for="photo in filteredPhotos" :key="photo.id" class="overflow-hidden rounded-lg border border-[rgba(79,59,42,0.14)] bg-white">
            <div class="relative aspect-[4/3] bg-[#eee9e3]">
              <ProtectedImage :src="photo.url" :alt="photo.filename" class="h-full w-full object-cover" :class="photo.cleaning.excluded ? 'opacity-55 grayscale' : ''" />
              <label class="absolute left-2 top-2 flex size-8 items-center justify-center rounded bg-white/90 shadow"><input type="checkbox" :checked="selectedIds.has(photo.id)" @change="toggleSelect(photo.id)" /></label>
              <span class="absolute right-2 top-2 rounded px-2 py-1 text-xs text-white" :class="reviewStatusClass(photo.cleaning.review_status)">{{ reviewStatusLabel(photo.cleaning.review_status) }}</span>
            </div>
            <div class="space-y-3 p-4">
              <div><p class="truncate text-sm font-semibold text-[#241c16]">{{ photo.filename }}</p><p class="mt-1 text-xs text-[#78695c]">{{ formatFileSize(photo.size) }} · {{ photo.width }}×{{ photo.height }}</p></div>
              <div class="grid grid-cols-4 overflow-hidden rounded-md border border-[rgba(79,59,42,0.12)] text-center text-xs">
                <div class="py-2"><b class="block text-sm text-[#241c16]">{{ photo.quality_score?.toFixed(1) ?? '-' }}</b>总分</div>
                <div class="border-l py-2"><b class="block text-sm text-[#241c16]">{{ formatPercent(photo.cleaning.features?.sharpness?.score) }}</b>清晰</div>
                <div class="border-l py-2"><b class="block text-sm text-[#241c16]">{{ formatPercent(photo.cleaning.features?.exposure?.score) }}</b>曝光</div>
                <div class="border-l py-2"><b class="block text-sm text-[#241c16]">{{ formatPercent(photo.cleaning.features?.resolution?.score) }}</b>分辨率</div>
              </div>
              <div v-if="photo.cleaning_issues?.length" class="flex flex-wrap gap-1.5"><span v-for="issue in photo.cleaning_issues" :key="issue" class="rounded bg-[#f3e5cf] px-2 py-1 text-xs text-[#815e2d]">{{ issueLabel(issue) }}</span></div>
              <p v-if="photo.cleaning.decision !== null && photo.cleaning.suggestion" class="text-xs text-[#78695c]">算法建议：{{ suggestionLabel(photo.cleaning.suggestion) }}</p>
              <div class="flex gap-2">
                <button v-if="photo.cleaning.excluded" class="story-button-secondary inline-flex flex-1 items-center justify-center gap-1 px-3 py-2 text-xs" @click="applyDecision([photo.id], 'keep', '照片已恢复')"><RotateCcw :size="14" /> 恢复</button>
                <template v-else><button class="story-button-secondary flex-1 px-3 py-2 text-xs" :disabled="photo.cleaning.review_status === 'kept'" @click="applyDecision([photo.id], 'keep', '已确认保留')">{{ photo.cleaning.review_status === 'kept' ? '已确认保留' : '确认保留' }}</button><button class="rounded-md bg-[#f1d8d2] px-3 py-2 text-xs text-[#8b4339]" @click="applyDecision([photo.id], 'remove', '照片已移出')">移出</button></template>
              </div>
            </div>
          </article>
        </div>
        <div v-if="!filteredPhotos.length" class="flex flex-col items-center py-12 text-sm text-[#78695c]"><ImageOff :size="28" class="mb-3" />当前筛选条件下没有照片</div>
      </div>
    </SectionCard>

    <div v-else-if="!loading" class="story-panel rounded-[28px] px-6 py-14 text-center">
      <ImageOff :size="34" class="mx-auto text-[var(--story-gold-soft)]" />
      <p class="mt-4 text-sm text-[var(--story-muted)]">相册中还没有照片</p>
      <button class="story-button mt-5 px-5 py-2.5 text-sm" @click="router.push(`/albums/${albumId}/upload`)">返回上传</button>
    </div>
  </div>
</template>

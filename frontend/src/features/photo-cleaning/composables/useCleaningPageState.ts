import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { httpGet, httpPatch, httpPost } from '@/shared/api/http'
import { useAlbumTaskMonitor } from '@/shared/composables/useAlbumTaskMonitor'
import type { TaskItem } from '@/shared/types/album'
import type {
  CleaningMutationResult,
  CleaningResults,
  Decision,
  PhotoItem,
  PoolMode,
  ReviewAction,
} from '@/features/photo-cleaning/types'

interface UndoState {
  label: string
  decisions: Map<string, Decision>
}

function reviewStatus(photo: PhotoItem) {
  if (photo.cleaning.decision === 'remove') return 'removed'
  if (photo.cleaning.decision === 'keep') return 'kept'
  if (photo.cleaning.suggestion === 'review' || photo.cleaning.suggestion === 'remove') return 'pending_review'
  if (photo.cleaning.suggestion === 'keep') return 'included'
  return 'unanalyzed'
}

export function useCleaningPageState() {
  const route = useRoute()
  const router = useRouter()
  const album = ref<any>(null)
  const results = ref<CleaningResults | null>(null)
  const loading = ref(false)
  const taskActionLoading = ref(false)
  const reviewActionLoading = ref(false)
  const errorMessage = ref('')
  const successMessage = ref('')
  const poolMode = ref<PoolMode>('retained')
  const orientationFilter = ref('all')
  const pendingIds = ref<Set<string>>(new Set())
  const undoState = ref<UndoState | null>(null)
  const reviewOpen = ref(false)
  const reviewInitialTotal = ref(0)

  const albumId = computed(() => (typeof route.params.id === 'string' ? route.params.id : ''))
  const photos = computed(() => results.value?.items ?? [])
  const photoMap = computed(() => new Map(photos.value.map((photo) => [photo.id, photo])))
  const reviewQueue = computed(() => results.value?.review_queue ?? [])
  const currentReviewItem = computed(() => reviewQueue.value[0] ?? null)
  const reviewPosition = computed(() => Math.max(1, reviewInitialTotal.value - reviewQueue.value.length + 1))
  const summary = computed(() => results.value?.summary ?? {
    total: 0,
    retained: 0,
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
  const retainedPhotos = computed(() => photos.value.filter((photo) => !photo.cleaning.excluded))
  const removedPhotos = computed(() => photos.value.filter((photo) => photo.cleaning.excluded))
  const filteredPhotos = computed(() => {
    const source = poolMode.value === 'removed' ? removedPhotos.value : retainedPhotos.value
    return source.filter((photo) => orientationFilter.value === 'all' || photo.cleaning.features?.composition?.orientation === orientationFilter.value)
  })
  const hasAnalysis = computed(() => Boolean(results.value?.analysis_version))

  const { latestTask, refreshTask, startPolling } = useAlbumTaskMonitor({
    albumId,
    matches: (task) => task.task_type === 'clean_photos',
  })

  function flash(message: string) {
    successMessage.value = message
    window.setTimeout(() => {
      successMessage.value = ''
    }, 3500)
  }

  function replacePending(photoId: string, pending: boolean) {
    const next = new Set(pendingIds.value)
    pending ? next.add(photoId) : next.delete(photoId)
    pendingIds.value = next
  }

  function recomputeSummary() {
    if (!results.value) return
    const removed = photos.value.filter((photo) => photo.cleaning.excluded).length
    results.value.summary = {
      ...results.value.summary,
      retained: photos.value.length - removed,
      removed,
      excluded: removed,
      pending_review: photos.value.filter((photo) => reviewStatus(photo) === 'pending_review').length,
    }
  }

  function applyChangedItems(items: PhotoItem[]) {
    if (!results.value) return
    const byId = new Map(items.map((item) => [item.id, item]))
    results.value.items = results.value.items.map((item) => byId.get(item.id) ?? item)
  }

  function applyMutation(result: CleaningMutationResult) {
    if (!results.value) return
    applyChangedItems(result.changed_items)
    results.value.summary = result.summary
    results.value.content_revision = result.content_revision
    if (album.value) album.value.content_revision = result.content_revision
  }

  function preloadReviewImages() {
    for (const item of reviewQueue.value.slice(0, 2)) {
      for (const photoId of item.photo_ids.slice(0, 4)) {
        const url = photoMap.value.get(photoId)?.url
        if (url) {
          const image = new Image()
          image.src = url
        }
      }
    }
  }

  function openReview(force = false) {
    if (!reviewQueue.value.length) return
    const sessionId = results.value?.review_session_id
    const key = sessionId ? `cleaning-review-opened:${sessionId}` : ''
    if (!force && key && window.sessionStorage.getItem(key)) return
    if (key) window.sessionStorage.setItem(key, '1')
    reviewInitialTotal.value = reviewQueue.value.length
    reviewOpen.value = true
    preloadReviewImages()
  }

  async function loadData(silent = false) {
    if (!albumId.value) return
    if (!silent) loading.value = true
    if (!silent) errorMessage.value = ''
    try {
      const [albumResponse, resultResponse] = await Promise.all([
        httpGet<any>(`/albums/${albumId.value}`),
        httpGet<CleaningResults>(`/albums/${albumId.value}/clean/results`),
      ])
      album.value = albumResponse.data
      results.value = resultResponse.data
      if (results.value.summary.pending_review > 0) openReview()
    } catch (error: any) {
      errorMessage.value = error.message
    } finally {
      if (!silent) loading.value = false
    }
  }

  async function startCleaning() {
    if (!albumId.value) return
    taskActionLoading.value = true
    errorMessage.value = ''
    undoState.value = null
    try {
      const response = await httpPost<{ task: TaskItem }>(`/albums/${albumId.value}/clean`)
      const taskId = response.data.task.id
      await refreshTask(taskId)
      startPolling(taskId, async (task) => {
        await loadData(true)
        if (task?.task_status === 'succeeded') {
          flash('照片分析已完成')
          openReview(true)
        }
      })
    } catch (error: any) {
      errorMessage.value = error.message
      await refreshTask()
    } finally {
      taskActionLoading.value = false
    }
  }

  async function applyDecision(photoId: string, decision: Exclude<Decision, null>, remember = true) {
    const photo = photoMap.value.get(photoId)
    if (!photo || pendingIds.value.has(photoId) || !results.value) return
    const previous = photo.cleaning.decision
    const snapshot = { ...photo, cleaning: { ...photo.cleaning } }
    if (remember) undoState.value = { label: decision === 'remove' ? '移除照片' : '恢复照片', decisions: new Map([[photoId, previous]]) }
    photo.cleaning.decision = decision
    photo.cleaning.decision_source = 'user'
    photo.cleaning.excluded = decision === 'remove'
    photo.cleaning.review_status = decision === 'remove' ? 'removed' : 'kept'
    recomputeSummary()
    replacePending(photoId, true)
    try {
      const response = await httpPatch<CleaningMutationResult>(`/albums/${albumId.value}/clean/decisions`, {
        photo_ids: [photoId],
        decision,
        expected_content_revision: results.value.content_revision,
      })
      applyMutation(response.data)
      flash(decision === 'remove' ? '照片已移除' : '照片已恢复保留')
    } catch (error: any) {
      const index = results.value.items.findIndex((item) => item.id === photoId)
      if (index >= 0) results.value.items[index] = snapshot
      recomputeSummary()
      errorMessage.value = error.message
      await loadData(true)
    } finally {
      replacePending(photoId, false)
    }
  }

  async function resolveReview(action: ReviewAction) {
    const item = currentReviewItem.value
    if (!item || !results.value || reviewActionLoading.value) return
    reviewActionLoading.value = true
    errorMessage.value = ''
    try {
      const response = await httpPost<CleaningMutationResult>(`/albums/${albumId.value}/clean/review/resolve`, {
        review_item_id: item.id,
        action,
        expected_content_revision: results.value.content_revision,
      })
      applyMutation(response.data)
      results.value.review_queue = results.value.review_queue.filter((queueItem) => queueItem.id !== item.id)
      if (!results.value.review_queue.length) {
        reviewOpen.value = false
        flash('照片复核已完成')
      } else {
        preloadReviewImages()
      }
    } catch (error: any) {
      errorMessage.value = error.message
      await loadData(true)
    } finally {
      reviewActionLoading.value = false
    }
  }

  async function resolveRemaining() {
    if (!results.value || reviewActionLoading.value || !reviewQueue.value.length) return
    reviewActionLoading.value = true
    errorMessage.value = ''
    try {
      const response = await httpPost<CleaningMutationResult>(`/albums/${albumId.value}/clean/review/resolve-remaining`, {
        expected_content_revision: results.value.content_revision,
      })
      applyMutation(response.data)
      results.value.review_queue = []
      reviewOpen.value = false
      flash(`系统已处理剩余 ${response.data.resolved_review_count ?? 0} 个复核项目`)
    } catch (error: any) {
      errorMessage.value = error.message
      await loadData(true)
    } finally {
      reviewActionLoading.value = false
    }
  }

  async function undoLastAction() {
    const state = undoState.value
    if (!state || !results.value) return
    undoState.value = null
    for (const [photoId, decision] of state.decisions) {
      replacePending(photoId, true)
      try {
        const response = await httpPatch<CleaningMutationResult>(`/albums/${albumId.value}/clean/decisions`, {
          photo_ids: [photoId],
          decision,
          expected_content_revision: results.value.content_revision,
        })
        applyMutation(response.data)
      } catch (error: any) {
        errorMessage.value = error.message
        await loadData(true)
        return
      } finally {
        replacePending(photoId, false)
      }
    }
    flash('上一项操作已撤销')
  }

  function goNext() {
    if (summary.value.pending_review) {
      openReview(true)
      return
    }
    void router.push(`/albums/${albumId.value}/chapters`)
  }

  onMounted(async () => {
    await loadData()
    await refreshTask()
  })

  watch(albumId, async () => {
    reviewOpen.value = false
    await loadData()
    await refreshTask()
  })

  return {
    album,
    albumId,
    currentReviewItem,
    errorMessage,
    filteredPhotos,
    goNext,
    hasAnalysis,
    latestTask,
    loading,
    openReview,
    orientationFilter,
    pendingIds,
    photoMap,
    poolMode,
    resolveRemaining,
    resolveReview,
    retainedPhotos,
    removedPhotos,
    reviewActionLoading,
    reviewInitialTotal,
    reviewOpen,
    reviewPosition,
    results,
    startCleaning,
    successMessage,
    summary,
    taskActionLoading,
    undoLastAction,
    undoState,
    applyDecision,
  }
}

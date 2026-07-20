import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { httpGet } from '@/shared/api/http'
import { useAlbumTaskMonitor } from '@/shared/composables/useAlbumTaskMonitor'
import type { ChapterItem, PhotoItem } from '@/features/chapter-clustering/types'
import { useChapterWorkspace } from '@/features/chapter-clustering/composables/useChapterWorkspace'
import {
  useThemeCuration,
  type ChapterStrategy,
  type ThemeWorkspace,
} from '@/features/chapter-clustering/composables/useThemeCuration'

export const chapterStrategyLabels: Record<ChapterStrategy, string> = {
  balanced: '综合平衡',
  activity_first: '内容优先',
  time_first: '时间优先',
  location_first: '地点优先',
}

export function useChapterPage() {
  const route = useRoute()
  const router = useRouter()
  const loading = ref(false)
  const actionLoading = ref(false)
  const errorMessage = ref('')
  const successMessage = ref('')
  const newChapterName = ref('')
  const granularity = ref(0)
  const albumId = computed(() => typeof route.params.id === 'string' ? route.params.id : '')

  const chapter = useChapterWorkspace(albumId)
  const theme = useThemeCuration<PhotoItem>(albumId)
  const {
    latestTask: latestThemeTask,
    refreshTask: refreshThemeTask,
    startPolling: startThemePolling,
  } = useAlbumTaskMonitor({
    albumId,
    matches: (task) => ['analyze_album_theme', 'score_album_theme'].includes(task.task_type),
  })

  const needCleaning = computed(() => ['draft', 'uploaded'].includes(chapter.albumStatus.value))
  const reviewChapterCount = computed(() => chapter.chapters.value.filter((item) => item.clustering?.needs_review).length)
  const segmentCount = computed(() => chapter.chapters.value.reduce((total, item) => total + (item.segments?.length || 0), 0))
  const showThemePhotoReview = computed(() => theme.isReviewPhase.value)
  const hasGeneratedChapters = computed(() => theme.ready.value && chapter.chapters.value.length > 0)
  const curatedPhotoCount = computed(() => theme.workspace.value?.assessments.length ? theme.kept.value.length : chapter.photos.value.length)
  const orphanPhotos = computed(() => {
    const assigned = new Set<string>()
    chapter.chapters.value.forEach((item) => (item.photo_ids || []).forEach((id) => assigned.add(id)))
    return chapter.photos.value.filter((photo) => !assigned.has(photo.id) && !theme.excludedIds.value.has(photo.id))
  })
  const primaryPhotoMetric = computed(() => ({
    value: theme.isSelectionPhase.value ? chapter.photos.value.length : curatedPhotoCount.value,
    label: theme.isSelectionPhase.value ? '现有镜头' : '候选镜头',
  }))
  const secondaryStructureMetric = computed(() => ({
    value: hasGeneratedChapters.value ? `${chapter.chapters.value.length} / ${segmentCount.value}` : '0 / 0',
    label: '章节 / 活动阶段',
  }))
  const tertiaryPhotoMetric = computed(() => {
    if (theme.isSelectionPhase.value) return { value: chapter.photos.value.length, label: '待归档镜头' }
    if (showThemePhotoReview.value) return { value: theme.excluded.value.length, label: '已移出镜头' }
    return { value: orphanPhotos.value.length, label: '未分配镜头' }
  })

  async function loadData() {
    if (!albumId.value) return
    loading.value = true
    errorMessage.value = ''
    try {
      const [, response] = await Promise.all([
        chapter.load(),
        httpGet<ThemeWorkspace<PhotoItem>>(`/albums/${albumId.value}/theme-workspace`),
      ])
      theme.setWorkspace(response.data)
      if (chapter.chapters.value.length) {
        granularity.value = chapter.chapters.value[0].clustering?.granularity ?? 0
      }
    } catch (error: any) {
      errorMessage.value = error.message
    } finally {
      loading.value = false
    }
  }

  async function startThemeAnalysis(useCustomTheme = false) {
    if (!albumId.value) return
    actionLoading.value = true
    errorMessage.value = ''
    try {
      const response = await theme.requestAnalysis(useCustomTheme)
      const taskId = response.data.task.id
      await refreshThemeTask(taskId)
      startThemePolling(taskId, async () => {
        theme.isRechoosing.value = false
        theme.selectedCandidateId.value = ''
        await loadData()
      })
    } catch (error: any) {
      errorMessage.value = error.message
    } finally {
      actionLoading.value = false
    }
  }

  async function confirmThemeSelection() {
    if (!theme.workspace.value?.profile || !theme.selectedCandidateId.value) return
    const confirmRebuild = chapter.chapters.value.length > 0
    if (confirmRebuild && !confirm('更换主题会清除当前章节、页面和手工调整。确定继续吗？')) return
    actionLoading.value = true
    errorMessage.value = ''
    try {
      const response = await theme.requestSelection(confirmRebuild)
      if (!response) return
      const taskId = response.data.task.id
      await refreshThemeTask(taskId)
      startThemePolling(taskId, async () => {
        theme.isRechoosing.value = false
        theme.selectedPhotoIds.value = new Set()
        await loadData()
      })
    } catch (error: any) {
      errorMessage.value = error.message
    } finally {
      actionLoading.value = false
    }
  }

  function returnToThemeSelection() {
    theme.isRechoosing.value = true
    theme.selectedCandidateId.value = ''
    theme.selectedPhotoIds.value = new Set()
    theme.customTheme.value = ''
    errorMessage.value = ''
    successMessage.value = ''
  }

  async function returnToThemeReview() {
    const confirmRebuild = chapter.chapters.value.length > 0
    if (confirmRebuild && !confirm('返回照片确认会清除当前章节、页面和手工调整。确定继续吗？')) return
    actionLoading.value = true
    errorMessage.value = ''
    try {
      await theme.reopenReview(confirmRebuild)
      theme.isRechoosing.value = false
      theme.selectedCandidateId.value = ''
      theme.selectedPhotoIds.value = new Set()
      await loadData()
    } catch (error: any) {
      errorMessage.value = error.message
    } finally {
      actionLoading.value = false
    }
  }

  async function applyThemeDecision(photoIds: string[], decision: 'keep' | 'exclude' | null) {
    if (!photoIds.length) return
    actionLoading.value = true
    try {
      await theme.updateDecisions(photoIds, decision)
      theme.selectedPhotoIds.value = new Set()
      await loadData()
    } catch (error: any) {
      errorMessage.value = error.message
    } finally {
      actionLoading.value = false
    }
  }

  async function confirmThemeReview() {
    if (theme.review.value.length) {
      errorMessage.value = `还有 ${theme.review.value.length} 张照片待处理，请先决定保留或移出。`
      return
    }
    actionLoading.value = true
    errorMessage.value = ''
    try {
      await theme.confirmReview()
      await loadData()
      successMessage.value = '主题照片范围已确认，可以开始整理章节。'
    } catch (error: any) {
      const reviewCount = Number(error?.context?.review_count)
      errorMessage.value = error?.status === 409 && Number.isFinite(reviewCount)
        ? `还有 ${reviewCount} 张照片待处理，请先在待处理照片中选择保留或移出。`
        : error.message
    } finally {
      actionLoading.value = false
    }
  }

  async function startCluster() {
    if (!albumId.value) return
    if (!theme.ready.value) {
      errorMessage.value = '请先完成主题选择和照片确认。'
      return
    }
    const confirmRebuild = chapter.chapters.value.length > 0
    if (confirmRebuild && !confirm('重新自动整理会覆盖当前章节和手工调整。确定继续吗？')) return
    actionLoading.value = true
    errorMessage.value = ''
    successMessage.value = ''
    try {
      const response = await chapter.requestCluster(confirmRebuild, granularity.value)
      const taskId = response.data.task.id
      await chapter.refreshTask(taskId)
      chapter.startPolling(taskId, async (task) => {
        await loadData()
        if (task?.task_status === 'succeeded') {
          successMessage.value = '自动章节整理完成。'
          setTimeout(() => { successMessage.value = '' }, 3000)
        }
      })
    } catch (error: any) {
      errorMessage.value = error.message
      await chapter.refreshTask()
    } finally {
      actionLoading.value = false
    }
  }

  async function createChapter() {
    if (!newChapterName.value.trim()) return
    try {
      await chapter.createChapter(newChapterName.value.trim())
      newChapterName.value = ''
      await loadData()
    } catch (error: any) {
      errorMessage.value = error.message
    }
  }

  async function renameChapter(item: ChapterItem, name: string) {
    try {
      await chapter.renameChapter(item.id, name)
      item.name = name
    } catch (error: any) {
      errorMessage.value = error.message
    }
  }

  async function deleteChapter(id: string) {
    if (!confirm('删除该章节后，其中照片会回到未分配区。确定继续吗？')) return
    try {
      await chapter.deleteChapter(id)
      await loadData()
    } catch (error: any) {
      errorMessage.value = error.message
    }
  }

  async function movePhoto(photoId: string, targetChapterId: string) {
    if (targetChapterId === '__orphan__') {
      errorMessage.value = '当前版本暂不支持直接拖回未分配区，可通过删除章节释放照片。'
      return
    }
    try {
      await chapter.movePhoto(photoId, targetChapterId)
      await loadData()
    } catch (error: any) {
      errorMessage.value = error.message
    }
  }

  function goBack() { void router.push(`/albums/${albumId.value}/cleaning`) }
  function goNext() { void router.push(`/albums/${albumId.value}/planning`) }

  onMounted(async () => {
    await loadData()
    await chapter.refreshTask()
    await refreshThemeTask()
  })
  watch(albumId, async () => {
    await loadData()
    await chapter.refreshTask()
    await refreshThemeTask()
  })
  watch(theme.isReviewPhase, (isReviewing) => {
    if (isReviewing) theme.photoView.value = theme.review.value.length ? 'review' : 'candidate'
  })

  return {
    albumId,
    loading,
    actionLoading,
    errorMessage,
    successMessage,
    newChapterName,
    granularity,
    chapters: chapter.chapters,
    allPhotos: chapter.photos,
    albumStatus: chapter.albumStatus,
    displayTask: chapter.displayTask,
    themeWorkspace: theme.workspace,
    customTheme: theme.customTheme,
    selectedCandidateId: theme.selectedCandidateId,
    selectedStrategy: theme.selectedStrategy,
    selectedThemePhotoIds: theme.selectedPhotoIds,
    themePhotoView: theme.photoView,
    isRechoosingTheme: theme.isRechoosing,
    themeReady: theme.ready,
    isThemeSelectionPhase: theme.isSelectionPhase,
    isThemeReviewPhase: theme.isReviewPhase,
    themeCandidates: theme.candidates,
    selectedCandidate: theme.selectedCandidate,
    candidateThemeAssessments: theme.kept,
    reviewThemeAssessments: theme.review,
    removedThemeAssessments: theme.excluded,
    visibleThemeAssessments: theme.visible,
    latestThemeTask,
    needCleaning,
    reviewChapterCount,
    showThemePhotoReview,
    hasGeneratedChapters,
    orphanPhotos,
    primaryPhotoMetric,
    secondaryStructureMetric,
    tertiaryPhotoMetric,
    strategyLabels: chapterStrategyLabels,
    chooseCandidate: theme.chooseCandidate,
    startThemeAnalysis,
    confirmThemeSelection,
    returnToThemeSelection,
    returnToThemeReview,
    applyThemeDecision,
    confirmThemeReview,
    startCluster,
    createChapter,
    renameChapter,
    deleteChapter,
    movePhoto,
    goBack,
    goNext,
  }
}

import { computed, ref, type Ref } from 'vue'
import { httpDelete, httpGet, httpPatch, httpPost } from '@/shared/api/http'
import { useAlbumTaskMonitor } from '@/shared/composables/useAlbumTaskMonitor'
import type { ChapterItem, PhotoItem } from '@/features/chapter-clustering/types'

export function useChapterWorkspace(albumId: Ref<string>) {
  const chapters = ref<ChapterItem[]>([])
  const photos = ref<PhotoItem[]>([])
  const albumStatus = ref('draft')
  const { latestTask, refreshTask, startPolling } = useAlbumTaskMonitor({
    albumId,
    matches: (task) => task.task_type === 'cluster_chapters',
  })
  const displayTask = computed(() => {
    const task = latestTask.value
    if (!task || task.task_status === 'failed' || task.task_status === 'cancelled') return task
    const debugPayload = { ...(task.debug_payload ?? {}) }
    delete debugPayload.stage
    delete debugPayload.reason
    return { ...task, debug_payload: debugPayload }
  })

  async function load() {
    const [chapterResponse, photoResponse, albumResponse] = await Promise.all([
      httpGet<ChapterItem[]>(`/albums/${albumId.value}/chapters`),
      httpGet<{ items: PhotoItem[] }>(`/albums/${albumId.value}/photos?recommendation=keep`),
      httpGet<{ status?: string }>(`/albums/${albumId.value}`),
    ])
    chapters.value = chapterResponse.data || []
    photos.value = photoResponse.data.items || []
    albumStatus.value = albumResponse.data?.status || 'draft'
  }

  async function requestCluster(confirmRebuild: boolean, granularity: number) {
    return httpPost<{ task: { id: string } }>(`/albums/${albumId.value}/cluster`, {
      confirm_rebuild: confirmRebuild,
      granularity,
    })
  }

  async function createChapter(name: string) {
    await httpPost(`/albums/${albumId.value}/chapters`, { name, photo_ids: [] })
  }

  async function renameChapter(chapterId: string, name: string) {
    await httpPatch(`/albums/${albumId.value}/chapters/${chapterId}`, { name })
  }

  async function deleteChapter(chapterId: string) {
    await httpDelete(`/albums/${albumId.value}/chapters/${chapterId}`)
  }

  async function movePhoto(photoId: string, targetChapterId: string) {
    await httpPost(`/albums/${albumId.value}/chapters/move-photos`, {
      photo_ids: [photoId],
      target_chapter_id: targetChapterId,
    })
  }

  return {
    chapters,
    photos,
    albumStatus,
    latestTask,
    displayTask,
    refreshTask,
    startPolling,
    load,
    requestCluster,
    createChapter,
    renameChapter,
    deleteChapter,
    movePhoto,
  }
}

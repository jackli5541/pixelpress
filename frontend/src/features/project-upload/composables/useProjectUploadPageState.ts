import { computed, onMounted, reactive, ref, watch, type Ref } from 'vue'
import type { Router } from 'vue-router'
import { currentUser } from '@/shared/auth'
import { ApiError, httpDelete, httpGet, httpPost, httpPostForm } from '@/shared/api/http'
import { getAlbumResumeRoute } from '@/shared/workflow/albumWorkflow'
import type { AlbumCard } from '@/shared/types/album'
import type { ProjectSummary } from '@/shared/types/admin'

const MAX_BATCH_FILES = 50
const MAX_BATCH_BYTES = 160 * 1024 * 1024
const MAX_PARALLEL_BATCHES = 2
const MAX_UPLOAD_RETRIES = 3

interface UploadRejectedItem {
  filename: string
  reason: string
}

interface UploadBatchResult {
  uploaded: UploadedPhotoItem[]
  rejected: UploadRejectedItem[]
}

export interface UploadedPhotoItem {
  id: string
  album_id: string
  filename: string
  content_type: string
  size: number
  storage_key: string
  url: string
  uploaded_at: string
  taken_at?: string | null
  taken_timezone?: string | null
  gps_latitude?: number | null
  gps_longitude?: number | null
  device_model?: string | null
}

interface UseProjectUploadPageStateOptions {
  albumId: Ref<string>
  router: Router
  apiBase: string
}

export function useProjectUploadPageState(options: UseProjectUploadPageStateOptions) {
  const form = reactive({
    name: '',
    project_id: '',
    album_type: 'yearbook',
    book_size: 'square_10inch',
    theme_style: 'minimal',
    cover_title: '',
  })

  const albums = ref<AlbumCard[]>([])
  const projects = ref<ProjectSummary[]>([])
  const currentAlbum = ref<AlbumCard | null>(null)
  const photos = ref<UploadedPhotoItem[]>([])
  const loading = ref(false)
  const projectsLoading = ref(false)
  const submitting = ref(false)
  const uploading = ref(false)
  const deletingProjectId = ref('')
  const deletingAlbumIds = ref<string[]>([])
  const deletingPhotoIds = ref<string[]>([])
  const showDeleteProjectDialog = ref(false)
  const projectPendingDelete = ref<ProjectSummary | null>(null)
  const deleteProjectError = ref('')
  const errorMessage = ref('')
  const successMessage = ref('')
  const uploadProgress = ref(0)
  const uploadTotal = ref(0)
  const fileInput = ref<HTMLInputElement | null>(null)

  const isAuthenticated = computed(() => Boolean(currentUser.value))
  const selectedProject = computed(() => projects.value.find((project) => project.id === form.project_id) ?? null)
  const currentProject = computed(() => {
    const projectId = currentAlbum.value?.project_id || form.project_id
    return projects.value.find((project) => project.id === projectId) ?? null
  })

  async function loadAlbums() {
    if (!isAuthenticated.value) {
      albums.value = []
      return
    }
    loading.value = true
    errorMessage.value = ''
    try {
      const response = await httpGet<AlbumCard[]>('/albums')
      albums.value = response.data
    } catch (error: any) {
      errorMessage.value = error.message
    } finally {
      loading.value = false
    }
  }

  async function loadProjects() {
    if (!isAuthenticated.value) {
      projects.value = []
      form.project_id = ''
      return
    }
    projectsLoading.value = true
    try {
      const response = await httpGet<ProjectSummary[]>('/users/me/projects')
      projects.value = response.data
      const hasCurrentSelection = response.data.some((project) => project.id === form.project_id)
      if ((!form.project_id || !hasCurrentSelection) && response.data.length > 0) {
        form.project_id = response.data[0].id
      }
      if (response.data.length === 0) {
        form.project_id = ''
      }
    } catch (error: any) {
      errorMessage.value = error.message
    } finally {
      projectsLoading.value = false
    }
  }

  async function loadCurrentAlbum() {
    if (!options.albumId.value) {
      currentAlbum.value = null
      return
    }
    try {
      const response = await httpGet<AlbumCard>(`/albums/${options.albumId.value}`)
      currentAlbum.value = response.data
    } catch {
      currentAlbum.value = null
    }
  }

  async function loadPhotos() {
    if (!options.albumId.value) return
    try {
      const response = await httpGet<{ items: UploadedPhotoItem[] }>(`/albums/${options.albumId.value}/photos`)
      photos.value = response.data.items
    } catch {
      photos.value = []
    }
  }

  async function submitAlbum() {
    if (!isAuthenticated.value) {
      await options.router.push({ name: 'login', query: { redirect: '/albums/create' } })
      return
    }
    if (!form.name.trim()) {
      errorMessage.value = '请填写相册名称。'
      return
    }
    if (!form.project_id) {
      errorMessage.value = '请先选择所属项目。'
      return
    }
    submitting.value = true
    errorMessage.value = ''
    try {
      const response = await httpPost<AlbumCard>('/albums', {
        ...form,
        project_id: form.project_id,
        cover_title: form.cover_title || null,
      })
      await loadAlbums()
      await options.router.push(`/albums/${response.data.id}/upload`)
    } catch (error: any) {
      errorMessage.value = error.message
    } finally {
      submitting.value = false
    }
  }

  function triggerFileSelect() {
    fileInput.value?.click()
  }

  function goToAlbumResume(album: AlbumCard) {
    void options.router.push(album.resume_route || getAlbumResumeRoute(album.id, album.status))
  }

  function openDeleteProjectDialog(project: ProjectSummary) {
    projectPendingDelete.value = project
    deleteProjectError.value = ''
    showDeleteProjectDialog.value = true
  }

  function closeDeleteProjectDialog() {
    showDeleteProjectDialog.value = false
    projectPendingDelete.value = null
    deleteProjectError.value = ''
    deletingProjectId.value = ''
  }

  async function refreshAlbumWorkspaceState() {
    await Promise.all([loadAlbums(), loadProjects(), loadCurrentAlbum()])
    if (options.albumId.value) {
      await loadPhotos()
    }
  }

  function addDeletingAlbumId(albumId: string) {
    if (!deletingAlbumIds.value.includes(albumId)) {
      deletingAlbumIds.value = [...deletingAlbumIds.value, albumId]
    }
  }

  function removeDeletingAlbumId(albumId: string) {
    deletingAlbumIds.value = deletingAlbumIds.value.filter((id) => id !== albumId)
  }

  async function confirmDeleteProject() {
    const project = projectPendingDelete.value
    if (!project) return

    deletingProjectId.value = project.id
    deleteProjectError.value = ''
    try {
      await httpDelete(`/users/me/projects/${project.id}`)
      await refreshAlbumWorkspaceState()
      if (currentAlbum.value?.project_id !== project.id) {
        successMessage.value = `项目《${project.name}》已删除。`
        closeDeleteProjectDialog()
      } else {
        currentAlbum.value = null
        photos.value = []
        successMessage.value = `项目《${project.name}》已删除。`
        closeDeleteProjectDialog()
        void options.router.push('/')
      }
    } catch (error: any) {
      deleteProjectError.value = error.message
    } finally {
      deletingProjectId.value = ''
    }
  }

  async function deleteAlbum(album: AlbumCard) {
    if (!window.confirm(`确定删除相册《${album.name}》吗？此操作会删除该相册下的照片、章节、页面与导出内容。`)) return

    addDeletingAlbumId(album.id)
    errorMessage.value = ''
    try {
      await httpDelete(`/albums/${album.id}`)
      const deletingCurrentAlbum = options.albumId.value === album.id
      await refreshAlbumWorkspaceState()
      successMessage.value = `相册《${album.name}》已删除。`
      window.setTimeout(() => {
        successMessage.value = ''
      }, 3000)
      if (deletingCurrentAlbum) {
        currentAlbum.value = null
        photos.value = []
        void options.router.push('/')
      }
    } catch (error: any) {
      errorMessage.value = error.message
    } finally {
      removeDeletingAlbumId(album.id)
    }
  }

  function createUploadBatches(fileList: File[]) {
    const batches: File[][] = []
    let currentBatch: File[] = []
    let currentBytes = 0

    for (const file of fileList) {
      const fileSize = Math.max(file.size || 0, 1)
      const shouldSplit = currentBatch.length > 0 && (currentBatch.length >= MAX_BATCH_FILES || currentBytes + fileSize > MAX_BATCH_BYTES)
      if (shouldSplit) {
        batches.push(currentBatch)
        currentBatch = []
        currentBytes = 0
      }
      currentBatch.push(file)
      currentBytes += fileSize
    }

    if (currentBatch.length > 0) {
      batches.push(currentBatch)
    }
    return batches
  }

  function wait(milliseconds: number) {
    return new Promise((resolve) => window.setTimeout(resolve, milliseconds))
  }

  async function uploadBatch(batch: File[]) {
    for (let attempt = 0; ; attempt += 1) {
      const formData = new FormData()
      for (const file of batch) {
        formData.append('files', file)
      }
      try {
        const response = await httpPostForm<UploadBatchResult>(`/albums/${options.albumId.value}/photos/upload`, formData)
        return response.data
      } catch (error) {
        if (!(error instanceof ApiError) || error.status !== 429 || attempt >= MAX_UPLOAD_RETRIES) throw error
        const fallbackSeconds = [1, 2, 4][attempt] ?? 4
        const retrySeconds = error.retryAfterSeconds ?? fallbackSeconds
        await wait(retrySeconds * 1000 + Math.floor(Math.random() * 250))
      }
    }
  }

  function formatRejectedSummary(items: UploadRejectedItem[]) {
    const preview = items.slice(0, 4).map((item) => `${item.filename}（${item.reason}）`).join('，')
    const remainder = items.length > 4 ? ` 等 ${items.length} 个文件` : ''
    return `部分文件被拒绝：${preview}${remainder}`
  }

  function formatBatchFailure(batch: File[], error: unknown) {
    const names = batch.slice(0, 3).map((file) => file.name).join('，')
    const prefix = batch.length > 3 ? `${names} 等文件` : names
    return `${prefix} 上传失败：${formatUploadError(error)}`
  }

  function formatUploadError(error: unknown) {
    if (error instanceof ApiError) {
      if (error.status === 413) {
        return '单批上传内容过大，请减少单批体积后重试。'
      }
      if (error.status === 429) {
        return '上传请求仍然过快，系统已自动重试 3 次，请稍后继续。'
      }
      return error.detail
    }
    if (error instanceof Error) {
      return error.message
    }
    return '上传失败，请稍后重试。'
  }

  async function processUploadBatches(fileList: File[]) {
    const batches = createUploadBatches(fileList)
    const uploadedItems: UploadedPhotoItem[] = []
    const rejectedItems: UploadRejectedItem[] = []
    const failedBatches: string[] = []
    let nextIndex = 0

    async function worker() {
      while (nextIndex < batches.length) {
        const batchIndex = nextIndex
        nextIndex += 1
        const batch = batches[batchIndex]
        try {
          const result = await uploadBatch(batch)
          uploadedItems.push(...result.uploaded)
          rejectedItems.push(...result.rejected)
        } catch (error) {
          failedBatches.push(formatBatchFailure(batch, error))
        } finally {
          uploadProgress.value += batch.length
        }
      }
    }

    const workerCount = Math.min(MAX_PARALLEL_BATCHES, batches.length)
    await Promise.all(Array.from({ length: workerCount }, () => worker()))

    return { uploadedItems, rejectedItems, failedBatches }
  }

  async function handleFilesSelected(event: Event) {
    const input = event.target as HTMLInputElement
    const files = input.files
    if (!files || !files.length) return

    if (!isAuthenticated.value) {
      input.value = ''
      await options.router.push({
        name: 'login',
        query: { redirect: options.albumId.value ? `/albums/${options.albumId.value}/upload` : '/albums/create' },
      })
      return
    }

    if (!options.albumId.value) {
      errorMessage.value = '请先创建或选择相册。'
      input.value = ''
      return
    }

    const fileList = Array.from(files)
    uploading.value = true
    successMessage.value = ''
    errorMessage.value = ''
    uploadTotal.value = fileList.length
    uploadProgress.value = 0

    try {
      const { uploadedItems, rejectedItems, failedBatches } = await processUploadBatches(fileList)
      await refreshAlbumWorkspaceState()

      if (uploadedItems.length > 0) {
        successMessage.value = `成功收录 ${uploadedItems.length} 张照片。`
        window.setTimeout(() => {
          successMessage.value = ''
        }, 3000)
      }

      const messageParts: string[] = []
      if (rejectedItems.length > 0) {
        messageParts.push(formatRejectedSummary(rejectedItems))
      }
      if (failedBatches.length > 0) {
        messageParts.push(failedBatches.join('；'))
      }
      errorMessage.value = messageParts.join('；')
      if (!uploadedItems.length && !messageParts.length) {
        errorMessage.value = '未检测到可上传的照片。'
      }
    } catch (error: any) {
      errorMessage.value = formatUploadError(error)
    } finally {
      uploading.value = false
      input.value = ''
    }
  }

  function addDeletingPhotoId(photoId: string) {
    if (!deletingPhotoIds.value.includes(photoId)) {
      deletingPhotoIds.value = [...deletingPhotoIds.value, photoId]
    }
  }

  function removeDeletingPhotoId(photoId: string) {
    deletingPhotoIds.value = deletingPhotoIds.value.filter((id) => id !== photoId)
  }

  async function deletePhoto(photo: UploadedPhotoItem) {
    if (!options.albumId.value) return
    if (!window.confirm(`确定删除照片《${photo.filename}》吗？`)) return

    addDeletingPhotoId(photo.id)
    errorMessage.value = ''
    try {
      await httpDelete(`/albums/${options.albumId.value}/photos/${photo.id}`)
      photos.value = photos.value.filter((item) => item.id !== photo.id)
      await refreshAlbumWorkspaceState()
      successMessage.value = `已删除照片《${photo.filename}》。`
      window.setTimeout(() => {
        successMessage.value = ''
      }, 3000)
    } catch (error: any) {
      errorMessage.value = error.message
    } finally {
      removeDeletingPhotoId(photo.id)
    }
  }

  async function goToCleaning() {
    if (!options.albumId.value) return
    if (!isAuthenticated.value) {
      await options.router.push({ name: 'login', query: { redirect: `/albums/${options.albumId.value}/cleaning` } })
      return
    }
    await options.router.push(`/albums/${options.albumId.value}/cleaning`)
  }

  function formatFileSize(bytes: number): string {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  }

  onMounted(async () => {
    await refreshAlbumWorkspaceState()
  })

  watch(
    () => options.albumId.value,
    async () => {
      photos.value = []
      await refreshAlbumWorkspaceState()
    },
  )

  return {
    form,
    albums,
    projects,
    currentAlbum,
    photos,
    loading,
    projectsLoading,
    submitting,
    uploading,
    deletingProjectId,
    deletingAlbumIds,
    deletingPhotoIds,
    showDeleteProjectDialog,
    projectPendingDelete,
    deleteProjectError,
    errorMessage,
    successMessage,
    uploadProgress,
    uploadTotal,
    fileInput,
    isAuthenticated,
    selectedProject,
    currentProject,
    refreshAlbumWorkspaceState,
    formatFileSize,
    submitAlbum,
    triggerFileSelect,
    goToAlbumResume,
    openDeleteProjectDialog,
    closeDeleteProjectDialog,
    confirmDeleteProject,
    deleteAlbum,
    handleFilesSelected,
    deletePhoto,
    goToCleaning,
  }
}

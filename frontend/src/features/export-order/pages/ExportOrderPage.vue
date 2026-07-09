<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import SectionCard from '@/shared/components/SectionCard.vue'
import StoryHero from '@/shared/components/StoryHero.vue'
import WorkflowStepper from '@/shared/components/WorkflowStepper.vue'
import AlbumTaskStatusCard from '@/shared/components/AlbumTaskStatusCard.vue'
import { getAccessToken, httpGet, httpPost } from '@/shared/api/http'
import type { ExportItem, TaskItem } from '@/shared/types/album'
import { useAlbumTaskMonitor } from '@/shared/composables/useAlbumTaskMonitor'

interface PreviewData {
  album_id: string
  html: string
}

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000/api/v1'

const route = useRoute()
const router = useRouter()

const exportsInfo = ref<ExportItem[]>([])
const albumStatus = ref('draft')
const loading = ref(false)
const actionLoading = ref(false)
const errorMessage = ref('')
const successMessage = ref('')
const pendingMessage = ref('')
const activeExportTaskId = ref('')
const activeExportFormat = ref<'html' | 'pdf' | ''>('')
const previewHtml = ref('')
const showPreview = ref(false)
const previewLoading = ref(false)

const albumId = computed(() => {
  const id = route.params.id
  return typeof id === 'string' ? id : ''
})

const needRender = computed(() => ['draft', 'uploaded', 'cleaned', 'clustered', 'planned'].includes(albumStatus.value))
const { latestTask, refreshTask, startPolling, stopPolling } = useAlbumTaskMonitor({
  albumId,
  matches: (task) => task.task_type.startsWith('export_'),
})

function formatFileSize(bytes: number | undefined) {
  if (!bytes) return '-'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function exportLabel(item: ExportItem) {
  return item.format === 'pdf' ? 'PDF' : 'HTML'
}

function getQueuedExportMessage(format: 'html' | 'pdf') {
  return format === 'pdf' ? 'PDF 导出任务已提交，正在生成文件。' : 'HTML 导出任务已提交，正在生成文件。'
}

function getSuccessExportMessage(format: 'html' | 'pdf') {
  return format === 'pdf' ? 'PDF 导出完成。' : 'HTML 导出完成。'
}

async function applyExportTaskOutcome(task: TaskItem | null) {
  pendingMessage.value = ''
  if (!task) {
    errorMessage.value = '导出任务状态获取失败。'
    return
  }

  await loadData()
  await refreshTask(task.id)

  if (task.task_status === 'succeeded') {
    successMessage.value = getSuccessExportMessage(activeExportFormat.value as 'html' | 'pdf')
    return
  }

  if (['failed', 'cancelled', 'skipped'].includes(task.task_status)) {
    const debugReason = task.debug_payload && typeof task.debug_payload.reason === 'string' ? task.debug_payload.reason : ''
    errorMessage.value = task.error_message || debugReason || '导出失败。'
  }
}

async function loadData() {
  if (!albumId.value) return
  loading.value = true
  errorMessage.value = ''
  try {
    const [exportResponse, albumResponse] = await Promise.all([
      httpGet<ExportItem[]>(`/albums/${albumId.value}/exports`),
      httpGet<any>(`/albums/${albumId.value}`),
    ])
    exportsInfo.value = exportResponse.data || []
    albumStatus.value = albumResponse.data?.status || 'draft'
  } catch (error: any) {
    errorMessage.value = error.message
  } finally {
    loading.value = false
  }
}

function goBack() {
  void router.push(`/albums/${albumId.value}/planning`)
}

async function doExport(format: 'html' | 'pdf') {
  if (!albumId.value) return
  stopPolling()
  actionLoading.value = true
  errorMessage.value = ''
  successMessage.value = ''
  pendingMessage.value = ''
  activeExportTaskId.value = ''
  activeExportFormat.value = format
  try {
    const response = await httpPost<{ task: TaskItem; status_url: string }>(`/albums/${albumId.value}/export?format=${format}`)
    const task = response.data.task
    activeExportTaskId.value = task.id
    pendingMessage.value = getQueuedExportMessage(format)
    await refreshTask(task.id)
    startPolling(task.id, async (terminalTask) => {
      await applyExportTaskOutcome(terminalTask)
    })
  } catch (error: any) {
    errorMessage.value = error.message
    await refreshTask(activeExportTaskId.value || undefined)
  } finally {
    actionLoading.value = false
  }
}

async function loadPreview() {
  if (!albumId.value) return
  previewLoading.value = true
  try {
    const response = await httpGet<PreviewData>(`/albums/${albumId.value}/preview`)
    previewHtml.value = response.data.html
    showPreview.value = true
  } catch {
    errorMessage.value = '预览暂不可用，请先完成渲染。'
  } finally {
    previewLoading.value = false
  }
}

async function downloadExport(item: ExportItem) {
  try {
    const token = getAccessToken()
    const response = await fetch(`${API_BASE}/albums/${albumId.value}/export/download/${item.id}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
    if (!response.ok) throw new Error(`下载失败 (${response.status})`)
    const blob = await response.blob()
    const url = window.URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `${item.id}.${item.format === 'pdf' ? 'pdf' : 'html'}`
    document.body.appendChild(link)
    link.click()
    link.remove()
    window.URL.revokeObjectURL(url)
  } catch (error: any) {
    errorMessage.value = error.message
  }
}

onMounted(async () => {
  await loadData()
  await refreshTask()
})
watch(
  () => albumId.value,
  async () => {
    stopPolling()
    pendingMessage.value = ''
    activeExportTaskId.value = ''
    activeExportFormat.value = ''
    await loadData()
    await refreshTask()
  },
)

onBeforeUnmount(() => {
  stopPolling()
})
</script>

<template>
  <WorkflowStepper v-if="albumId" :album-id="albumId" :album-status="albumStatus" />

  <div class="space-y-6">
    <StoryHero
      eyebrow="Final Cut"
      title="确认成册效果，然后导出你的故事书"
      description="在导出前先检查整册预览，确认页面节奏、内容排布和章节完整性。这里更像成片交付，而不是简单下载文件。"
    >
      <div class="grid gap-4 md:grid-cols-3">
        <div class="story-panel rounded-[24px] px-4 py-4">
          <p class="font-story text-3xl text-[var(--story-gold-soft)]">{{ exportsInfo.length }}</p>
          <p class="mt-2 text-sm text-[var(--story-text)]">导出记录</p>
        </div>
        <div class="story-panel rounded-[24px] px-4 py-4">
          <p class="font-story text-3xl text-[var(--story-gold-soft)]">{{ latestTask?.task_status || 'idle' }}</p>
          <p class="mt-2 text-sm text-[var(--story-text)]">最近导出状态</p>
        </div>
        <div class="story-panel rounded-[24px] px-4 py-4">
          <p class="font-story text-3xl text-[var(--story-gold-soft)]">{{ albumStatus }}</p>
          <p class="mt-2 text-sm text-[var(--story-text)]">当前作品状态</p>
        </div>
      </div>
    </StoryHero>

    <SectionCard
      title="导出中心"
      description="先查看整册效果，再选择 HTML 或 PDF 输出。整条导出链路要尽量像最终成片交付，而不是裸文件下载。"
      tone="film"
      eyebrow="Step 5"
    >
      <div v-if="!loading && needRender" class="rounded-[22px] border border-[#8e6732] bg-[rgba(170,120,44,0.14)] px-4 py-4 text-sm text-[var(--story-muted)]">
        请先完成页面渲染，再进入导出环节。
        <button class="story-button-secondary ml-3 px-4 py-2 text-sm" @click="goBack">返回页面编排</button>
      </div>

      <div class="mt-4">
        <AlbumTaskStatusCard
          :task="latestTask"
          title="导出任务"
          running-hint="系统正在生成导出文件，页面会自动轮询最新状态。"
          empty-text="点击导出按钮后，这里会显示导出任务状态、格式和警告信息。"
        />
      </div>

      <div class="mt-4 grid gap-4 lg:grid-cols-[1.1fr_0.9fr]">
        <div class="rounded-[24px] border border-[rgba(224,177,106,0.16)] bg-[rgba(255,255,255,0.03)] p-5">
          <div class="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p class="text-xs uppercase tracking-[0.24em] text-[var(--story-faint)]">Preview</p>
              <p class="mt-2 font-story text-4xl text-[var(--story-gold-soft)]">Before Export</p>
            </div>
            <button class="story-button-secondary px-5 py-3 text-sm" :disabled="previewLoading" @click="loadPreview">
              {{ previewLoading ? '加载中...' : showPreview ? '刷新预览' : '查看预览' }}
            </button>
          </div>

          <div v-if="!showPreview" class="mt-4 rounded-[22px] border border-dashed border-[rgba(224,177,106,0.18)] px-5 py-12 text-center text-sm text-[var(--story-muted)]">
            先查看整册预览，再决定最终导出格式。
          </div>
          <div v-else class="mt-4 max-h-[360px] overflow-auto rounded-[22px] bg-white">
            <div v-html="previewHtml" />
          </div>
        </div>

        <div class="paper-panel rounded-[24px] p-5">
          <p class="text-xs uppercase tracking-[0.24em] text-[#8e6d45]">Export Actions</p>
          <p class="font-story mt-3 text-4xl text-[#241c16]">Choose Format</p>
          <p class="mt-3 text-sm leading-7 text-[#5f5347]">
            HTML 更适合在线预览或继续调试，PDF 更适合打印与交付。
          </p>

          <div class="mt-5 space-y-3">
            <button class="story-button w-full px-6 py-3 text-sm" :disabled="!albumId || actionLoading" @click="doExport('html')">
              {{ actionLoading ? '导出中...' : '导出 HTML 版本' }}
            </button>
            <button class="story-button-secondary w-full px-6 py-3 text-sm !text-[#241c16] !bg-[rgba(43,31,24,0.08)]" :disabled="!albumId || actionLoading" @click="doExport('pdf')">
              {{ actionLoading ? '导出中...' : '导出 PDF 版本' }}
            </button>
          </div>

          <div v-if="pendingMessage || successMessage || errorMessage" class="mt-5 space-y-3">
            <p v-if="pendingMessage" class="rounded-[18px] bg-[rgba(224,177,106,0.16)] px-4 py-3 text-sm text-[var(--story-text)]">{{ pendingMessage }}</p>
            <p v-if="successMessage" class="rounded-[18px] bg-[#dcead5] px-4 py-3 text-sm text-[#47673d]">{{ successMessage }}</p>
            <p v-if="errorMessage" class="rounded-[18px] bg-[#f6d9d3] px-4 py-3 text-sm text-[#8b4339]">{{ errorMessage }}</p>
          </div>
        </div>
      </div>
    </SectionCard>

    <SectionCard
      v-if="exportsInfo.length > 0"
      title="已生成版本"
      :description="`目前共有 ${exportsInfo.length} 个导出文件。可以继续下载或重复生成。`"
      tone="accent"
      eyebrow="Exports"
    >
      <div class="space-y-3">
        <article v-for="item in exportsInfo" :key="item.id" class="flex flex-wrap items-center justify-between gap-4 rounded-[22px] border border-[rgba(79,59,42,0.14)] bg-white/72 px-5 py-4">
          <div>
            <p class="text-sm font-medium text-[#241c16]">
              {{ exportLabel(item) }} 文件
              <span class="ml-2 rounded-full bg-[#f4e0be] px-3 py-1 text-xs text-[#8e6d45]">{{ item.status }}</span>
            </p>
            <p class="mt-2 text-xs text-[#78695c]">{{ item.created_at }} | {{ formatFileSize(item.file_size || undefined) }}</p>
          </div>
          <button
            v-if="item.status === 'completed' || item.file_path"
            class="story-button px-5 py-3 text-sm"
            @click="downloadExport(item)"
          >
            下载
          </button>
          <span v-else class="rounded-full bg-[rgba(43,31,24,0.08)] px-4 py-2 text-sm text-[#5f5347]">{{ item.status }}</span>
        </article>
      </div>
    </SectionCard>

    <div v-else-if="!loading && albumId" class="story-panel rounded-[28px] px-6 py-12 text-center">
      <p class="font-story text-4xl text-[var(--story-gold-soft)]">No Export Yet</p>
      <p class="mt-3 text-sm text-[var(--story-muted)]">完成预览确认后，即可在这里生成第一版导出文件。</p>
    </div>

    <div v-if="showPreview" class="fixed inset-0 z-50 flex items-start justify-center overflow-auto bg-black/70 p-4" @click.self="showPreview = false">
      <div class="paper-panel my-8 w-full max-w-5xl overflow-hidden rounded-[28px]">
        <div class="flex items-center justify-between border-b border-[rgba(79,59,42,0.12)] px-6 py-4">
          <p class="font-story text-3xl text-[#241c16]">整册预览</p>
          <button class="rounded-full bg-[rgba(43,31,24,0.08)] px-4 py-2 text-sm text-[#3f342b]" @click="showPreview = false">
            关闭
          </button>
        </div>
        <div class="max-h-[75vh] overflow-auto bg-white px-4 py-4" v-html="previewHtml" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import SectionCard from '@/shared/components/SectionCard.vue'
import WorkflowStepper from '@/shared/components/WorkflowStepper.vue'
import { httpGet, httpPost } from '@/shared/api/http'
import type { ExportItem, TaskItem } from '@/shared/types/album'

interface PreviewData { album_id: string; html: string }

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000/api/v1'
const route = useRoute(); const router = useRouter()
const exportsInfo = ref<ExportItem[]>([])
const tasks = ref<TaskItem[]>([])
const albumStatus = ref<string>('draft')
const loading = ref(false); const actionLoading = ref(false)
const errorMessage = ref(''); const successMessage = ref('')
const previewHtml = ref(''); const showPreview = ref(false)
const previewLoading = ref(false)

const albumId = computed(() => { const id = route.params.id; return typeof id === 'string' ? id : '' })
const needRender = computed(() => {
  const idx = ['draft','uploaded','cleaned','clustered','planned','rendered','exported'].indexOf(albumStatus.value)
  return idx < 5 // status < "rendered"
})
const latestTask = computed(() => tasks.value.find(t => t.task_type?.startsWith('export')))

function formatFileSize(bytes: number | undefined): string { if (!bytes) return '-'; if (bytes < 1024) return `${bytes} B`; if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`; return `${(bytes / (1024 * 1024)).toFixed(1)} MB` }

async function loadData() {
  if (!albumId.value) return; loading.value = true; errorMessage.value = ''
  try {
    const [expRes, taskRes, albRes] = await Promise.all([
      httpGet<ExportItem[]>(`/albums/${albumId.value}/exports`),
      httpGet<TaskItem[]>('/tasks'),
      httpGet<any>(`/albums/${albumId.value}`),
    ])
    exportsInfo.value = expRes.data || []; tasks.value = taskRes.data.filter(t => t.album_id === albumId.value)
    albumStatus.value = albRes.data?.status || 'draft'
  } catch (e: any) { errorMessage.value = e.message } finally { loading.value = false }
}

function goBack() { router.push(`/albums/${albumId.value}/planning`) }

async function doExport(format: 'html' | 'pdf') {
  if (!albumId.value) return; actionLoading.value = true; errorMessage.value = ''; successMessage.value = ''
  try { const r = await httpPost<ExportItem>(`/albums/${albumId.value}/export?format=${format}`); successMessage.value = r.message || '导出完成'; await loadData() } catch (e: any) { errorMessage.value = e.message } finally { actionLoading.value = false }
}

async function loadPreview() {
  if (!albumId.value) return; previewLoading.value = true
  try { const r = await httpGet<PreviewData>(`/albums/${albumId.value}/preview`); previewHtml.value = r.data.html; showPreview.value = true } catch (e: any) { errorMessage.value = '预览不可用，请先执行排版渲染。' } finally { previewLoading.value = false }
}

function downloadUrl(item: ExportItem) { return `${API_BASE}/albums/${albumId.value}/export/download/${item.id}` }
function fmtLabel(item: ExportItem): string { return (item as any).format === 'pdf' ? 'PDF' : 'HTML' }

onMounted(loadData); watch(() => albumId.value, loadData)
</script>

<template>
  <WorkflowStepper v-if="albumId" :album-id="albumId" :album-status="albumStatus" />

  <div class="space-y-6">
    <div v-if="!loading && needRender" class="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-700 flex items-center justify-between">
      <span>请先完成排版渲染，再进入导出。</span>
      <button class="rounded-full bg-amber-200 px-4 py-1.5 text-xs text-amber-800 hover:bg-amber-300" @click="goBack">返回排版</button>
    </div>
    <SectionCard title="导出中心" description="导出前可预览全册排版效果。选择 HTML 或 PDF 格式导出。"
      eyebrow="步骤 5" tone="accent">

      <!-- 预览区 -->
      <div class="mb-4 rounded-2xl border border-slate-200 bg-slate-50 p-4">
        <div class="flex items-center justify-between mb-3">
          <p class="text-sm font-semibold text-slate-900">预览</p>
          <button class="rounded-full border border-slate-300 bg-white px-4 py-2 text-sm text-slate-600 hover:bg-slate-100 disabled:opacity-50"
            :disabled="previewLoading" @click="loadPreview">
            {{ previewLoading ? '加载中...' : showPreview ? '刷新预览' : '显示预览' }}
          </button>
        </div>
        <div v-if="!showPreview" class="rounded-xl border border-dashed border-slate-300 py-10 text-center">
          <p class="text-sm text-slate-400">点击「显示预览」查看排版效果，满意后再导出。</p>
        </div>
        <div v-else class="rounded-xl border border-slate-200 bg-white overflow-auto" style="max-height:360px">
          <div v-html="previewHtml" />
        </div>
      </div>

      <!-- 导出按钮 -->
      <div class="flex flex-wrap items-center gap-3">
        <button class="rounded-full bg-cyan-600 px-6 py-3 text-sm text-white hover:bg-cyan-700 disabled:bg-slate-400"
          :disabled="!albumId || actionLoading" @click="doExport('html')">
          {{ actionLoading ? '导出中...' : '导出 HTML' }}
        </button>
        <button class="rounded-full border border-slate-300 bg-white px-6 py-3 text-sm text-slate-700 hover:border-slate-400 disabled:text-slate-400"
          :disabled="!albumId || actionLoading" @click="doExport('pdf')">
          {{ actionLoading ? '导出中...' : '导出 PDF' }}
        </button>
        <span class="text-sm text-slate-500">状态：{{ latestTask?.task_status || '空闲' }}</span>
        <span v-if="successMessage" class="text-sm text-emerald-600">{{ successMessage }}</span>
        <span v-if="errorMessage" class="text-sm text-rose-600">{{ errorMessage }}</span>
      </div>
    </SectionCard>

    <SectionCard v-if="exportsInfo.length > 0" title="导出记录" :description="`共 ${exportsInfo.length} 次`">
      <div class="space-y-3">
        <div v-for="item in exportsInfo" :key="item.id" class="flex items-center justify-between rounded-2xl border border-slate-200 bg-slate-50 px-5 py-4">
          <div>
            <p class="text-sm font-medium text-slate-900">{{ item.id.slice(0, 8) }}...{{ fmtLabel(item) === 'PDF' ? 'pdf' : 'html' }}
              <span class="ml-2 rounded-full bg-slate-200 px-2 py-0.5 text-[10px] text-slate-600">{{ fmtLabel(item) }}</span>
            </p>
            <p class="mt-1 text-xs text-slate-500">{{ item.created_at }} &middot; {{ formatFileSize((item as any).file_size) }} &middot; {{ item.status }}</p>
          </div>
          <a v-if="item.status === 'completed' || item.file_path" :href="downloadUrl(item)"
            class="rounded-full bg-cyan-600 px-5 py-2.5 text-sm text-white hover:bg-cyan-700 shadow-sm" download target="_blank">下载</a>
          <span v-else class="rounded-full bg-slate-200 px-3 py-1 text-xs text-slate-600">{{ item.status }}</span>
        </div>
      </div>
    </SectionCard>

    <div v-else-if="!loading && albumId" class="rounded-2xl border border-dashed border-slate-300 px-4 py-10 text-center">
      <p class="text-slate-500">暂无导出记录。完成前面步骤后点击导出。</p>
      <p class="mt-2 text-xs text-slate-400">流程：上传 &rarr; 清洗 &rarr; 章节 &rarr; 排版 &rarr; 渲染 &rarr; 导出</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import SectionCard from '@/shared/components/SectionCard.vue'
import WorkflowStepper from '@/shared/components/WorkflowStepper.vue'
import { httpGet, httpPost } from '@/shared/api/http'

interface PhotoItem { id: string; filename: string; size: number; url: string; quality_score?: number | null; cleaning_recommendation?: string | null; cleaning_issues?: string[] | null }

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000/api/v1'
const route = useRoute(); const router = useRouter()
const album = ref<any>(null); const photos = ref<PhotoItem[]>([])
const loading = ref(false); const actionLoading = ref(false)
const errorMessage = ref(''); const successMessage = ref('')
const selectedIds = ref<Set<string>>(new Set()); const showRemoved = ref(false)

const albumId = computed(() => { const id = route.params.id; return typeof id === 'string' ? id : '' })
const keepPhotos = computed(() => photos.value.filter(p => p.cleaning_recommendation !== 'remove'))
const removedPhotos = computed(() => photos.value.filter(p => p.cleaning_recommendation === 'remove'))
const unscoredPhotos = computed(() => photos.value.filter(p => p.quality_score == null))

function formatFileSize(bytes: number): string { if (bytes < 1024) return `${bytes} B`; if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`; return `${(bytes / (1024 * 1024)).toFixed(1)} MB` }
function toggleSelect(photoId: string) { const n = new Set(selectedIds.value); if (n.has(photoId)) n.delete(photoId); else n.add(photoId); selectedIds.value = n }
function toggleSelectAll() { selectedIds.value = selectedIds.value.size === keepPhotos.value.length ? new Set() : new Set(keepPhotos.value.map(p => p.id)) }

async function loadData() {
  if (!albumId.value) return; loading.value = true; errorMessage.value = ''
  try { const [ar, pr] = await Promise.all([httpGet<any>(`/albums/${albumId.value}`), httpGet<{ items: PhotoItem[] }>(`/albums/${albumId.value}/photos`)]); album.value = ar.data; photos.value = pr.data.items || [] } catch (e: any) { errorMessage.value = e.message } finally { loading.value = false }
}

async function startCleaning() { if (!albumId.value) return; actionLoading.value = true; try { await httpPost(`/albums/${albumId.value}/clean`); await loadData(); successMessage.value = '清洗完成' } catch (e: any) { errorMessage.value = e.message } finally { actionLoading.value = false; setTimeout(() => successMessage.value = '', 3000) } }

async function updateDecision(photo: PhotoItem, decision: string) {
  try { await fetch(`${API_BASE}/albums/${albumId.value}/photos/${photo.id}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ cleaning_recommendation: decision }) }); photo.cleaning_recommendation = decision } catch (e: any) { errorMessage.value = e.message }
}

async function batchUpdate(decision: string) {
  let c = 0
  for (const pid of selectedIds.value) { try { await fetch(`${API_BASE}/albums/${albumId.value}/photos/${pid}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ cleaning_recommendation: decision }) }); const p = photos.value.find(x => x.id === pid); if (p) p.cleaning_recommendation = decision; c++ } catch { } }
  selectedIds.value = new Set(); successMessage.value = `已更新 ${c} 张为「${decision === 'keep' ? '保留' : '移除'}」`; setTimeout(() => successMessage.value = '', 3000)
}

function goNext() {
  if (album.value?.status === 'draft') { errorMessage.value = '请先上传照片再进入清洗。'; return }
  router.push(`/albums/${albumId.value}/chapters`)
}
onMounted(loadData); watch(() => albumId.value, loadData)
</script>

<template>
  <WorkflowStepper v-if="albumId" :album-id="albumId" :album-status="album?.status" />
  <div class="space-y-6">
    <div v-if="album?.status === 'draft'" class="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-700 flex items-center justify-between">
      <span>请先上传照片，才能进行清洗分析。</span>
      <button class="rounded-full bg-amber-200 px-4 py-1.5 text-xs text-amber-800 hover:bg-amber-300" @click="router.push(`/albums/${albumId}/upload`)">返回上传</button>
    </div>
    <SectionCard title="照片清洗" description="系统分析每张照片的质量。标记为「移除」的照片不会进入后续流程。"
      eyebrow="步骤 2" tone="accent">
      <div v-if="loading" class="text-sm text-slate-500">加载中...</div>
      <div v-else class="grid gap-3 md:grid-cols-5">
        <div class="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3"><p class="text-xs text-slate-500">项目</p><p class="mt-1 font-semibold">{{ album?.name }}</p></div>
        <div class="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3"><p class="text-xs text-slate-500">总数</p><p class="mt-1 font-semibold">{{ photos.length }}</p></div>
        <div class="rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3"><p class="text-xs text-emerald-600">保留</p><p class="mt-1 font-semibold text-emerald-700">{{ keepPhotos.length }}</p></div>
        <div class="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3"><p class="text-xs text-rose-600">移除</p><p class="mt-1 font-semibold text-rose-700">{{ removedPhotos.length }}</p></div>
        <div class="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3"><p class="text-xs text-slate-500">未评分</p><p class="mt-1 font-semibold">{{ unscoredPhotos.length }}</p></div>
      </div>
      <div class="mt-4 flex flex-wrap items-center gap-3">
        <button class="rounded-full bg-cyan-600 px-5 py-3 text-sm text-white hover:bg-cyan-700 disabled:bg-slate-400" :disabled="!albumId || actionLoading" @click="startCleaning">{{ actionLoading ? '分析中...' : '启动清洗分析' }}</button>
        <span v-if="successMessage" class="text-sm text-emerald-600">{{ successMessage }}</span>
        <span v-if="errorMessage" class="text-sm text-rose-600">{{ errorMessage }}</span>
        <button v-if="keepPhotos.length > 0"
          class="ml-auto rounded-full border border-cyan-300 bg-cyan-50 px-6 py-3 text-sm text-cyan-700 hover:bg-cyan-100 shadow-sm"
          @click="goNext">下一步：章节聚类 &rarr;</button>
      </div>
    </SectionCard>

    <SectionCard v-if="keepPhotos.length > 0" title="保留照片" :description="`${keepPhotos.length} 张将进入后续排版流程`">
      <div class="mb-3 flex flex-wrap items-center gap-2">
        <button class="rounded-full border border-slate-300 px-3 py-1.5 text-xs hover:bg-slate-50" @click="toggleSelectAll">{{ selectedIds.size === keepPhotos.length ? '取消全选' : '全选' }}</button>
        <span class="text-xs text-slate-400">已选 {{ selectedIds.size }} 张</span>
        <button class="rounded-full bg-rose-50 px-4 py-1.5 text-xs text-rose-600 hover:bg-rose-100 disabled:opacity-30" :disabled="selectedIds.size === 0" @click="batchUpdate('remove')">批量移除</button>
      </div>
      <div class="overflow-x-auto rounded-2xl border border-slate-200">
        <table class="w-full text-left text-sm">
          <thead><tr class="border-b border-slate-200 bg-slate-50 text-xs text-slate-500"><th class="px-3 py-2 w-8"></th><th class="px-3 py-2 w-16"></th><th class="px-3 py-2">文件名</th><th class="px-3 py-2 w-16">大小</th><th class="px-3 py-2 w-20">评分</th><th class="px-3 py-2 w-16"></th></tr></thead>
          <tbody>
            <tr v-for="photo in keepPhotos" :key="photo.id" class="border-b border-slate-100 hover:bg-slate-50/50 last:border-b-0" :class="{ 'bg-cyan-50/30': selectedIds.has(photo.id) }">
              <td class="px-3 py-2"><input type="checkbox" :checked="selectedIds.has(photo.id)" @change="toggleSelect(photo.id)" class="h-4 w-4 rounded border-slate-300 text-cyan-600" /></td>
              <td class="px-3 py-2"><img :src="photo.url" :alt="photo.filename" class="h-10 w-10 rounded-lg object-cover" /></td>
              <td class="px-3 py-2 font-medium text-slate-800 truncate max-w-[200px]">{{ photo.filename }}</td>
              <td class="px-3 py-2 text-xs text-slate-500">{{ formatFileSize(photo.size) }}</td>
              <td class="px-3 py-2"><span class="font-semibold" :class="(photo.quality_score ?? 0) >= 5 ? 'text-emerald-600' : 'text-amber-600'">{{ photo.quality_score?.toFixed(1) ?? '-' }}</span></td>
              <td class="px-3 py-2"><button class="rounded-full px-2 py-1 text-xs text-rose-600 hover:bg-rose-50" @click="updateDecision(photo, 'remove')">移除</button></td>
            </tr>
          </tbody>
        </table>
      </div>
    </SectionCard>

    <SectionCard v-if="removedPhotos.length > 0" title="已移除照片" :description="`${removedPhotos.length} 张，不会进入后续流程`">
      <button class="mb-3 text-xs text-slate-500 underline hover:text-slate-700" @click="showRemoved = !showRemoved">{{ showRemoved ? '收起' : '展开' }}</button>
      <div v-if="showRemoved" class="grid gap-2 sm:grid-cols-4 lg:grid-cols-6">
        <div v-for="photo in removedPhotos" :key="photo.id" class="rounded-xl border border-rose-200 bg-rose-50/30 overflow-hidden opacity-60 hover:opacity-100 transition">
          <img :src="photo.url" :alt="photo.filename" class="h-16 w-full object-cover grayscale" />
          <div class="px-2 py-1.5 flex items-center justify-between"><span class="truncate text-[10px] text-slate-500">{{ photo.filename }}</span><button class="rounded-full bg-emerald-50 px-2 py-0.5 text-[10px] text-emerald-600 hover:bg-emerald-100" @click="updateDecision(photo, 'keep')">恢复</button></div>
        </div>
      </div>
    </SectionCard>

    <div v-if="!loading && photos.length === 0 && albumId" class="rounded-2xl border border-dashed border-slate-300 px-4 py-10 text-center">
      <p class="text-slate-500">暂无照片，请先返回上传。</p>
      <button class="mt-3 rounded-full bg-slate-100 px-4 py-2 text-sm text-slate-600 hover:bg-slate-200" @click="router.push(`/albums/${albumId}/upload`)">&larr; 返回上传</button>
    </div>
  </div>
</template>

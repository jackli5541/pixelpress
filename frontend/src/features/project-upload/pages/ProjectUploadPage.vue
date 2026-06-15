<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import SectionCard from '@/shared/components/SectionCard.vue'
import WorkflowStepper from '@/shared/components/WorkflowStepper.vue'
import { httpGet, httpPost } from '@/shared/api/http'
import type { AlbumCard } from '@/shared/types/album'

interface UploadedPhotoItem {
  id: string; album_id: string; filename: string; content_type: string
  size: number; storage_key: string; url: string; uploaded_at: string
}

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000/api/v1'
const route = useRoute(); const router = useRouter()

const form = reactive({ name: '', album_type: 'yearbook', book_size: 'square_10inch', theme_style: 'minimal', cover_title: '' })
const albums = ref<AlbumCard[]>([])
const currentAlbum = ref<AlbumCard | null>(null)
const photos = ref<UploadedPhotoItem[]>([])
const loading = ref(false); const submitting = ref(false); const uploading = ref(false)
const errorMessage = ref(''); const successMessage = ref('')
const uploadProgress = ref(0); const uploadTotal = ref(0)
const fileInput = ref<HTMLInputElement | null>(null)

const currentAlbumId = computed(() => { const id = route.params.id; return typeof id === 'string' ? id : '' })

function formatFileSize(bytes: number): string { if (bytes < 1024) return `${bytes} B`; if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`; return `${(bytes / (1024 * 1024)).toFixed(1)} MB` }

async function loadAlbums() { loading.value = true; errorMessage.value = ''; try { const r = await httpGet<AlbumCard[]>('/albums'); albums.value = r.data } catch (e: any) { errorMessage.value = e.message } finally { loading.value = false } }
async function loadCurrentAlbum() { if (!currentAlbumId.value) { currentAlbum.value = null; return }; try { const r = await httpGet<AlbumCard>(`/albums/${currentAlbumId.value}`); currentAlbum.value = r.data } catch { currentAlbum.value = null } }
async function loadPhotos() { if (!currentAlbumId.value) return; try { const r = await httpGet<{ items: UploadedPhotoItem[] }>(`/albums/${currentAlbumId.value}/photos`); photos.value = r.data.items } catch { photos.value = [] } }

async function submitAlbum() {
  if (!form.name.trim()) { errorMessage.value = '请填写项目名称'; return }
  submitting.value = true; errorMessage.value = ''
  try { const r = await httpPost<AlbumCard>('/albums', { ...form, cover_title: form.cover_title || null }); await loadAlbums(); await router.push(`/albums/${r.data.id}/upload`) } catch (e: any) { errorMessage.value = e.message } finally { submitting.value = false }
}

function triggerFileSelect() { fileInput.value?.click() }

async function handleFilesSelected(event: Event) {
  const input = event.target as HTMLInputElement; const files = input.files; if (!files || !files.length) return
  if (!currentAlbumId.value) { errorMessage.value = '请先选择项目'; input.value = ''; return }
  uploading.value = true; errorMessage.value = ''; uploadTotal.value = files.length; uploadProgress.value = 0
  const fd = new FormData(); for (let i = 0; i < files.length; i++) fd.append('files', files[i])
  try {
    const res = await fetch(`${API_BASE}/albums/${currentAlbumId.value}/photos/upload`, { method: 'POST', body: fd })
    if (!res.ok) throw new Error(`上传失败 (${res.status})`)
    const result = await res.json(); uploadProgress.value = uploadTotal.value
    if (result.data?.rejected?.length) errorMessage.value = '部分文件被拒绝: ' + result.data.rejected.map((r: any) => r.filename).join(', ')
    await loadPhotos(); await loadCurrentAlbum()
    successMessage.value = `成功上传 ${result.data?.uploaded?.length || 0} 张照片`; setTimeout(() => successMessage.value = '', 3000)
  } catch (e: any) { errorMessage.value = e.message } finally { uploading.value = false; input.value = '' }
}

function goToCleaning() { if (currentAlbumId.value) router.push(`/albums/${currentAlbumId.value}/cleaning`) }

onMounted(async () => { await loadAlbums(); await loadCurrentAlbum(); if (currentAlbumId.value) await loadPhotos() })
watch(() => currentAlbumId.value, async () => { await loadAlbums(); await loadCurrentAlbum(); photos.value = []; if (currentAlbumId.value) await loadPhotos() })
</script>

<template>
  <WorkflowStepper v-if="currentAlbumId" :album-id="currentAlbumId" />

  <div class="space-y-6">
    <SectionCard title="上传照片" :description="currentAlbum ? `正在向「${currentAlbum.name}」添加照片` : '请先选择或创建项目'"
      eyebrow="步骤 1" tone="accent">
      <input ref="fileInput" type="file" accept="image/*" multiple class="hidden" @change="handleFilesSelected" />

      <div v-if="currentAlbum" class="grid gap-3 md:grid-cols-4 mb-4">
        <div class="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3"><p class="text-xs text-slate-500">项目</p><p class="mt-1 font-semibold text-slate-900">{{ currentAlbum.name }}</p></div>
        <div class="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3"><p class="text-xs text-slate-500">规格</p><p class="mt-1 font-semibold text-slate-900">{{ currentAlbum.book_size }}</p></div>
        <div class="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3"><p class="text-xs text-slate-500">照片数</p><p class="mt-1 font-semibold text-slate-900">{{ photos.length }} 张</p></div>
        <div class="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3"><p class="text-xs text-slate-500">状态</p><p class="mt-1 font-semibold text-slate-900">{{ currentAlbum.status }}</p></div>
      </div>

      <div class="flex flex-wrap items-center gap-3">
        <button class="rounded-full bg-cyan-600 px-6 py-3 text-sm text-white hover:bg-cyan-700 disabled:bg-slate-400"
          :disabled="!currentAlbumId || uploading" @click="triggerFileSelect">
          {{ uploading ? '上传中...' : '选择照片上传' }}
        </button>
        <span v-if="successMessage" class="text-sm text-emerald-600">{{ successMessage }}</span>
        <span v-if="errorMessage" class="text-sm text-rose-600">{{ errorMessage }}</span>
        <button v-if="currentAlbumId && photos.length > 0"
          class="ml-auto rounded-full border border-cyan-300 bg-cyan-50 px-6 py-3 text-sm text-cyan-700 hover:bg-cyan-100 shadow-sm"
          @click="goToCleaning">下一步：照片清洗 &rarr;</button>
      </div>

      <div v-if="uploading" class="mt-4">
        <div class="h-2 w-full rounded-full bg-slate-200"><div class="h-2 rounded-full bg-cyan-600 transition-all duration-300" :style="{ width: uploadTotal ? `${(uploadProgress / uploadTotal) * 100}%` : '0%' }" /></div>
        <p class="mt-1 text-xs text-slate-500">{{ uploadProgress }} / {{ uploadTotal }}</p>
      </div>
    </SectionCard>

    <SectionCard v-if="photos.length > 0" title="已上传照片" :description="`共 ${photos.length} 张`">
      <div class="grid gap-3 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
        <div v-for="photo in photos" :key="photo.id" class="group rounded-xl border border-slate-200 bg-white overflow-hidden shadow-sm hover:shadow-md transition">
          <div class="aspect-square bg-slate-100"><img :src="photo.url" :alt="photo.filename" class="h-full w-full object-cover" loading="lazy" /></div>
          <div class="px-2 py-2"><p class="truncate text-xs font-medium text-slate-700">{{ photo.filename }}</p><p class="text-[10px] text-slate-400">{{ formatFileSize(photo.size) }}</p></div>
        </div>
      </div>
    </SectionCard>

    <SectionCard title="项目列表" description="选择已有项目或创建新项目">
      <div class="grid gap-4 lg:grid-cols-2">
        <div class="rounded-2xl border border-slate-200 p-4">
          <p class="text-sm font-semibold text-slate-900 mb-3">创建新项目</p>
          <div class="space-y-3">
            <input v-model="form.name" type="text" placeholder="项目名称，如：2025 年度相册" class="w-full rounded-xl border border-slate-200 px-4 py-2.5 text-sm outline-none focus:border-cyan-400" />
            <button class="w-full rounded-xl bg-cyan-600 px-4 py-2.5 text-sm text-white hover:bg-cyan-700 disabled:bg-slate-400" :disabled="submitting" @click="submitAlbum">{{ submitting ? '创建中...' : '创建并开始' }}</button>
          </div>
        </div>
        <div>
          <div v-if="loading" class="text-sm text-slate-500 py-4">加载中...</div>
          <div v-else-if="albums.length === 0" class="rounded-xl border border-dashed border-slate-300 py-8 text-center text-sm text-slate-400">暂无项目</div>
          <div v-else class="space-y-2 max-h-[320px] overflow-auto">
            <button v-for="album in albums" :key="album.id" class="flex w-full items-center justify-between rounded-xl border border-slate-200 px-4 py-3 text-left hover:border-cyan-300 hover:bg-cyan-50/50 transition" @click="router.push(`/albums/${album.id}/upload`)">
              <div><p class="text-sm font-medium text-slate-900">{{ album.name }}</p><p class="text-xs text-slate-500 mt-0.5">{{ album.photo_count }} 张照片 · {{ album.status }}</p></div>
              <span class="text-xs text-cyan-600">进入 &rarr;</span>
            </button>
          </div>
        </div>
      </div>
    </SectionCard>
  </div>
</template>

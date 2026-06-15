<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import SectionCard from '@/shared/components/SectionCard.vue'
import WorkflowStepper from '@/shared/components/WorkflowStepper.vue'
import { httpGet, httpPost } from '@/shared/api/http'

interface PhotoItem { id: string; filename: string; size: number; url: string }
interface PageItem { id: string; page_number: number; template: string; photo_ids: string[]; photo_count: number; html: string; status: string }
interface PreviewData { album_id: string; html: string }

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000/api/v1'
const route = useRoute(); const router = useRouter()
const pages = ref<PageItem[]>([]); const allPhotos = ref<PhotoItem[]>([])
const albumStatus = ref<string>('draft')
const loading = ref(false); const actionLoading = ref(false)
const errorMessage = ref(''); const successMessage = ref('')
const previewHtml = ref(''); const showPreview = ref(false)

const albumId = computed(() => { const id = route.params.id; return typeof id === 'string' ? id : '' })
const needChapters = computed(() => {
  const idx = ['draft','uploaded','cleaned','clustered','planned','rendered','exported'].indexOf(albumStatus.value)
  return idx < 3 // status < "clustered"
})
const templateLabels: Record<string, string> = { full_page: '全页', half_half: '对半', two_column: '双栏', grid_3: '三图', grid_4: '四图', one_large_two_small: '一大两小' }

function getPhotos(idList: string[]): PhotoItem[] { const ids = new Set(idList); return allPhotos.value.filter(p => ids.has(p.id)) }
function getOrphans(): PhotoItem[] { const assigned = new Set<string>(); pages.value.forEach(p => (p.photo_ids || []).forEach(id => assigned.add(id))); return allPhotos.value.filter(p => !assigned.has(p.id)) }

async function loadData() {
  if (!albumId.value) return; loading.value = true; errorMessage.value = ''
  try {
    const [pgRes, phRes, albRes] = await Promise.all([
      httpGet<PageItem[]>(`/albums/${albumId.value}/pages`),
      httpGet<{ items: PhotoItem[] }>(`/albums/${albumId.value}/photos?recommendation=keep`),
      httpGet<any>(`/albums/${albumId.value}`),
    ])
    pages.value = (pgRes.data || []).sort((a, b) => (a.page_number || 0) - (b.page_number || 0)); allPhotos.value = phRes.data.items || []
    albumStatus.value = albRes.data?.status || 'draft'
  } catch (e: any) { errorMessage.value = e.message } finally { loading.value = false }
}

function goBack() { router.push(`/albums/${albumId.value}/chapters`) }

async function startPlan() { if (!albumId.value) return; actionLoading.value = true; try { await httpPost(`/albums/${albumId.value}/plan`); await loadData(); successMessage.value = '规划完成' } catch (e: any) { errorMessage.value = e.message } finally { actionLoading.value = false; setTimeout(() => successMessage.value = '', 3000) } }
async function startRender() { if (!albumId.value) return; actionLoading.value = true; try { await httpPost(`/albums/${albumId.value}/render`); await loadData(); successMessage.value = '渲染完成' } catch (e: any) { errorMessage.value = e.message } finally { actionLoading.value = false; setTimeout(() => successMessage.value = '', 3000) } }
async function changeTemplate(page: PageItem, tmpl: string) { try { await fetch(`${API_BASE}/albums/${albumId.value}/pages/${page.id}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ template: tmpl }) }); page.template = tmpl } catch (e: any) { errorMessage.value = e.message } }
async function movePhoto(photoId: string, targetPageId: string) { try { await fetch(`${API_BASE}/albums/${albumId.value}/pages/move-photos`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ photo_ids: [photoId], target_page_id: targetPageId }) }); await loadData() } catch (e: any) { errorMessage.value = e.message } }
async function createPage() { try { await fetch(`${API_BASE}/albums/${albumId.value}/pages`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ template: 'grid_3', photo_ids: [] }) }); await loadData() } catch (e: any) { errorMessage.value = e.message } }
async function deletePage(id: string) { if (!confirm('删除此页面？照片将变为未分配。')) return; try { await fetch(`${API_BASE}/albums/${albumId.value}/pages/${id}`, { method: 'DELETE' }); await loadData() } catch (e: any) { errorMessage.value = e.message } }
async function loadPreview() { if (!albumId.value) return; try { const r = await httpGet<PreviewData>(`/albums/${albumId.value}/preview`); previewHtml.value = r.data.html; showPreview.value = true } catch (e: any) { errorMessage.value = '请先执行渲染' } }
function goNext() { router.push(`/albums/${albumId.value}/export`) }
onMounted(loadData); watch(() => albumId.value, loadData)
</script>

<template>
  <WorkflowStepper v-if="albumId" :album-id="albumId" :album-status="albumStatus" />
  <div class="space-y-6">
    <div v-if="!loading && needChapters" class="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-700 flex items-center justify-between">
      <span>请先完成章节聚类，再进入页面排版。</span>
      <button class="rounded-full bg-amber-200 px-4 py-1.5 text-xs text-amber-800 hover:bg-amber-300" @click="goBack">返回章节</button>
    </div>
    <SectionCard title="页面排版" description="规划每页照片分布，选择版式模板，渲染 HTML 预览。"
      eyebrow="步骤 4" tone="accent">
      <div class="flex flex-wrap items-center gap-3">
        <button class="rounded-full bg-cyan-600 px-5 py-3 text-sm text-white hover:bg-cyan-700 disabled:bg-slate-400" :disabled="!albumId || actionLoading" @click="startPlan">自动规划</button>
        <button class="rounded-full border border-slate-300 bg-white px-5 py-3 text-sm text-slate-700 hover:border-slate-400 disabled:text-slate-400" :disabled="!albumId || actionLoading" @click="startRender">排版渲染</button>
        <button class="rounded-full border border-cyan-300 bg-cyan-50 px-5 py-3 text-sm text-cyan-700 hover:bg-cyan-100 disabled:opacity-30" :disabled="!albumId || !pages.length" @click="loadPreview">预览全册</button>
        <button class="rounded-full border border-slate-200 bg-white px-4 py-3 text-sm text-slate-600 hover:bg-slate-50" @click="createPage">+ 空白页</button>
        <span v-if="successMessage" class="text-sm text-emerald-600">{{ successMessage }}</span>
        <span v-if="errorMessage" class="text-sm text-rose-600">{{ errorMessage }}</span>
        <button v-if="pages.length > 0"
          class="ml-auto rounded-full border border-cyan-300 bg-cyan-50 px-6 py-3 text-sm text-cyan-700 hover:bg-cyan-100 shadow-sm"
          @click="goNext">下一步：导出 &rarr;</button>
      </div>
      <p class="mt-2 text-xs text-slate-400">{{ allPhotos.length }} 张保留照片，{{ pages.length }} 页，{{ getOrphans().length }} 张未分配</p>
    </SectionCard>

    <div v-if="pages.length > 0" class="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
      <div v-for="page in pages" :key="page.id" class="rounded-2xl border border-slate-200 bg-white overflow-hidden shadow-sm">
        <div class="flex items-center justify-between bg-slate-50 px-4 py-3">
          <div><p class="text-sm font-semibold text-slate-900">第 {{ page.page_number }} 页</p><p class="text-xs text-slate-500">{{ getPhotos(page.photo_ids || []).length }} 张 · {{ templateLabels[page.template] || page.template }}</p></div>
          <div class="flex gap-1">
            <select :value="page.template" @change="changeTemplate(page, ($event.target as HTMLSelectElement).value)" class="rounded-full border border-slate-200 bg-white px-2 py-1 text-xs text-slate-600 outline-none"><option v-for="(label, key) in templateLabels" :key="key" :value="key">{{ label }}</option></select>
            <button class="rounded-full bg-rose-50 px-2 py-1 text-xs text-rose-600 hover:bg-rose-100" @click="deletePage(page.id)">删</button>
          </div>
        </div>
        <div v-if="page.html" class="border-b border-slate-100" style="max-height:140px;overflow:hidden" v-html="page.html" />
        <div class="px-3 py-2">
          <div v-if="getPhotos(page.photo_ids || []).length === 0" class="py-4 text-center text-xs text-slate-400">从下方拖入照片</div>
          <div v-else class="flex flex-wrap gap-1.5">
            <div v-for="photo in getPhotos(page.photo_ids || [])" :key="photo.id" class="group relative">
              <img :src="photo.url" :alt="photo.filename" class="h-12 w-12 rounded-lg object-cover border border-slate-100" />
              <select class="absolute top-0 right-0 rounded border border-slate-300 bg-white text-[10px] opacity-0 group-hover:opacity-100" @change="(e: Event) => movePhoto(photo.id, (e.target as HTMLSelectElement).value)"><option value="">移</option><option v-for="pg in pages.filter(p => p.id !== page.id)" :key="pg.id" :value="pg.id">第{{ pg.page_number }}页</option></select>
            </div>
          </div>
        </div>
      </div>
    </div>

    <SectionCard v-if="getOrphans().length > 0" title="未分配照片" :description="`${getOrphans().length} 张`">
      <div class="flex flex-wrap gap-2">
        <div v-for="photo in getOrphans()" :key="photo.id" class="rounded-xl border border-dashed border-slate-300 bg-slate-50 overflow-hidden">
          <img :src="photo.url" :alt="photo.filename" class="h-14 w-14 object-cover" />
          <select v-if="pages.length > 0" class="w-full border-t border-slate-200 text-[10px] px-1 py-0.5" @change="(e: Event) => movePhoto(photo.id, (e.target as HTMLSelectElement).value)"><option value="">分配到...</option><option v-for="pg in pages" :key="pg.id" :value="pg.id">第{{ pg.page_number }}页</option></select>
        </div>
      </div>
    </SectionCard>

    <div v-if="!loading && !pages.length && albumId" class="rounded-2xl border border-dashed border-slate-300 px-4 py-10 text-center"><p class="text-slate-500">暂无页面，请先「自动规划」或「添加空白页」。</p></div>

    <div v-if="showPreview" class="fixed inset-0 z-50 flex items-start justify-center overflow-auto bg-black/60 p-4" @click.self="showPreview = false">
      <div class="my-8 w-full max-w-4xl rounded-2xl bg-white shadow-2xl">
        <div class="flex items-center justify-between border-b px-6 py-4"><p class="text-lg font-semibold text-slate-900">全册预览</p><button class="rounded-full bg-slate-100 px-4 py-2 text-sm hover:bg-slate-200" @click="showPreview = false">关闭</button></div>
        <div class="p-4" v-html="previewHtml" />
      </div>
    </div>
  </div>
</template>

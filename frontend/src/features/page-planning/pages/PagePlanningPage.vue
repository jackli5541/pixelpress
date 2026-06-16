<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import SectionCard from '@/shared/components/SectionCard.vue'
import WorkflowStepper from '@/shared/components/WorkflowStepper.vue'
import { httpGet, httpPost } from '@/shared/api/http'
import { usePhotoDrag } from '@/shared/composables/usePhotoDrag'

interface PhotoItem { id: string; filename: string; size: number; url: string }
interface PageItem { id: string; page_number: number; template: string; photo_ids: string[]; photo_count: number; chapter_id: string | null; html: string; status: string }
interface ChapterItem { id: string; name: string; description: string; photo_ids: string[] }
interface PreviewData { album_id: string; html: string }

const ORPHAN_ID = '__orphan__'
const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000/api/v1'
const route = useRoute(); const router = useRouter()
const pages = ref<PageItem[]>([]); const allPhotos = ref<PhotoItem[]>([])
const chapters = ref<ChapterItem[]>([])
const albumStatus = ref<string>('draft')
const loading = ref(false); const actionLoading = ref(false)
const errorMessage = ref(''); const successMessage = ref('')
const previewHtml = ref(''); const showPreview = ref(false)
const expandedChapter = ref<string | null>(null)

const albumId = computed(() => { const id = route.params.id; return typeof id === 'string' ? id : '' })
const needChapters = computed(() => {
  const idx = ['draft','uploaded','cleaned','clustered','planned','rendered','exported'].indexOf(albumStatus.value)
  return idx < 3 // status < "clustered"
})
const templateLabels: Record<string, string> = { full_page: '全页', half_half: '对半', two_column: '双栏', grid_3: '三图', grid_4: '四图', one_large_two_small: '一大两小' }

// ── 按章节分组页面 ──
interface ChapterPageGroup {
  chapter: ChapterItem
  pages: PageItem[]
  photos: PhotoItem[]
  unassignedPhotos: PhotoItem[]
}

const chapterGroups = computed((): ChapterPageGroup[] => {
  return chapters.value.map(ch => {
    const chPages = pages.value.filter(p => p.chapter_id === ch.id).sort((a, b) => (a.page_number || 0) - (b.page_number || 0))
    const pagePhotoIds = new Set<string>()
    chPages.forEach(p => (p.photo_ids || []).forEach(pid => pagePhotoIds.add(pid)))
    const chPhotos = getPhotos(ch.photo_ids || [])
    const unassigned = chPhotos.filter(p => !pagePhotoIds.has(p.id))
    return { chapter: ch, pages: chPages, photos: chPhotos, unassignedPhotos: unassigned }
  })
})

// 无章节的孤立页面（chapter_id 为 null）
const orphanPages = computed(() => pages.value.filter(p => !p.chapter_id).sort((a, b) => (a.page_number || 0) - (b.page_number || 0)))

// 所有已分配到页面的照片 ID
const allPagePhotoIds = computed(() => {
  const ids = new Set<string>()
  pages.value.forEach(p => (p.photo_ids || []).forEach(pid => ids.add(pid)))
  return ids
})

// 不属于任何章节的完全孤立照片
const totalUnassignedPhotos = computed(() => allPhotos.value.filter(p => !allPagePhotoIds.value.has(p.id)))

function getPhotos(idList: string[]): PhotoItem[] { const ids = new Set(idList); return allPhotos.value.filter(p => ids.has(p.id)) }

async function loadData() {
  if (!albumId.value) return; loading.value = true; errorMessage.value = ''
  try {
    const [pgRes, phRes, albRes, chRes] = await Promise.all([
      httpGet<PageItem[]>(`/albums/${albumId.value}/pages`),
      httpGet<{ items: PhotoItem[] }>(`/albums/${albumId.value}/photos?recommendation=keep`),
      httpGet<any>(`/albums/${albumId.value}`),
      httpGet<ChapterItem[]>(`/albums/${albumId.value}/chapters`),
    ])
    pages.value = (pgRes.data || []).sort((a, b) => (a.page_number || 0) - (b.page_number || 0))
    allPhotos.value = phRes.data.items || []
    chapters.value = chRes.data || []
    albumStatus.value = albRes.data?.status || 'draft'
  } catch (e: any) { errorMessage.value = e.message } finally { loading.value = false }
}

function goBack() { router.push(`/albums/${albumId.value}/chapters`) }

async function startPlan() { if (!albumId.value) return; actionLoading.value = true; try { await httpPost(`/albums/${albumId.value}/plan`); await loadData(); successMessage.value = '规划完成' } catch (e: any) { errorMessage.value = e.message } finally { actionLoading.value = false; setTimeout(() => successMessage.value = '', 3000) } }
async function startRender() { if (!albumId.value) return; actionLoading.value = true; try { await httpPost(`/albums/${albumId.value}/render`); await loadData(); successMessage.value = '渲染完成' } catch (e: any) { errorMessage.value = e.message } finally { actionLoading.value = false; setTimeout(() => successMessage.value = '', 3000) } }
async function changeTemplate(page: PageItem, tmpl: string) { try { await fetch(`${API_BASE}/albums/${albumId.value}/pages/${page.id}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ template: tmpl }) }); page.template = tmpl } catch (e: any) { errorMessage.value = e.message } }

async function movePhoto(photoId: string, targetPageId: string) {
  if (targetPageId === ORPHAN_ID) {
    errorMessage.value = '移回未分配区域暂不支持，请删除对应页面来释放照片。'
    return
  }
  try {
    await fetch(`${API_BASE}/albums/${albumId.value}/pages/move-photos`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ photo_ids: [photoId], target_page_id: targetPageId })
    })
    await loadData()
  } catch (e: any) { errorMessage.value = e.message }
}

async function createPage(chapterId: string | null = null) {
  try {
    await fetch(`${API_BASE}/albums/${albumId.value}/pages`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ template: 'grid_3', photo_ids: [], chapter_id: chapterId })
    })
    await loadData()
  } catch (e: any) { errorMessage.value = e.message }
}

async function deletePage(id: string) { if (!confirm('删除此页面？照片将变为未分配。')) return; try { await fetch(`${API_BASE}/albums/${albumId.value}/pages/${id}`, { method: 'DELETE' }); await loadData() } catch (e: any) { errorMessage.value = e.message } }
async function loadPreview() { if (!albumId.value) return; try { const r = await httpGet<PreviewData>(`/albums/${albumId.value}/preview`); previewHtml.value = r.data.html; showPreview.value = true } catch (e: any) { errorMessage.value = '请先执行渲染' } }
function goNext() { router.push(`/albums/${albumId.value}/export`) }

const { isDragging, onDragStart, onDragOver, onDragLeave, onDrop, onDragEnd, getDragPhotoClass, getDropTargetClass } = usePhotoDrag({
  onPhotoMove: movePhoto,
  orphanAreaId: ORPHAN_ID,
})

onMounted(loadData); watch(() => albumId.value, loadData)
</script>

<template>
  <WorkflowStepper v-if="albumId" :album-id="albumId" :album-status="albumStatus" />
  <div class="space-y-6">
    <div v-if="!loading && needChapters" class="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-700 flex items-center justify-between">
      <span>请先完成章节聚类，再进入页面排版。</span>
      <button class="rounded-full bg-amber-200 px-4 py-1.5 text-xs text-amber-800 hover:bg-amber-300" @click="goBack">返回章节</button>
    </div>

    <!-- ── 顶部操作区 ── -->
    <SectionCard title="页面排版" description="每个章节独立规划页面。点击章节展开查看，拖拽照片分配到页面。"
      eyebrow="步骤 4" tone="accent">
      <div class="flex flex-wrap items-center gap-3">
        <button class="rounded-full bg-cyan-600 px-5 py-3 text-sm text-white hover:bg-cyan-700 disabled:bg-slate-400" :disabled="!albumId || actionLoading" @click="startPlan">自动规划</button>
        <button class="rounded-full border border-slate-300 bg-white px-5 py-3 text-sm text-slate-700 hover:border-slate-400 disabled:text-slate-400" :disabled="!albumId || actionLoading" @click="startRender">排版渲染</button>
        <button class="rounded-full border border-cyan-300 bg-cyan-50 px-5 py-3 text-sm text-cyan-700 hover:bg-cyan-100 disabled:opacity-30" :disabled="!albumId || !pages.length" @click="loadPreview">预览全册</button>
        <span v-if="successMessage" class="text-sm text-emerald-600">{{ successMessage }}</span>
        <span v-if="errorMessage" class="text-sm text-rose-600">{{ errorMessage }}</span>
        <button v-if="pages.length > 0"
          class="ml-auto rounded-full border border-cyan-300 bg-cyan-50 px-6 py-3 text-sm text-cyan-700 hover:bg-cyan-100 shadow-sm"
          @click="goNext">下一步：导出 &rarr;</button>
      </div>
      <p class="mt-2 text-xs text-slate-400">{{ allPhotos.length }} 张保留照片，{{ chapters.length }} 个章节，{{ pages.length }} 页，{{ totalUnassignedPhotos.length }} 张未分配</p>
      <p v-if="isDragging" class="mt-1 text-xs text-cyan-600 animate-pulse">拖拽照片到目标页面即可移动</p>
    </SectionCard>

    <!-- ── 按章节分组展示页面 ── -->
    <div v-if="chapterGroups.length > 0" class="space-y-4">
      <div v-for="group in chapterGroups" :key="group.chapter.id"
        class="rounded-2xl border border-slate-200 bg-white overflow-hidden shadow-sm"
        :class="getDropTargetClass(group.chapter.id)"
        @dragover.prevent="(e: DragEvent) => onDragOver(e, group.chapter.id)"
        @dragleave="() => onDragLeave(group.chapter.id)"
        @drop="(e: DragEvent) => onDrop(e, group.chapter.id)">

        <!-- 章节标题栏 -->
        <div class="flex items-center justify-between px-4 py-3 bg-slate-50 cursor-pointer"
          @click="expandedChapter = expandedChapter === group.chapter.id ? null : group.chapter.id">
          <div class="flex items-center gap-3">
            <span class="text-xs text-slate-400">{{ expandedChapter === group.chapter.id ? '▾' : '▸' }}</span>
            <div>
              <p class="text-base font-semibold text-slate-900">{{ group.chapter.name }}</p>
              <p class="text-xs text-slate-500">{{ group.chapter.description || '' }} · {{ group.photos.length }} 张照片 · {{ group.pages.length }} 页 · {{ group.unassignedPhotos.length }} 张未分配</p>
            </div>
          </div>
          <div class="flex gap-2" @click.stop>
            <button class="rounded-full bg-slate-100 px-3 py-1 text-xs text-slate-600 hover:bg-slate-200" @click="createPage(group.chapter.id)">+ 添加页面</button>
          </div>
        </div>

        <!-- 章节内容（可折叠） -->
        <div v-if="expandedChapter === group.chapter.id" class="border-t border-slate-100">
          <!-- 页面卡片 -->
          <div v-if="group.pages.length > 0" class="grid gap-4 p-4 md:grid-cols-2 xl:grid-cols-3">
            <div v-for="page in group.pages" :key="page.id"
              class="rounded-xl border border-slate-200 bg-white overflow-hidden shadow-sm"
              :class="getDropTargetClass(page.id)"
              @dragover.prevent="(e: DragEvent) => onDragOver(e, page.id)"
              @dragleave="() => onDragLeave(page.id)"
              @drop="(e: DragEvent) => onDrop(e, page.id)">
              <!-- 页面头部 -->
              <div class="flex items-center justify-between bg-slate-50 px-3 py-2">
                <div><p class="text-xs font-semibold text-slate-900">第 {{ page.page_number }} 页</p><p class="text-[10px] text-slate-500">{{ getPhotos(page.photo_ids || []).length }} 张 · {{ templateLabels[page.template] || page.template }}</p></div>
                <div class="flex gap-1">
                  <select :value="page.template" @change="changeTemplate(page, ($event.target as HTMLSelectElement).value)" class="rounded-full border border-slate-200 bg-white px-2 py-1 text-[10px] text-slate-600 outline-none"><option v-for="(label, key) in templateLabels" :key="key" :value="key">{{ label }}</option></select>
                  <button class="rounded-full bg-rose-50 px-2 py-1 text-[10px] text-rose-600 hover:bg-rose-100" @click="deletePage(page.id)">删</button>
                </div>
              </div>
              <!-- 页面预览缩略图 -->
              <div v-if="page.html" class="border-b border-slate-100" style="max-height:100px;overflow:hidden" v-html="page.html" />
              <!-- 照片缩略图 -->
              <div class="px-2 py-2">
                <div v-if="getPhotos(page.photo_ids || []).length === 0" class="py-4 text-center text-xs text-slate-400">拖入照片到此页面</div>
                <div v-else class="flex flex-wrap gap-1">
                  <div v-for="photo in getPhotos(page.photo_ids || [])" :key="photo.id"
                    class="select-none"
                    :class="getDragPhotoClass(photo.id)"
                    draggable="true"
                    @dragstart="(e: DragEvent) => onDragStart(e, photo.id, page.id)"
                    @dragend="onDragEnd">
                    <img :src="photo.url" :alt="photo.filename" class="h-10 w-10 rounded-lg object-cover border border-slate-100 pointer-events-none" />
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div v-if="group.pages.length === 0" class="px-4 py-6 text-center text-sm text-slate-400">
            该章节暂无页面，点击「+ 添加页面」或运行「自动规划」
          </div>

          <!-- 章节内未分配照片 -->
          <div v-if="group.unassignedPhotos.length > 0" class="border-t border-slate-100 px-4 py-3 bg-amber-50/50">
            <p class="text-xs font-medium text-amber-700 mb-2">未分配到页面的照片（{{ group.unassignedPhotos.length }} 张）</p>
            <div class="flex flex-wrap gap-1.5">
              <div v-for="photo in group.unassignedPhotos" :key="photo.id"
                class="select-none"
                :class="getDragPhotoClass(photo.id)"
                draggable="true"
                @dragstart="(e: DragEvent) => onDragStart(e, photo.id, group.chapter.id)"
                @dragend="onDragEnd">
                <img :src="photo.url" :alt="photo.filename" class="h-10 w-10 rounded-lg object-cover border border-dashed border-amber-300 pointer-events-none" />
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- ── 无章节的孤立页面 ── -->
    <div v-if="orphanPages.length > 0" class="space-y-2">
      <p class="text-xs font-medium text-slate-500">未归属章节的页面</p>
      <div class="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        <div v-for="page in orphanPages" :key="page.id" class="rounded-xl border border-dashed border-slate-300 bg-white overflow-hidden shadow-sm">
          <div class="flex items-center justify-between bg-slate-50 px-3 py-2">
            <div><p class="text-xs font-semibold text-slate-900">第 {{ page.page_number }} 页</p><p class="text-[10px] text-slate-500">{{ getPhotos(page.photo_ids || []).length }} 张 · {{ templateLabels[page.template] || page.template }}</p></div>
            <button class="rounded-full bg-rose-50 px-2 py-1 text-[10px] text-rose-600 hover:bg-rose-100" @click="deletePage(page.id)">删</button>
          </div>
        </div>
      </div>
    </div>

    <!-- ── 完全未分配的照片（不属于任何页面） ── -->
    <SectionCard v-if="totalUnassignedPhotos.length > 0 && pages.length > 0" title="未分配照片" :description="`${totalUnassignedPhotos.length} 张未归属任何页面`">
      <div class="flex flex-wrap gap-2"
        :class="getDropTargetClass(ORPHAN_ID)"
        @dragover.prevent="(e: DragEvent) => onDragOver(e, ORPHAN_ID)"
        @dragleave="() => onDragLeave(ORPHAN_ID)"
        @drop="(e: DragEvent) => onDrop(e, ORPHAN_ID)">
        <div v-for="photo in totalUnassignedPhotos" :key="photo.id"
          class="rounded-xl border border-dashed border-slate-300 bg-slate-50 overflow-hidden select-none"
          :class="getDragPhotoClass(photo.id)"
          draggable="true"
          @dragstart="(e: DragEvent) => onDragStart(e, photo.id, ORPHAN_ID)"
          @dragend="onDragEnd">
          <img :src="photo.url" :alt="photo.filename" class="h-14 w-14 object-cover pointer-events-none" />
        </div>
      </div>
    </SectionCard>

    <div v-if="!loading && !pages.length && albumId" class="rounded-2xl border border-dashed border-slate-300 px-4 py-10 text-center">
      <p class="text-slate-500">暂无页面，请先「自动规划」或按章节「添加页面」。</p>
      <p class="mt-1 text-xs text-slate-400">规划将为每个章节独立分页</p>
    </div>

    <!-- ── 全册预览弹窗 ── -->
    <div v-if="showPreview" class="fixed inset-0 z-50 flex items-start justify-center overflow-auto bg-black/60 p-4" @click.self="showPreview = false">
      <div class="my-8 w-full max-w-4xl rounded-2xl bg-white shadow-2xl">
        <div class="flex items-center justify-between border-b px-6 py-4"><p class="text-lg font-semibold text-slate-900">全册预览</p><button class="rounded-full bg-slate-100 px-4 py-2 text-sm hover:bg-slate-200" @click="showPreview = false">关闭</button></div>
        <div class="p-4" v-html="previewHtml" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import SectionCard from '@/shared/components/SectionCard.vue'
import WorkflowStepper from '@/shared/components/WorkflowStepper.vue'
import { httpGet, httpPost } from '@/shared/api/http'

interface PhotoItem { id: string; filename: string; size: number; url: string }
interface ChapterItem { id: string; name: string; description: string; order: number; photo_ids: string[] }

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000/api/v1'
const route = useRoute(); const router = useRouter()
const chapters = ref<ChapterItem[]>([]); const allPhotos = ref<PhotoItem[]>([])
const albumStatus = ref<string>('draft')
const loading = ref(false); const actionLoading = ref(false)
const errorMessage = ref(''); const successMessage = ref('')
const expandedChapter = ref<string | null>(null); const editingChapter = ref<string | null>(null)
const editName = ref(''); const newChapterName = ref('')

const albumId = computed(() => { const id = route.params.id; return typeof id === 'string' ? id : '' })
const needCleaning = computed(() => albumStatus.value === 'draft' || albumStatus.value === 'uploaded')

function getPhotos(idList: string[]): PhotoItem[] { const ids = new Set(idList); return allPhotos.value.filter(p => ids.has(p.id)) }
function getOrphans(): PhotoItem[] { const assigned = new Set<string>(); chapters.value.forEach(ch => (ch.photo_ids || []).forEach(id => assigned.add(id))); return allPhotos.value.filter(p => !assigned.has(p.id)) }

async function loadData() {
  if (!albumId.value) return; loading.value = true; errorMessage.value = ''
  try {
    const [chRes, phRes, albRes] = await Promise.all([
      httpGet<ChapterItem[]>(`/albums/${albumId.value}/chapters`),
      httpGet<{ items: PhotoItem[] }>(`/albums/${albumId.value}/photos?recommendation=keep`),
      httpGet<any>(`/albums/${albumId.value}`),
    ])
    chapters.value = chRes.data || []; allPhotos.value = phRes.data.items || []
    albumStatus.value = albRes.data?.status || 'draft'
  } catch (e: any) { errorMessage.value = e.message } finally { loading.value = false }
}

function goBack() { router.push(`/albums/${albumId.value}/cleaning`) }

async function startCluster() { if (!albumId.value) return; actionLoading.value = true; try { await httpPost(`/albums/${albumId.value}/cluster`); await loadData(); successMessage.value = '聚类完成' } catch (e: any) { errorMessage.value = e.message } finally { actionLoading.value = false; setTimeout(() => successMessage.value = '', 3000) } }

async function createChapter() { if (!newChapterName.value.trim()) return; try { await fetch(`${API_BASE}/albums/${albumId.value}/chapters`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name: newChapterName.value.trim(), photo_ids: [] }) }); newChapterName.value = ''; await loadData() } catch (e: any) { errorMessage.value = e.message } }

async function renameChapter(ch: ChapterItem) { try { await fetch(`${API_BASE}/albums/${albumId.value}/chapters/${ch.id}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name: editName.value }) }); ch.name = editName.value; editingChapter.value = null } catch (e: any) { errorMessage.value = e.message } }

async function deleteChapter(id: string) { if (!confirm('删除此章节？照片将变为未分配。')) return; try { await fetch(`${API_BASE}/albums/${albumId.value}/chapters/${id}`, { method: 'DELETE' }); await loadData() } catch (e: any) { errorMessage.value = e.message } }

async function movePhoto(photoId: string, targetChapterId: string) { try { await fetch(`${API_BASE}/albums/${albumId.value}/chapters/move-photos`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ photo_ids: [photoId], target_chapter_id: targetChapterId }) }); await loadData() } catch (e: any) { errorMessage.value = e.message } }

function goNext() { router.push(`/albums/${albumId.value}/planning`) }
onMounted(loadData); watch(() => albumId.value, loadData)
</script>

<template>
  <WorkflowStepper v-if="albumId" :album-id="albumId" :album-status="albumStatus" />
  <div class="space-y-6">
    <div v-if="!loading && needCleaning" class="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-700 flex items-center justify-between">
      <span>请先完成照片清洗，再进入章节聚类。</span>
      <button class="rounded-full bg-amber-200 px-4 py-1.5 text-xs text-amber-800 hover:bg-amber-300" @click="goBack">返回清洗</button>
    </div>
    <SectionCard title="章节聚类" description="系统按时间自动分组，也可手动创建章节、移动照片。"
      eyebrow="步骤 3" tone="accent">
      <div class="flex flex-wrap items-center gap-3">
        <button class="rounded-full bg-cyan-600 px-5 py-3 text-sm text-white hover:bg-cyan-700 disabled:bg-slate-400" :disabled="!albumId || actionLoading" @click="startCluster">{{ actionLoading ? '聚类中...' : '启动自动聚类' }}</button>
        <div class="flex items-center gap-2">
          <input v-model="newChapterName" type="text" placeholder="新章节名称" class="rounded-full border border-slate-200 px-4 py-2.5 text-sm outline-none focus:border-cyan-400 w-36" @keyup.enter="createChapter" />
          <button class="rounded-full border border-cyan-300 bg-cyan-50 px-4 py-2 text-sm text-cyan-700 hover:bg-cyan-100" @click="createChapter">+ 添加</button>
        </div>
        <span v-if="successMessage" class="text-sm text-emerald-600">{{ successMessage }}</span>
        <span v-if="errorMessage" class="text-sm text-rose-600">{{ errorMessage }}</span>
        <button v-if="chapters.length > 0"
          class="ml-auto rounded-full border border-cyan-300 bg-cyan-50 px-6 py-3 text-sm text-cyan-700 hover:bg-cyan-100 shadow-sm"
          @click="goNext">下一步：页面排版 &rarr;</button>
      </div>
      <p class="mt-2 text-xs text-slate-400">{{ allPhotos.length }} 张保留照片，{{ chapters.length }} 个章节，{{ getOrphans().length }} 张未分配</p>
    </SectionCard>

    <div v-if="chapters.length > 0" class="space-y-3">
      <div v-for="chapter in chapters" :key="chapter.id" class="rounded-2xl border border-slate-200 bg-white overflow-hidden shadow-sm">
        <div class="flex items-center justify-between px-4 py-3 bg-slate-50 cursor-pointer" @click="expandedChapter = expandedChapter === chapter.id ? null : chapter.id">
          <div class="flex items-center gap-3">
            <span class="text-xs text-slate-400">{{ expandedChapter === chapter.id ? 'v' : '>' }}</span>
            <div v-if="editingChapter === chapter.id" @click.stop><input v-model="editName" class="rounded-lg border border-cyan-300 px-2 py-1 text-sm outline-none" @keyup.enter="renameChapter(chapter)" @blur="renameChapter(chapter)" autofocus /></div>
            <div v-else><p class="text-base font-semibold text-slate-900">{{ chapter.name }}</p><p class="text-xs text-slate-500">{{ chapter.description || '' }} · {{ (chapter.photo_ids || []).length }} 张</p></div>
          </div>
          <div class="flex gap-2" @click.stop>
            <button class="rounded-full bg-slate-100 px-3 py-1 text-xs text-slate-600 hover:bg-slate-200" @click="editName = chapter.name; editingChapter = chapter.id">重命名</button>
            <button class="rounded-full bg-rose-50 px-3 py-1 text-xs text-rose-600 hover:bg-rose-100" @click="deleteChapter(chapter.id)">删除</button>
          </div>
        </div>
        <div v-if="expandedChapter === chapter.id" class="border-t border-slate-100 px-4 py-3">
          <div v-if="getPhotos(chapter.photo_ids || []).length === 0" class="py-8 text-center text-sm text-slate-400">暂无照片，从下方未分配区域移动照片过来</div>
          <div v-else class="grid gap-2 sm:grid-cols-3 lg:grid-cols-4">
            <div v-for="photo in getPhotos(chapter.photo_ids || [])" :key="photo.id" class="group relative rounded-xl border border-slate-200 overflow-hidden">
              <img :src="photo.url" :alt="photo.filename" class="h-20 w-full object-cover" />
              <p class="truncate px-2 py-1 text-xs text-slate-600">{{ photo.filename }}</p>
              <select class="absolute top-1 right-1 rounded border border-slate-300 bg-white/90 text-xs opacity-0 group-hover:opacity-100 transition" @change="(e: Event) => movePhoto(photo.id, (e.target as HTMLSelectElement).value)">
                <option value="">移动到...</option>
                <option v-for="ch in chapters.filter(c => c.id !== chapter.id)" :key="ch.id" :value="ch.id">{{ ch.name }}</option>
              </select>
            </div>
          </div>
        </div>
      </div>
    </div>

    <SectionCard v-if="getOrphans().length > 0" title="未分配照片" :description="`${getOrphans().length} 张未归属任何章节`">
      <div class="grid gap-2 sm:grid-cols-4 lg:grid-cols-6">
        <div v-for="photo in getOrphans()" :key="photo.id" class="rounded-xl border border-dashed border-slate-300 bg-slate-50 overflow-hidden">
          <img :src="photo.url" :alt="photo.filename" class="h-16 w-full object-cover" />
          <div class="px-2 py-1.5"><p class="truncate text-[10px] text-slate-600">{{ photo.filename }}</p>
            <select v-if="chapters.length > 0" class="mt-1 w-full rounded border border-slate-200 text-xs" @change="(e: Event) => movePhoto(photo.id, (e.target as HTMLSelectElement).value)"><option value="">分配到...</option><option v-for="ch in chapters" :key="ch.id" :value="ch.id">{{ ch.name }}</option></select>
          </div>
        </div>
      </div>
    </SectionCard>

    <div v-if="!loading && chapters.length === 0 && albumId" class="rounded-2xl border border-dashed border-slate-300 px-4 py-10 text-center"><p class="text-slate-500">暂无章节，请点击「启动自动聚类」或手动「添加」。</p></div>
  </div>
</template>

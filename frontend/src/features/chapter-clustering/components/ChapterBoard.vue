<script setup lang="ts">
import { ref } from 'vue'
import ProtectedImage from '@/shared/components/ProtectedImage.vue'
import SectionCard from '@/shared/components/SectionCard.vue'
import { usePhotoDrag } from '@/shared/composables/usePhotoDrag'
import type { ChapterItem, ChapterSegmentItem, PhotoItem } from '@/features/chapter-clustering/types'

const ORPHAN_ID = '__orphan__'
const props = defineProps<{
  chapters: ChapterItem[]
  photos: PhotoItem[]
  orphanPhotos: PhotoItem[]
}>()
const emit = defineEmits<{
  rename: [chapter: ChapterItem, name: string]
  delete: [chapterId: string]
  move: [photoId: string, targetChapterId: string]
}>()

const expandedChapter = ref<string | null>(null)
const editingChapter = ref<string | null>(null)
const editName = ref('')

function getPhotos(ids: string[]) {
  const idSet = new Set(ids)
  return props.photos.filter((photo) => idSet.has(photo.id))
}

function getSegments(chapter: ChapterItem): ChapterSegmentItem[] {
  if (chapter.segments?.length) return chapter.segments
  return [{
    id: `${chapter.id}-fallback-segment`,
    name: '活动阶段 1',
    description: chapter.description,
    order: 1,
    segment_type: 'legacy',
    time_range: null,
    photo_ids: chapter.photo_ids || [],
  }]
}

function finishRename(chapter: ChapterItem) {
  const name = editName.value.trim()
  if (name && name !== chapter.name) emit('rename', chapter, name)
  editingChapter.value = null
}

function qualityLabel(value: number | null | undefined) {
  return typeof value === 'number' ? `聚类稳定度 ${Math.round(value * 100)}%` : '降级结果，需人工检查'
}

function coverageLabel(chapter: ChapterItem) {
  const value = chapter.clustering?.feature_coverage?.embedding
  return typeof value === 'number' ? `跨模态特征覆盖 ${Math.round(value * 100)}%` : ''
}

const { isDragging, onDragStart, onDragOver, onDragLeave, onDrop, onDragEnd, getDragPhotoClass, getDropTargetClass } = usePhotoDrag({
  onPhotoMove: async (photoId, targetId) => emit('move', photoId, targetId),
  orphanAreaId: ORPHAN_ID,
})
</script>

<template>
  <p v-if="isDragging" class="text-xs text-[var(--story-faint)]">拖动照片到目标章节，即可调整故事归属。</p>
  <div class="space-y-4">
    <article
      v-for="chapter in chapters"
      :key="chapter.id"
      class="story-panel overflow-hidden rounded-[28px]"
      :class="getDropTargetClass(chapter.id)"
      @dragover.prevent="(event: DragEvent) => onDragOver(event, chapter.id)"
      @dragleave="() => onDragLeave(chapter.id)"
      @drop="(event: DragEvent) => onDrop(event, chapter.id)"
    >
      <div class="flex flex-wrap items-center justify-between gap-4 px-5 py-5">
        <div class="min-w-0 flex-1">
          <input
            v-if="editingChapter === chapter.id"
            v-model="editName"
            class="w-full rounded-[18px] border border-[rgba(224,177,106,0.24)] bg-[rgba(255,255,255,0.05)] px-4 py-3 text-lg text-[var(--story-text)] outline-none"
            autofocus
            @keyup.enter="finishRename(chapter)"
            @blur="finishRename(chapter)"
          />
          <template v-else>
            <div class="flex flex-wrap items-center gap-3">
              <p class="font-story text-4xl text-[var(--story-gold-soft)]">{{ chapter.name }}</p>
              <span v-if="chapter.clustering?.needs_review" class="rounded-full border border-[#b98643] bg-[rgba(185,134,67,0.18)] px-3 py-1 text-xs text-[var(--story-gold-soft)]">建议检查</span>
            </div>
            <p class="mt-2 text-sm text-[var(--story-muted)]">{{ chapter.description || '这一章正在等待你填入更明确的叙事重点。' }}</p>
            <p class="mt-2 text-xs text-[var(--story-faint)]">
              {{ qualityLabel(chapter.clustering?.quality_score) }}
              <template v-if="coverageLabel(chapter)"> · {{ coverageLabel(chapter) }}</template>
              <template v-if="chapter.clustering?.degraded_photo_count"> · {{ chapter.clustering.degraded_photo_count }} 张照片使用降级证据</template>
            </p>
            <p class="mt-2 text-xs uppercase tracking-[0.22em] text-[var(--story-faint)]">{{ chapter.photo_ids.length }} Frames · {{ getSegments(chapter).length }} Segments</p>
          </template>
        </div>
        <div class="flex flex-wrap gap-2">
          <button class="story-button-secondary px-4 py-2 text-sm" @click="expandedChapter = expandedChapter === chapter.id ? null : chapter.id">{{ expandedChapter === chapter.id ? '收起' : '展开章节' }}</button>
          <button class="story-button-secondary px-4 py-2 text-sm" @click="editName = chapter.name; editingChapter = chapter.id">重命名</button>
          <button class="rounded-full bg-[#f2d8d2] px-4 py-2 text-sm text-[#8b4339] hover:brightness-95" @click="emit('delete', chapter.id)">删除</button>
        </div>
      </div>
      <div v-if="expandedChapter === chapter.id" class="border-t border-[rgba(224,177,106,0.14)] px-5 py-5">
        <div v-if="getPhotos(chapter.photo_ids).length === 0" class="rounded-[22px] border border-dashed border-[rgba(224,177,106,0.18)] px-5 py-10 text-center text-sm text-[var(--story-muted)]">这个章节还没有镜头。把照片拖拽到这里，或先运行自动整理。</div>
        <div v-else class="space-y-6">
          <section v-for="segment in getSegments(chapter)" :key="segment.id" class="border-t border-[rgba(224,177,106,0.12)] pt-4 first:border-t-0 first:pt-0">
            <div class="mb-3 flex flex-wrap items-center gap-3">
              <p class="text-sm font-medium text-[var(--story-text)]">{{ segment.name }}</p>
              <span class="text-xs text-[var(--story-faint)]">{{ segment.time_range || segment.description }}</span>
              <span v-if="segment.clustering?.needs_review" class="border-l border-[#b98643] pl-3 text-xs text-[var(--story-gold-soft)]">建议检查</span>
            </div>
            <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <article v-for="photo in getPhotos(segment.photo_ids)" :key="photo.id" class="film-frame overflow-hidden rounded-[22px] bg-[rgba(255,255,255,0.04)]" :class="getDragPhotoClass(photo.id)" draggable="true" @dragstart="(event: DragEvent) => onDragStart(event, photo.id, chapter.id)" @dragend="onDragEnd">
                <ProtectedImage :src="photo.url" :alt="photo.filename" class="pointer-events-none h-44 w-full object-cover" />
                <div class="px-3 py-3"><p class="truncate text-sm text-[var(--story-text)]">{{ photo.filename }}</p></div>
              </article>
            </div>
          </section>
        </div>
      </div>
    </article>
  </div>

  <SectionCard v-if="orphanPhotos.length" title="待归档镜头" :description="`${orphanPhotos.length} 张照片还没有进入任何章节。`" tone="accent" eyebrow="Unassigned">
    <div class="grid gap-3 sm:grid-cols-3 lg:grid-cols-5">
      <article v-for="photo in orphanPhotos" :key="photo.id" class="overflow-hidden rounded-[22px] border border-dashed border-[rgba(79,59,42,0.22)] bg-white/60" :class="getDragPhotoClass(photo.id)" draggable="true" @dragstart="(event: DragEvent) => onDragStart(event, photo.id, ORPHAN_ID)" @dragend="onDragEnd">
        <ProtectedImage :src="photo.url" :alt="photo.filename" class="pointer-events-none h-36 w-full object-cover" />
        <div class="px-3 py-3"><p class="truncate text-sm text-[#241c16]">{{ photo.filename }}</p></div>
      </article>
    </div>
  </SectionCard>
</template>

<script setup lang="ts">
import { getAlbumResumeLabel } from '@/shared/workflow/albumWorkflow'
import type { AlbumCard } from '@/shared/types/album'

const props = defineProps<{
  albums: AlbumCard[]
  loading: boolean
  isAuthenticated?: boolean
  deletingAlbumIds?: string[]
}>()

const emit = defineEmits<{
  (e: 'resume', album: AlbumCard): void
  (e: 'delete-album', album: AlbumCard): void
}>()

function handleResume(album: AlbumCard) {
  emit('resume', album)
}

function handleDelete(album: AlbumCard) {
  emit('delete-album', album)
}

function getAlbumMeta(album: AlbumCard) {
  return `${album.photo_count} 张照片 | 状态：${album.status}`
}

function getResumeHint(album: AlbumCard) {
  return getAlbumResumeLabel(album.status)
}

function isDeleting(albumId: string) {
  return props.deletingAlbumIds?.includes(albumId) ?? false
}
</script>

<template>
  <div v-if="props.loading" class="text-sm text-[var(--story-muted)]">加载中...</div>
  <div v-else-if="props.albums.length === 0" class="rounded-[24px] border border-dashed border-[rgba(224,177,106,0.18)] px-5 py-10 text-center text-sm text-[var(--story-muted)]">
    还没有相册。先从左侧创建第一本故事书。
  </div>
  <div v-else class="space-y-3">
    <div
      v-for="album in props.albums"
      :key="album.id"
      class="rounded-[22px] border border-[rgba(224,177,106,0.16)] bg-[rgba(255,255,255,0.04)] px-4 py-4 transition hover:bg-[rgba(255,255,255,0.07)]"
    >
      <div class="flex items-start justify-between gap-4">
        <button
          class="flex min-w-0 flex-1 items-start justify-between gap-4 text-left"
          @click="handleResume(album)"
        >
          <div class="min-w-0 flex-1">
            <p class="font-story text-2xl text-[var(--story-text)]">{{ album.name }}</p>
            <p class="mt-2 text-sm text-[var(--story-muted)]">{{ getAlbumMeta(album) }}</p>
            <p class="mt-1 text-xs text-[var(--story-faint)]">{{ getResumeHint(album) }}</p>
          </div>
          <span class="mt-1 shrink-0 text-sm text-[var(--story-gold-soft)]">继续 →</span>
        </button>
        <button
          class="shrink-0 rounded-full bg-[#f2d8d2] px-3 py-2 text-xs text-[#8b4339] transition hover:brightness-95 disabled:cursor-not-allowed disabled:opacity-50"
          :disabled="isDeleting(album.id)"
          @click.stop="handleDelete(album)"
        >
          {{ isDeleting(album.id) ? '删除中...' : '删除相册' }}
        </button>
      </div>
    </div>
  </div>

  <p v-if="props.isAuthenticated === false" class="mt-4 text-xs text-[var(--story-faint)]">
    你可以先浏览页面结构；真正创建相册、绑定项目和上传素材时会要求登录。
  </p>
</template>

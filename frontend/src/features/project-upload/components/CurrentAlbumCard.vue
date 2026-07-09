<script setup lang="ts">
import type { AlbumCard } from '@/shared/types/album'

const props = defineProps<{
  album: AlbumCard | null
  photosCount: number
  uploading: boolean
  uploadProgress: number
  uploadTotal: number
  deleting?: boolean
}>()

const emit = defineEmits<{
  (e: 'upload-click'): void
  (e: 'go-cleaning'): void
  (e: 'delete-album'): void
}>()

function handleUploadClick() {
  emit('upload-click')
}

function handleGoCleaning() {
  emit('go-cleaning')
}

function handleDeleteAlbum() {
  emit('delete-album')
}
</script>

<template>
  <div class="rounded-[24px] border border-[rgba(224,177,106,0.18)] bg-[rgba(255,255,255,0.03)] p-5">
    <div class="grid gap-3 md:grid-cols-4">
      <div>
        <p class="text-xs uppercase tracking-[0.2em] text-[var(--story-faint)]">Album</p>
        <p class="mt-2 text-lg font-medium text-[var(--story-text)]">{{ props.album?.name }}</p>
      </div>
      <div>
        <p class="text-xs uppercase tracking-[0.2em] text-[var(--story-faint)]">Format</p>
        <p class="mt-2 text-lg font-medium text-[var(--story-text)]">{{ props.album?.book_size }}</p>
      </div>
      <div>
        <p class="text-xs uppercase tracking-[0.2em] text-[var(--story-faint)]">Frames</p>
        <p class="mt-2 text-lg font-medium text-[var(--story-text)]">{{ props.photosCount }} 张</p>
      </div>
      <div>
        <p class="text-xs uppercase tracking-[0.2em] text-[var(--story-faint)]">Status</p>
        <p class="mt-2 text-lg font-medium text-[var(--story-text)]">{{ props.album?.status }}</p>
      </div>
    </div>

    <div class="mt-5 flex flex-wrap items-center gap-3">
      <button class="story-button px-6 py-3 text-sm" :disabled="!props.album?.id || props.uploading || props.deleting" @click="handleUploadClick">
        {{ props.uploading ? '上传中...' : '添加照片素材' }}
      </button>
      <button
        v-if="props.album?.id && props.photosCount > 0"
        class="story-button-secondary px-6 py-3 text-sm"
        :disabled="props.deleting"
        @click="handleGoCleaning"
      >
        进入镜头筛选 →
      </button>
      <button
        v-if="props.album?.id"
        class="rounded-full bg-[#f2d8d2] px-4 py-3 text-sm text-[#8b4339] transition hover:brightness-95 disabled:cursor-not-allowed disabled:opacity-50"
        :disabled="props.deleting || props.uploading"
        @click="handleDeleteAlbum"
      >
        {{ props.deleting ? '删除中...' : '删除当前相册' }}
      </button>
    </div>

    <div v-if="props.uploading" class="mt-5">
      <div class="h-2 overflow-hidden rounded-full bg-[rgba(255,255,255,0.12)]">
        <div class="h-2 rounded-full bg-[var(--story-gold)] transition-all duration-300" :style="{ width: props.uploadTotal ? `${(props.uploadProgress / props.uploadTotal) * 100}%` : '0%' }" />
      </div>
      <p class="mt-2 text-xs text-[var(--story-muted)]">{{ props.uploadProgress }} / {{ props.uploadTotal }}</p>
    </div>
  </div>
</template>

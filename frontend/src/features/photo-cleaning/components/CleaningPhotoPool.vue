<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ImageOff } from 'lucide-vue-next'
import CleaningPhotoCard from './CleaningPhotoCard.vue'
import type { Decision, PhotoItem } from '@/features/photo-cleaning/types'

const props = defineProps<{
  photos: PhotoItem[]
  pendingIds: Set<string>
  resetKey: string
}>()

const emit = defineEmits<{
  (event: 'decide', photoId: string, decision: Exclude<Decision, null>): void
}>()

const renderedCount = ref(24)
const scrollRoot = ref<HTMLElement | null>(null)
const sentinel = ref<HTMLElement | null>(null)
const visiblePhotos = computed(() => props.photos.slice(0, renderedCount.value))
let observer: IntersectionObserver | null = null

function reset() {
  renderedCount.value = 24
  window.requestAnimationFrame(() => scrollRoot.value?.scrollTo({ top: 0 }))
}

function decide(photoId: string, decision: Exclude<Decision, null>) {
  emit('decide', photoId, decision)
}

onMounted(() => {
  observer = new IntersectionObserver((entries) => {
    if (entries.some((entry) => entry.isIntersecting)) {
      renderedCount.value = Math.min(props.photos.length, renderedCount.value + 24)
    }
  }, { root: scrollRoot.value, rootMargin: '240px 0px' })
  if (sentinel.value) observer.observe(sentinel.value)
})

onBeforeUnmount(() => observer?.disconnect())

watch(() => props.resetKey, reset)
watch(() => props.photos.length, (length) => {
  renderedCount.value = Math.min(Math.max(24, renderedCount.value), Math.max(24, length))
})
</script>

<template>
  <div ref="scrollRoot" class="cleaning-photo-pool overflow-y-auto pr-2" tabindex="0" aria-label="照片池">
    <div v-if="props.photos.length" class="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
      <CleaningPhotoCard
        v-for="photo in visiblePhotos"
        :key="photo.id"
        :photo="photo"
        :busy="props.pendingIds.has(photo.id)"
        @decide="decide"
      />
    </div>
    <div v-else class="flex h-full flex-col items-center justify-center text-sm text-[#78695c]">
      <ImageOff :size="28" class="mb-3" />当前照片池为空
    </div>
    <div ref="sentinel" class="h-px" />
  </div>
</template>

<style scoped>
.cleaning-photo-pool {
  height: clamp(480px, 68vh, 760px);
  scrollbar-gutter: stable;
}

@media (max-width: 640px) {
  .cleaning-photo-pool {
    height: 70vh;
    min-height: 360px;
  }
}
</style>

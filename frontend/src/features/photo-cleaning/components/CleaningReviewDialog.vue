<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Check, Images, ShieldCheck, Sparkles, X } from 'lucide-vue-next'
import ProtectedImage from '@/shared/components/ProtectedImage.vue'
import { issueLabel, type PhotoItem, type ReviewAction, type ReviewQueueItem } from '@/features/photo-cleaning/types'

const props = defineProps<{
  visible: boolean
  item: ReviewQueueItem | null
  photoMap: Map<string, PhotoItem>
  position: number
  total: number
  busy: boolean
}>()

const emit = defineEmits<{
  (event: 'resolve', action: ReviewAction): void
  (event: 'resolveRemaining'): void
}>()

const confirmClose = ref(false)
const photos = computed<PhotoItem[]>(() => (props.item?.photo_ids ?? [])
  .map((id) => props.photoMap.get(id))
  .filter((photo): photo is PhotoItem => Boolean(photo)))

watch(() => props.item?.id, () => {
  confirmClose.value = false
})

function requestClose() {
  confirmClose.value = true
}
</script>

<template>
  <div v-if="props.visible && props.item" class="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-3 md:p-6">
    <section role="dialog" aria-modal="true" aria-label="照片复核" class="grid h-[min(92vh,820px)] w-full max-w-5xl grid-rows-[auto_minmax(0,1fr)] overflow-hidden rounded-lg bg-[#fbf8f3] shadow-2xl">
      <header class="z-10 flex items-center justify-between border-b border-[rgba(79,59,42,0.12)] bg-[#fbf8f3] px-5 py-4 md:px-7">
        <div>
          <p class="text-xs text-[#8e6d45]">复核 {{ props.position }} / {{ props.total }}</p>
          <h2 class="mt-1 text-lg font-semibold text-[#241c16]">{{ props.item.kind === 'duplicate_group' ? '相似照片选择' : '照片质量确认' }}</h2>
        </div>
        <button class="flex size-9 items-center justify-center rounded-md text-[#5f5347] hover:bg-black/5" title="关闭复核" aria-label="关闭复核" @click="requestClose">
          <X :size="20" />
        </button>
      </header>

      <div class="space-y-5 overflow-y-auto p-5 md:p-7">
        <div class="flex flex-wrap gap-2">
          <span v-for="reason in props.item.reason_codes" :key="reason" class="rounded bg-[#f3e5cf] px-2.5 py-1 text-xs text-[#815e2d]">
            {{ issueLabel(reason) }}
          </span>
        </div>

        <div v-if="props.item.kind === 'single_photo' && photos[0]" class="mx-auto max-w-3xl">
          <div class="aspect-[4/3] overflow-hidden rounded-lg bg-[#ebe5dd]">
            <ProtectedImage :src="photos[0].url" :alt="photos[0].filename" class="h-full w-full object-contain" />
          </div>
          <p class="mt-3 truncate text-center text-sm font-medium text-[#241c16]">{{ photos[0].filename }}</p>
        </div>

        <div v-else class="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <article v-for="photo in photos" :key="photo.id" class="overflow-hidden rounded-lg border bg-white" :class="photo.id === props.item.preferred_photo_id ? 'border-[#b8843d] ring-1 ring-[#b8843d]' : 'border-[rgba(79,59,42,0.14)]'">
            <div class="relative aspect-[4/3] bg-[#ebe5dd]">
              <ProtectedImage :src="photo.url" :alt="photo.filename" class="h-full w-full object-cover" />
              <span v-if="photo.id === props.item.preferred_photo_id" class="absolute left-2 top-2 inline-flex items-center gap-1 rounded bg-[#8a612b] px-2 py-1 text-xs text-white">
                <ShieldCheck :size="13" /> 系统首选
              </span>
            </div>
            <p class="truncate p-3 text-sm text-[#241c16]">{{ photo.filename }}</p>
          </article>
        </div>

        <div v-if="confirmClose" class="sticky bottom-0 z-10 rounded-lg border border-[#d8b98c] bg-[#fff4df] p-4 shadow-lg">
          <p class="text-sm text-[#5f4930]">将从当前项开始，把剩余全部复核项目按系统建议一次处理。已有人工决定不会被覆盖。</p>
          <div class="mt-3 flex flex-wrap justify-end gap-2">
            <button class="story-button-secondary px-4 py-2 text-sm" @click="confirmClose = false">继续复核</button>
            <button class="story-button px-4 py-2 text-sm" :disabled="props.busy" @click="emit('resolveRemaining')">确认全部交给系统</button>
          </div>
        </div>

        <div v-else-if="props.item.kind === 'single_photo'" class="sticky bottom-0 z-10 grid gap-2 border-t border-[rgba(79,59,42,0.12)] bg-[#fbf8f3] pt-4 sm:grid-cols-3">
          <button class="story-button-secondary inline-flex items-center justify-center gap-2 px-4 py-3 text-sm" :disabled="props.busy" @click="emit('resolve', 'keep')"><Check :size="17" /> 保留</button>
          <button class="rounded-md bg-[#9b4e43] px-4 py-3 text-sm text-white disabled:opacity-50" :disabled="props.busy" @click="emit('resolve', 'remove')">移除</button>
          <button class="story-button inline-flex items-center justify-center gap-2 px-4 py-3 text-sm" :disabled="props.busy" @click="confirmClose = true"><Sparkles :size="17" /> 剩余全部交给系统</button>
        </div>

        <div v-else-if="!confirmClose" class="sticky bottom-0 z-10 grid gap-2 border-t border-[rgba(79,59,42,0.12)] bg-[#fbf8f3] pt-4 sm:grid-cols-3">
          <button class="story-button-secondary inline-flex items-center justify-center gap-2 px-4 py-3 text-sm" :disabled="props.busy" @click="emit('resolve', 'keep_all')"><Images :size="17" /> 全部保留</button>
          <button class="story-button inline-flex items-center justify-center gap-2 px-4 py-3 text-sm" :disabled="props.busy" @click="emit('resolve', 'accept_preferred')"><ShieldCheck :size="17" /> 采用首选</button>
          <button class="story-button inline-flex items-center justify-center gap-2 px-4 py-3 text-sm" :disabled="props.busy" @click="confirmClose = true"><Sparkles :size="17" /> 剩余全部交给系统</button>
        </div>
      </div>
    </section>
  </div>
</template>

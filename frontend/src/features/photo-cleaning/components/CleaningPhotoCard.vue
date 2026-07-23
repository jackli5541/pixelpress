<script setup lang="ts">
import { RotateCcw, Trash2, UserRound } from 'lucide-vue-next'
import ProtectedImage from '@/shared/components/ProtectedImage.vue'
import { issueLabel, type Decision, type PhotoItem } from '@/features/photo-cleaning/types'

const props = defineProps<{
  photo: PhotoItem
  busy: boolean
}>()

const emit = defineEmits<{
  (event: 'decide', photoId: string, decision: Exclude<Decision, null>): void
}>()

function formatFileSize(bytes: number) {
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function formatPercent(value?: number | null) {
  return value == null ? '--' : `${Math.round(value * 100)}%`
}

const exposureNotApplicable = () => props.photo.cleaning.features?.exposure?.severity === 'not_applicable'
</script>

<template>
  <article class="overflow-hidden rounded-lg border border-[rgba(79,59,42,0.14)] bg-white">
    <div class="relative aspect-[4/3] bg-[#eee9e3]">
      <ProtectedImage
        :src="props.photo.url"
        :alt="props.photo.filename"
        class="h-full w-full object-cover"
        :class="props.photo.cleaning.excluded ? 'opacity-55 grayscale' : ''"
      />
      <span
        v-if="props.photo.cleaning.features?.faces?.detected_count"
        class="absolute left-2 top-2 inline-flex items-center gap-1 rounded bg-[rgba(20,18,16,0.78)] px-2 py-1 text-xs text-white"
      >
        <UserRound :size="13" /> {{ props.photo.cleaning.features.faces.detected_count }}
      </span>
      <span class="absolute right-2 top-2 rounded px-2 py-1 text-xs text-white" :class="props.photo.cleaning.excluded ? 'bg-[#9b4e43]' : 'bg-[#4f7048]'">
        {{ props.photo.cleaning.excluded ? '已移除' : '保留' }}
      </span>
    </div>

    <div class="space-y-3 p-4">
      <div>
        <p class="truncate text-sm font-semibold text-[#241c16]">{{ props.photo.filename }}</p>
        <p class="mt-1 text-xs text-[#78695c]">{{ formatFileSize(props.photo.size) }} · {{ props.photo.width }}×{{ props.photo.height }}</p>
      </div>

      <div class="grid grid-cols-4 overflow-hidden rounded-md border border-[rgba(79,59,42,0.12)] text-center text-xs text-[#78695c]">
        <div class="py-2"><b class="block text-sm text-[#241c16]">{{ props.photo.quality_score?.toFixed(1) ?? '-' }}</b>总分</div>
        <div class="border-l py-2"><b class="block text-sm text-[#241c16]">{{ formatPercent(props.photo.cleaning.features?.sharpness?.score) }}</b>清晰</div>
        <div class="border-l py-2"><b class="block text-sm text-[#241c16]">{{ formatPercent(props.photo.cleaning.features?.exposure?.score) }}</b>{{ exposureNotApplicable() ? '不适用' : '曝光' }}</div>
        <div class="border-l py-2"><b class="block text-sm text-[#241c16]">{{ formatPercent(props.photo.cleaning.features?.resolution?.score) }}</b>分辨率</div>
      </div>

      <div v-if="props.photo.cleaning_issues?.length" class="flex flex-wrap gap-1.5">
        <span v-for="issue in props.photo.cleaning_issues" :key="issue" class="rounded bg-[#f3e5cf] px-2 py-1 text-xs text-[#815e2d]">
          {{ issueLabel(issue) }}
        </span>
      </div>

      <button
        v-if="props.photo.cleaning.excluded"
        class="story-button-secondary inline-flex w-full items-center justify-center gap-2 px-3 py-2 text-xs"
        :disabled="props.busy"
        title="恢复保留"
        aria-label="恢复保留"
        @click="emit('decide', props.photo.id, 'keep')"
      >
        <RotateCcw :size="15" /> {{ props.busy ? '处理中' : '恢复保留' }}
      </button>
      <button
        v-else
        class="inline-flex w-full items-center justify-center gap-2 rounded-md bg-[#f1d8d2] px-3 py-2 text-xs text-[#8b4339] disabled:opacity-50"
        :disabled="props.busy"
        title="移除照片"
        aria-label="移除照片"
        @click="emit('decide', props.photo.id, 'remove')"
      >
        <Trash2 :size="15" /> {{ props.busy ? '处理中' : '移除' }}
      </button>
    </div>
  </article>
</template>

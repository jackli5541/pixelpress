<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const props = defineProps<{
  albumId: string
  albumStatus?: string | null
}>()
const route = useRoute()
const router = useRouter()

const steps = [
  { key: 'upload',   label: '上传', path: `/albums/${props.albumId}/upload`,   requires: 'draft' },
  { key: 'cleaning', label: '清洗', path: `/albums/${props.albumId}/cleaning`, requires: 'uploaded' },
  { key: 'chapters', label: '章节', path: `/albums/${props.albumId}/chapters`, requires: 'cleaned' },
  { key: 'planning', label: '排版', path: `/albums/${props.albumId}/planning`, requires: 'clustered' },
  { key: 'export',   label: '导出', path: `/albums/${props.albumId}/export`,   requires: 'rendered' },
]

const statusOrder = ['draft', 'uploaded', 'cleaned', 'clustered', 'planned', 'rendered', 'exported']

const currentKey = computed(() => {
  const p = route.path
  if (p.includes('/upload')) return 'upload'
  if (p.includes('/cleaning')) return 'cleaning'
  if (p.includes('/chapters')) return 'chapters'
  if (p.includes('/planning')) return 'planning'
  if (p.includes('/export')) return 'export'
  return ''
})

const currentIndex = computed(() => steps.findIndex(s => s.key === currentKey.value))

function isStepAccessible(step: typeof steps[0]): boolean {
  if (!props.albumStatus) return step.key === 'upload'
  const currentLevel = statusOrder.indexOf(props.albumStatus)
  const requiredLevel = statusOrder.indexOf(step.requires)
  return currentLevel >= requiredLevel
}

function goStep(step: typeof steps[0]) {
  if (isStepAccessible(step)) {
    router.push(step.path)
  }
}
</script>

<template>
  <div v-if="albumId" class="mb-6 rounded-2xl border border-slate-200 bg-white px-4 py-3 shadow-sm">
    <div class="flex items-center justify-between gap-1">
      <button
        v-for="(step, idx) in steps" :key="step.key"
        @click="goStep(step)"
        :disabled="!isStepAccessible(step)"
        :title="!isStepAccessible(step) ? '请先完成上一步' : ''"
        class="group flex items-center gap-2 rounded-xl px-3 py-2 text-sm transition"
        :class="!isStepAccessible(step)
          ? 'cursor-not-allowed text-slate-300'
          : idx === currentIndex
            ? 'bg-cyan-50 text-cyan-700 font-semibold'
            : idx < currentIndex
              ? 'text-emerald-600 hover:bg-emerald-50'
              : 'text-slate-400 hover:bg-slate-50 hover:text-slate-600'"
      >
        <span
          class="flex h-6 w-6 items-center justify-center rounded-full text-xs font-bold"
          :class="!isStepAccessible(step)
            ? 'bg-slate-100 text-slate-300'
            : idx === currentIndex
              ? 'bg-cyan-600 text-white'
              : idx < currentIndex
                ? 'bg-emerald-500 text-white'
                : 'bg-slate-200 text-slate-500'"
        >
          {{ idx < currentIndex && isStepAccessible(step) ? 'V' : idx + 1 }}
        </span>
        <span class="hidden sm:inline">{{ step.label }}</span>
        <span v-if="!isStepAccessible(step)" class="hidden sm:inline text-[10px] text-slate-300">*</span>
      </button>
    </div>
  </div>
</template>

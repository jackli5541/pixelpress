<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  getAlbumResumeRoute,
  getAlbumStepKey,
  getRouteStepKey,
  isStepAccessible as isAlbumStepAccessible,
  isStepCompleted,
  isStepCurrent,
  type AlbumWorkflowStep,
} from '@/shared/workflow/albumWorkflow'

const props = defineProps<{
  albumId: string
  albumStatus?: string | null
}>()

const route = useRoute()
const router = useRouter()

const steps = computed<{ key: AlbumWorkflowStep; label: string; sublabel: string; path: string }[]>(() => [
  { key: 'upload', label: '收集素材', sublabel: 'Upload', path: `/albums/${props.albumId}/upload` },
  { key: 'cleaning', label: '筛选镜头', sublabel: 'Clean', path: `/albums/${props.albumId}/cleaning` },
  { key: 'chapters', label: '整理章节', sublabel: 'Chapters', path: `/albums/${props.albumId}/chapters` },
  { key: 'planning', label: '编排书页', sublabel: 'Layout', path: `/albums/${props.albumId}/planning` },
  { key: 'export', label: '导出成册', sublabel: 'Export', path: `/albums/${props.albumId}/export` },
])

const persistedCurrentKey = computed(() => getAlbumStepKey(props.albumStatus))
const routeKey = computed(() => getRouteStepKey(route.path))

function isAccessible(stepKey: AlbumWorkflowStep) {
  return isAlbumStepAccessible(props.albumStatus, stepKey)
}

function isCompletedStep(stepKey: AlbumWorkflowStep) {
  return isStepCompleted(props.albumStatus, stepKey)
}

function isCurrentStep(stepKey: AlbumWorkflowStep) {
  return isStepCurrent(props.albumStatus, stepKey)
}

function getStepPath(stepKey: AlbumWorkflowStep) {
  if (stepKey === 'cleaning') return `/albums/${props.albumId}/cleaning`
  if (stepKey === 'chapters') return `/albums/${props.albumId}/chapters`
  if (stepKey === 'planning') return `/albums/${props.albumId}/planning`
  if (stepKey === 'export') return `/albums/${props.albumId}/export`
  return `/albums/${props.albumId}/upload`
}

function goStep(stepKey: AlbumWorkflowStep) {
  if (isAccessible(stepKey)) {
    void router.push(getStepPath(stepKey))
  }
}

const resumePath = computed(() => getAlbumResumeRoute(props.albumId, props.albumStatus))
</script>

<template>
  <div v-if="albumId" class="story-panel overflow-hidden rounded-[28px] px-4 py-4 md:px-6">
    <div class="flex flex-wrap items-center gap-2 md:gap-3">
      <button
        v-for="(step, index) in steps"
        :key="step.key"
        class="group min-w-[108px] rounded-[22px] border px-3 py-3 text-left transition md:flex-1"
        :class="
          !isAccessible(step.key)
            ? 'cursor-not-allowed border-[rgba(224,177,106,0.08)] bg-[rgba(255,255,255,0.02)] text-[rgba(244,234,217,0.32)]'
            : isCurrentStep(step.key)
              ? 'border-[rgba(224,177,106,0.44)] bg-[rgba(203,143,57,0.16)] text-[var(--story-text)]'
              : isCompletedStep(step.key)
                ? 'border-[rgba(113,175,109,0.3)] bg-[rgba(77,116,73,0.16)] text-[var(--story-text)]'
                : 'border-[rgba(224,177,106,0.16)] bg-[rgba(255,255,255,0.04)] text-[var(--story-muted)] hover:bg-[rgba(255,255,255,0.06)]'
        "
        :disabled="!isAccessible(step.key)"
        @click="goStep(step.key)"
      >
        <div class="flex items-center gap-3">
          <span
            class="flex h-9 w-9 items-center justify-center rounded-full border text-sm"
            :class="
              !isAccessible(step.key)
                ? 'border-[rgba(244,234,217,0.08)] text-[rgba(244,234,217,0.28)]'
                : isCurrentStep(step.key)
                  ? 'border-[rgba(224,177,106,0.4)] bg-[var(--story-gold)] text-[#1f150f]'
                  : isCompletedStep(step.key)
                    ? 'border-transparent bg-[#5a7b56] text-white'
                    : 'border-[rgba(224,177,106,0.2)] text-[var(--story-gold-soft)]'
            "
          >
            {{ isCompletedStep(step.key) && isAccessible(step.key) ? '✓' : index + 1 }}
          </span>
          <div>
            <p class="text-xs uppercase tracking-[0.2em] opacity-70">{{ step.sublabel }}</p>
            <p class="mt-1 font-medium">{{ step.label }}</p>
            <p v-if="routeKey === step.key && !isCurrentStep(step.key)" class="mt-1 text-[10px] opacity-60">当前打开页</p>
          </div>
        </div>
      </button>
    </div>
    <p v-if="route.path !== resumePath && routeKey !== persistedCurrentKey" class="mt-3 text-xs text-[var(--story-faint)]">
      当前页面与作品进度不完全一致，建议从系统恢复入口继续编辑。
    </p>
  </div>
</template>

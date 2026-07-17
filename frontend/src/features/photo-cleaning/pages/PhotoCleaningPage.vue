<script setup lang="ts">
import { computed } from 'vue'
import { Check, ChevronRight, ImageOff, RotateCcw, ScanSearch, SlidersHorizontal, X } from 'lucide-vue-next'
import AlbumTaskStatusCard from '@/shared/components/AlbumTaskStatusCard.vue'
import SectionCard from '@/shared/components/SectionCard.vue'
import WorkflowStepper from '@/shared/components/WorkflowStepper.vue'
import CleaningPhotoPool from '@/features/photo-cleaning/components/CleaningPhotoPool.vue'
import CleaningReviewDialog from '@/features/photo-cleaning/components/CleaningReviewDialog.vue'
import { useCleaningPageState } from '@/features/photo-cleaning/composables/useCleaningPageState'

const {
  album,
  albumId,
  applyDecision,
  currentReviewItem,
  errorMessage,
  filteredPhotos,
  goNext,
  hasAnalysis,
  latestTask,
  loading,
  openReview,
  orientationFilter,
  pendingIds,
  photoMap,
  poolMode,
  removedPhotos,
  resolveRemaining,
  resolveReview,
  retainedPhotos,
  reviewActionLoading,
  reviewInitialTotal,
  reviewOpen,
  reviewPosition,
  results,
  startCleaning,
  successMessage,
  summary,
  taskActionLoading,
  undoLastAction,
  undoState,
} = useCleaningPageState()

const taskRunning = computed(() => ['queued', 'running'].includes(latestTask.value?.task_status ?? ''))
</script>

<template>
  <WorkflowStepper v-if="albumId" :album-id="albumId" :album-status="album?.status" />

  <div class="space-y-6">
    <section class="story-panel overflow-hidden rounded-[28px] px-5 py-6 md:px-8">
      <div class="flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p class="text-xs uppercase text-[var(--story-gold-soft)]">Stage B · Photo Cleaning</p>
          <h1 class="font-story mt-2 text-4xl text-[var(--story-text)]">照片清洗</h1>
          <p class="mt-2 text-sm text-[var(--story-muted)]">
            {{ album?.name ?? '当前相册' }} · {{ results?.analysis_version ?? '尚未分析' }}
          </p>
        </div>

        <div class="flex flex-wrap gap-2">
          <button
            v-if="undoState"
            class="story-button-secondary inline-flex items-center gap-2 px-4 py-2 text-sm"
            :disabled="pendingIds.size > 0"
            @click="undoLastAction"
          >
            <RotateCcw :size="16" /> 撤销
          </button>
          <button
            v-if="summary.pending_review"
            class="story-button-secondary inline-flex items-center gap-2 px-4 py-2 text-sm"
            :disabled="reviewActionLoading"
            @click="openReview(true)"
          >
            <SlidersHorizontal :size="16" /> 继续复核（{{ summary.pending_review }}）
          </button>
          <button
            class="story-button inline-flex items-center gap-2 px-5 py-2.5 text-sm"
            :disabled="taskActionLoading || taskRunning || !summary.total"
            @click="startCleaning"
          >
            <ScanSearch :size="17" />
            {{ taskRunning ? '分析中' : hasAnalysis ? '重新分析' : '开始分析' }}
          </button>
          <button
            class="story-button-secondary inline-flex items-center gap-2 px-5 py-2.5 text-sm"
            :disabled="!summary.total"
            @click="goNext"
          >
            进入分章 <ChevronRight :size="17" />
          </button>
        </div>
      </div>

      <div class="mt-6 grid grid-cols-2 gap-px overflow-hidden rounded-lg bg-[rgba(224,177,106,0.18)]">
        <button
          class="bg-[rgba(24,20,18,0.92)] px-4 py-4 text-left"
          :class="poolMode === 'retained' ? 'ring-2 ring-inset ring-[#b8843d]' : ''"
          @click="poolMode = 'retained'"
        >
          <span class="block text-2xl text-white">{{ summary.retained }}</span>
          <span class="text-xs text-[var(--story-muted)]">保留照片</span>
        </button>
        <button
          class="bg-[rgba(24,20,18,0.92)] px-4 py-4 text-left"
          :class="poolMode === 'removed' ? 'ring-2 ring-inset ring-[#9b4e43]' : ''"
          @click="poolMode = 'removed'"
        >
          <span class="block text-2xl text-[#dc8b7e]">{{ summary.removed }}</span>
          <span class="text-xs text-[var(--story-muted)]">已移除照片</span>
        </button>
      </div>
    </section>

    <AlbumTaskStatusCard
      :task="latestTask"
      title="照片清洗任务"
      running-hint="正在分析照片，任务完成后会自动更新结果。"
      empty-text=""
    />

    <div v-if="successMessage || errorMessage" class="sticky top-3 z-20 flex flex-col gap-2">
      <div v-if="successMessage" class="flex items-center gap-2 rounded-lg bg-[#e2eddf] px-4 py-3 text-sm text-[#42643a]">
        <Check :size="17" /> {{ successMessage }}
      </div>
      <div v-if="errorMessage" class="flex items-center gap-2 rounded-lg bg-[#f5d9d3] px-4 py-3 text-sm text-[#8b4339]">
        <X :size="17" /> {{ errorMessage }}
      </div>
    </div>

    <SectionCard v-if="summary.total" title="清洗结果" description="" tone="accent" eyebrow="Result">
      <div class="mb-5 flex flex-col gap-4 border-b border-[rgba(79,59,42,0.12)] pb-5 md:flex-row md:items-center md:justify-between">
        <div class="inline-flex w-full rounded-lg bg-[rgba(43,31,24,0.07)] p-1 md:w-auto">
          <button
            class="min-w-28 rounded-md px-4 py-2 text-sm"
            :class="poolMode === 'retained' ? 'bg-white text-[#241c16] shadow-sm' : 'text-[#78695c]'"
            @click="poolMode = 'retained'"
          >
            保留（{{ retainedPhotos.length }}）
          </button>
          <button
            class="min-w-28 rounded-md px-4 py-2 text-sm"
            :class="poolMode === 'removed' ? 'bg-white text-[#241c16] shadow-sm' : 'text-[#78695c]'"
            @click="poolMode = 'removed'"
          >
            已移除（{{ removedPhotos.length }}）
          </button>
        </div>

        <select
          v-model="orientationFilter"
          aria-label="照片方向"
          class="rounded-lg border border-[rgba(79,59,42,0.18)] bg-white px-3 py-2 text-sm text-[#4f4339]"
        >
          <option value="all">全部方向</option>
          <option value="landscape">横图</option>
          <option value="portrait">竖图</option>
          <option value="square">方图</option>
        </select>
      </div>

      <CleaningPhotoPool
        :photos="filteredPhotos"
        :pending-ids="pendingIds"
        :reset-key="`${poolMode}:${orientationFilter}`"
        @decide="applyDecision"
      />
    </SectionCard>

    <div v-else-if="!loading" class="story-panel rounded-[28px] px-6 py-14 text-center">
      <ImageOff :size="34" class="mx-auto text-[var(--story-gold-soft)]" />
      <p class="mt-4 text-sm text-[var(--story-muted)]">相册中还没有照片</p>
      <RouterLink class="story-button mt-5 inline-flex px-5 py-2.5 text-sm" :to="`/albums/${albumId}/upload`">返回上传</RouterLink>
    </div>
  </div>

  <CleaningReviewDialog
    :visible="reviewOpen"
    :item="currentReviewItem"
    :photo-map="photoMap"
    :position="reviewPosition"
    :total="reviewInitialTotal"
    :busy="reviewActionLoading"
    @resolve="resolveReview"
    @resolve-remaining="resolveRemaining"
  />
</template>

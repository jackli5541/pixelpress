<script setup lang="ts">
import { computed } from 'vue'
import { ArrowLeft, Check, RotateCcw } from 'lucide-vue-next'
import ProtectedImage from '@/shared/components/ProtectedImage.vue'
import type { ThemeAssessment } from '@/features/chapter-clustering/composables/useThemeCuration'
import { useProgressiveList } from '@/shared/composables/useProgressiveList'

interface ReviewPhoto {
  id: string
  filename: string
  url: string
}

const props = defineProps<{
  assessments: ThemeAssessment<ReviewPhoto>[]
  keptCount: number
  reviewCount: number
  excludedCount: number
  view: 'candidate' | 'review' | 'removed'
  selectedIds: Set<string>
  loading: boolean
}>()

const emit = defineEmits<{
  back: []
  'update:view': [value: 'candidate' | 'review' | 'removed']
  'update:selectedIds': [value: Set<string>]
  decision: [photoIds: string[], decision: 'keep' | 'exclude' | null]
  confirm: []
}>()

const reasonLabels: Record<string, string> = {
  matched_year: '主题年份匹配',
  outside_requested_year: '不在主题年份范围内',
  outside_requested_date_range: '不在主题日期范围内',
  missing_capture_time: '缺少拍摄时间',
  photo_embedding_unavailable: '照片向量不可用',
  embedding_model_mismatch: '照片与主题向量模型不一致',
  invalid_embedding_vector: '照片向量无效',
  provisional_threshold: '按临时阈值自动判断',
  constraint_mismatch_unconfirmed: '不满足显式时间范围，但当前不能自动移出',
  cross_modal_match: '画面语义符合主题',
  cross_modal_mismatch: '画面语义与主题不符',
  cross_modal_uncertain: '画面语义处于标定边界',
}

const poolLabel = computed(() => ({
  candidate: '已保留照片池',
  review: '待复核照片池',
  removed: '已移出照片池',
})[props.view])
const {
  scrollRoot,
  sentinel,
  visibleItems: visibleAssessments,
} = useProgressiveList(
  () => props.assessments,
  { resetKey: () => props.view },
)

function selectView(value: 'candidate' | 'review' | 'removed') {
  emit('update:view', value)
  emit('update:selectedIds', new Set())
}

function togglePhoto(photoId: string) {
  const next = new Set(props.selectedIds)
  next.has(photoId) ? next.delete(photoId) : next.add(photoId)
  emit('update:selectedIds', next)
}

function relevanceDisplay(assessment: ThemeAssessment<ReviewPhoto>) {
  if (assessment.relevance_evidence?.calibrated) {
    return `相关度 ${Math.round(assessment.relevance_score * 100)}%`
  }
  if (assessment.relevance_evidence?.score_kind === 'embedding_similarity_rank') {
    return `相似度排序分 ${Math.round(assessment.relevance_score * 100)}`
  }
  if (assessment.relevance_label === 'relevant') return '相关性较高'
  if (assessment.relevance_label === 'off_theme') return '不相关'
  return '证据不足'
}

function assessmentReason(assessment: ThemeAssessment<ReviewPhoto>) {
  return assessment.reasons.map((reason) => reasonLabels[reason] || reason).join(' · ')
}
</script>

<template>
  <div>
    <div class="mb-4 flex items-center justify-between gap-3">
      <button class="story-button-secondary inline-flex items-center gap-2 px-4 py-2 text-xs" @click="emit('back')">
        <ArrowLeft :size="14" /> 返回选择主题
      </button>
      <span class="text-xs text-[#65584e]">可重新选择已有候选或解析自定义主题</span>
    </div>

    <div class="grid grid-cols-3 overflow-hidden rounded-lg border border-[rgba(79,59,42,0.14)]" role="tablist" aria-label="主题照片范围">
      <button class="min-h-11 px-3 py-2.5 text-sm font-medium" :class="view === 'candidate' ? 'bg-[#33271f] text-white' : 'bg-white/70 text-[#65584e]'" role="tab" :aria-selected="view === 'candidate'" @click="selectView('candidate')">已保留 {{ keptCount }}</button>
      <button class="min-h-11 border-l border-[rgba(79,59,42,0.14)] px-3 py-2.5 text-sm font-medium" :class="view === 'review' ? 'bg-[#33271f] text-white' : 'bg-white/70 text-[#65584e]'" role="tab" :aria-selected="view === 'review'" @click="selectView('review')">待复核 {{ reviewCount }}</button>
      <button class="min-h-11 border-l border-[rgba(79,59,42,0.14)] px-3 py-2.5 text-sm font-medium" :class="view === 'removed' ? 'bg-[#33271f] text-white' : 'bg-white/70 text-[#65584e]'" role="tab" :aria-selected="view === 'removed'" @click="selectView('removed')">已移出 {{ excludedCount }}</button>
    </div>

    <div v-if="selectedIds.size" class="mt-4 flex flex-wrap items-center gap-2 border-y border-[rgba(79,59,42,0.12)] py-3">
      <span class="mr-2 text-xs text-[#78695c]">已选 {{ selectedIds.size }} 张</span>
      <button v-if="view === 'removed'" class="story-button-secondary px-3 py-1.5 text-xs" @click="emit('decision', [...selectedIds], 'keep')">恢复照片</button>
      <template v-else-if="view === 'review'">
        <button class="story-button-secondary px-3 py-1.5 text-xs" @click="emit('decision', [...selectedIds], 'keep')">保留照片</button>
        <button class="rounded-md bg-[#9b4e43] px-3 py-1.5 text-xs text-white" @click="emit('decision', [...selectedIds], 'exclude')">移出照片</button>
      </template>
      <button v-else class="rounded-md bg-[#9b4e43] px-3 py-1.5 text-xs text-white" @click="emit('decision', [...selectedIds], 'exclude')">移出照片</button>
      <button class="inline-flex items-center gap-1 px-3 py-1.5 text-xs text-[#65584e]" @click="emit('decision', [...selectedIds], null)"><RotateCcw :size="13" /> 采用系统建议</button>
    </div>

    <div ref="scrollRoot" class="progressive-photo-pool mt-5 overflow-y-auto pr-2" tabindex="0" role="region" :aria-label="poolLabel">
      <div v-if="assessments.length" class="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        <article v-for="assessment in visibleAssessments" :key="assessment.photo.id" :data-photo-id="assessment.photo.id" class="overflow-hidden rounded-lg border border-[rgba(79,59,42,0.14)] bg-white">
          <div class="relative">
            <ProtectedImage :src="assessment.photo.url" :alt="assessment.photo.filename" class="h-44 w-full object-cover" />
            <label class="absolute left-2 top-2 flex size-8 items-center justify-center rounded bg-white/90 shadow"><input type="checkbox" :checked="selectedIds.has(assessment.photo.id)" @change="togglePhoto(assessment.photo.id)" /></label>
            <span class="absolute right-2 top-2 rounded px-2 py-1 text-xs text-white" :class="assessment.effective_decision === 'keep' ? 'bg-[#4f7048]' : assessment.effective_decision === 'review' ? 'bg-[#8a612b]' : 'bg-[#9b4e43]'">{{ assessment.effective_decision === 'keep' ? '已保留' : assessment.effective_decision === 'review' ? '待复核' : '已移出' }}</span>
          </div>
          <div class="space-y-3 p-4">
            <div><p class="truncate text-sm font-semibold text-[#241c16]">{{ assessment.photo.filename }}</p><p class="mt-1 text-xs text-[#78695c]">{{ relevanceDisplay(assessment) }}</p></div>
            <p class="text-xs leading-5 text-[#78695c]">{{ assessmentReason(assessment) }}</p>
            <div class="flex gap-2">
              <button v-if="view === 'removed'" class="story-button-secondary w-full px-3 py-2 text-xs" @click="emit('decision', [assessment.photo.id], 'keep')">恢复照片</button>
              <template v-else-if="assessment.effective_decision === 'review'">
                <button class="story-button-secondary flex-1 px-3 py-2 text-xs" @click="emit('decision', [assessment.photo.id], 'keep')">保留</button>
                <button class="flex-1 rounded-md bg-[#f1d8d2] px-3 py-2 text-xs text-[#8b4339]" @click="emit('decision', [assessment.photo.id], 'exclude')">移出</button>
              </template>
              <button v-else class="w-full rounded-md bg-[#f1d8d2] px-3 py-2 text-xs text-[#8b4339]" @click="emit('decision', [assessment.photo.id], 'exclude')">移出照片</button>
            </div>
          </div>
        </article>
      </div>
      <div v-else class="flex h-full items-center justify-center px-4 text-center text-sm text-[#65584e]">{{ view === 'removed' ? '没有已移出的照片。' : view === 'review' ? '没有待处理的照片。' : '没有已保留的照片。' }}</div>
      <div ref="sentinel" class="h-px" />
    </div>

    <div class="mt-6 flex flex-wrap items-center gap-3">
      <button v-if="reviewCount && view === 'review'" class="story-button-secondary px-4 py-2.5 text-sm" :disabled="loading" @click="emit('decision', assessments.map((item) => item.photo.id), 'keep')">保留全部待复核</button>
      <button class="story-button inline-flex items-center gap-2 px-5 py-2.5 text-sm" :disabled="loading || reviewCount > 0" @click="emit('confirm')"><Check :size="16" /> 确认照片范围</button>
    </div>
  </div>
</template>

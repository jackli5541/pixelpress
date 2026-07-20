<script setup lang="ts">
import { ArrowLeft, Check, RefreshCw, Sparkles } from 'lucide-vue-next'
import type { ChapterStrategy, ThemeCandidate } from '@/features/chapter-clustering/composables/useThemeCuration'

const props = defineProps<{
  phase: string
  rechoosing: boolean
  fallbackUsed: boolean
  candidates: ThemeCandidate[]
  selectedCandidate: ThemeCandidate | null
  selectedCandidateId: string
  selectedStrategy: ChapterStrategy
  strategies: ChapterStrategy[]
  strategyLabels: Record<ChapterStrategy, string>
  customTheme: string
  loading: boolean
}>()
const emit = defineEmits<{
  analyze: [custom: boolean]
  back: []
  choose: [candidate: ThemeCandidate]
  confirm: []
  'update:customTheme': [value: string]
  'update:selectedStrategy': [value: ChapterStrategy]
}>()

function concepts(candidate: ThemeCandidate, key: 'include_concepts' | 'exclude_concepts') {
  const value = candidate.constraints[key]
  return Array.isArray(value) ? value.map(String).join('、') : ''
}
</script>

<template>
  <div v-if="phase === 'needs_analysis'" class="mt-6 flex flex-wrap items-center gap-3">
    <button class="story-button inline-flex items-center gap-2 px-5 py-2.5 text-sm" :disabled="loading" @click="emit('analyze', false)"><Sparkles :size="16" /> 生成候选主题</button>
  </div>
  <button v-if="rechoosing" class="story-button-secondary mt-5 inline-flex items-center gap-2 px-4 py-2 text-xs" @click="emit('back')"><ArrowLeft :size="14" /> 返回照片确认</button>
  <div v-if="rechoosing || ['needs_analysis', 'choose_theme'].includes(phase)" class="mt-5 flex flex-col gap-3 border-t border-[rgba(79,59,42,0.12)] pt-5 sm:flex-row">
    <input :value="customTheme" type="text" maxlength="500" placeholder="输入自定义主题，例如：亲友聚会" class="min-w-0 flex-1 rounded-lg border border-[rgba(79,59,42,0.18)] bg-white px-4 py-2.5 text-sm text-[#241c16] outline-none" @input="emit('update:customTheme', ($event.target as HTMLInputElement).value)" @keyup.enter="customTheme.trim() && emit('analyze', true)" />
    <button class="story-button-secondary inline-flex items-center justify-center gap-2 px-4 py-2.5 text-sm" :disabled="!customTheme.trim() || loading" @click="emit('analyze', true)"><Sparkles :size="15" /> 解析自定义主题</button>
  </div>
  <div v-if="phase === 'choose_theme' || rechoosing" class="mt-6">
    <div class="mb-3 flex flex-wrap items-center justify-between gap-3">
      <p class="text-sm font-semibold text-[#241c16]">候选主题</p>
      <button class="story-button-secondary inline-flex items-center gap-2 px-3 py-2 text-xs" :disabled="loading" @click="emit('analyze', false)">
        <RefreshCw :size="14" :class="loading ? 'animate-spin' : ''" />
        重新生成候选
      </button>
    </div>
    <div v-if="fallbackUsed" class="mb-5 border-l-2 border-[#b98643] bg-[rgba(185,134,67,0.08)] px-4 py-3 text-xs leading-5 text-[#78695c]">智能主题生成失败，当前仅提供“完整记录”。如需使用自定义主题，请在上方输入主题并解析。</div>
    <div class="divide-y divide-[rgba(79,59,42,0.12)] border-y border-[rgba(79,59,42,0.12)]">
      <button v-for="candidate in candidates" :key="candidate.id" class="flex w-full items-start gap-3 px-2 py-4 text-left" @click="emit('choose', candidate)">
        <span class="mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full border" :class="selectedCandidateId === candidate.id ? 'border-[#5b714d] bg-[#5b714d] text-white' : 'border-[#9c8b7d]'">
          <Check v-if="selectedCandidateId === candidate.id" :size="13" />
        </span>
        <span class="min-w-0 flex-1"><span class="block text-sm font-semibold text-[#241c16]">{{ candidate.title }}</span><span class="mt-1 block text-xs text-[#8a612b]">推荐 {{ strategyLabels[candidate.recommended_strategy] }}</span></span>
      </button>
    </div>
    <div v-if="selectedCandidate" class="mt-5 border-l-2 border-[#b98643] pl-4">
      <p class="text-sm font-semibold text-[#241c16]">{{ selectedCandidate.title }}</p>
      <div class="mt-3 flex flex-wrap gap-x-5 gap-y-2 text-xs text-[#78695c]"><span>包含：{{ concepts(selectedCandidate, 'include_concepts') || '不限' }}</span><span>排除：{{ concepts(selectedCandidate, 'exclude_concepts') || '无预设' }}</span></div>
    </div>
    <div class="mt-5">
      <p class="mb-2 text-xs text-[#78695c]">章节组织方式</p>
      <div class="inline-flex max-w-full overflow-x-auto rounded-lg bg-[rgba(43,31,24,0.07)] p-1">
        <button v-for="strategy in strategies" :key="strategy" class="whitespace-nowrap rounded-md px-3 py-2 text-xs" :class="selectedStrategy === strategy ? 'bg-white text-[#241c16] shadow-sm' : 'text-[#78695c]'" @click="emit('update:selectedStrategy', strategy)">{{ strategyLabels[strategy] }}</button>
      </div>
    </div>
    <button class="story-button mt-5 inline-flex items-center gap-2 px-5 py-2.5 text-sm" :disabled="!selectedCandidate || loading" @click="emit('confirm')"><Check :size="16" /> 确认主题并分析照片</button>
  </div>
</template>

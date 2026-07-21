<script setup lang="ts">
import { ArrowLeft } from 'lucide-vue-next'
import SectionCard from '@/shared/components/SectionCard.vue'
import StoryHero from '@/shared/components/StoryHero.vue'
import WorkflowStepper from '@/shared/components/WorkflowStepper.vue'
import ProtectedImage from '@/shared/components/ProtectedImage.vue'
import AlbumTaskStatusCard from '@/shared/components/AlbumTaskStatusCard.vue'
import ThemePhotoReview from '@/features/chapter-clustering/components/ThemePhotoReview.vue'
import ChapterBoard from '@/features/chapter-clustering/components/ChapterBoard.vue'
import ThemeSelectionPanel from '@/features/chapter-clustering/components/ThemeSelectionPanel.vue'
import { useChapterPage } from '@/features/chapter-clustering/composables/useChapterPage'
import { useProgressiveList } from '@/shared/composables/useProgressiveList'

const {
  albumId, loading, actionLoading, errorMessage, successMessage, newChapterName, granularity,
  chapters, allPhotos, albumStatus, displayTask, themeWorkspace, customTheme,
  selectedCandidateId, selectedStrategy, selectedThemePhotoIds, themePhotoView,
  isRechoosingTheme, themeReady, isThemeSelectionPhase, isThemeReviewPhase,
  themeCandidates, selectedCandidate, candidateThemeAssessments,
  reviewThemeAssessments, removedThemeAssessments, visibleThemeAssessments,
  latestThemeTask, needCleaning, reviewChapterCount, showThemePhotoReview,
  hasGeneratedChapters, orphanPhotos, primaryPhotoMetric, secondaryStructureMetric,
  tertiaryPhotoMetric, strategyLabels, chooseCandidate, startThemeAnalysis,
  confirmThemeSelection, returnToThemeSelection, returnToThemeReview,
  applyThemeDecision, confirmThemeReview, startCluster, createChapter,
  renameChapter, deleteChapter, movePhoto, goBack, goNext,
} = useChapterPage()

const {
  scrollRoot: archiveScrollRoot,
  sentinel: archiveSentinel,
  visibleItems: visibleArchivePhotos,
} = useProgressiveList(
  () => allPhotos.value,
  { resetKey: () => `${albumId.value}:${themeWorkspace.value?.phase || ''}` },
)
</script>

<template>
  <WorkflowStepper v-if="albumId" :album-id="albumId" :album-status="albumStatus" />

  <div class="space-y-6">
    <StoryHero
      eyebrow="Chapter Assembly"
      title="把镜头整理成可以阅读的故事章节"
      description="系统会尝试自动聚类，但最终章节结构仍由你把控。每个章节更像一本书里的段落，而不是机械标签。"
    >
      <div class="grid gap-4 md:grid-cols-3">
        <div class="story-panel rounded-[24px] px-4 py-4">
          <p class="font-story text-3xl text-[var(--story-gold-soft)]">{{ primaryPhotoMetric.value }}</p>
          <p class="mt-2 text-sm text-[var(--story-text)]">{{ primaryPhotoMetric.label }}</p>
        </div>
        <div class="story-panel rounded-[24px] px-4 py-4">
          <p class="font-story text-3xl text-[var(--story-gold-soft)]">{{ secondaryStructureMetric.value }}</p>
          <p class="mt-2 text-sm text-[var(--story-text)]">{{ secondaryStructureMetric.label }}</p>
        </div>
        <div class="story-panel rounded-[24px] px-4 py-4">
          <p class="font-story text-3xl text-[var(--story-gold-soft)]">{{ tertiaryPhotoMetric.value }}</p>
          <p class="mt-2 text-sm text-[var(--story-text)]">{{ tertiaryPhotoMetric.label }}</p>
        </div>
      </div>
    </StoryHero>

    <SectionCard
      v-if="themeWorkspace?.enabled && !needCleaning"
      title="叙事主题"
      description=""
      tone="accent"
      eyebrow="Theme"
    >
      <div class="grid grid-cols-3 overflow-hidden rounded-lg border border-[rgba(79,59,42,0.14)] text-center text-xs">
        <div class="px-3 py-3" :class="isThemeSelectionPhase ? 'bg-[#33271f] text-[#f0c98e]' : 'bg-white/60 text-[#78695c]'">选择主题</div>
        <div class="border-x border-[rgba(79,59,42,0.14)] px-3 py-3" :class="isThemeReviewPhase ? 'bg-[#33271f] text-[#f0c98e]' : 'bg-white/60 text-[#78695c]'">确认照片</div>
        <div class="px-3 py-3" :class="themeWorkspace.phase === 'ready_to_cluster' ? 'bg-[#42613d] text-white' : 'bg-white/60 text-[#78695c]'">准备分章</div>
      </div>

      <div class="mt-5">
        <AlbumTaskStatusCard
          :task="latestThemeTask"
          title="主题分析任务"
          running-hint="系统正在分析主题候选与照片相关性。"
          empty-text=""
        />
      </div>

      <p v-if="errorMessage" class="mt-4 rounded-[18px] bg-[#f6d9d3] px-4 py-3 text-sm text-[#8b4339]">
        {{ errorMessage }}
      </p>
      <div
        v-if="themeWorkspace.calibration.decision_mode === 'provisional_binary'"
        class="mt-4 border-l-2 border-[#b98643] bg-[rgba(185,134,67,0.08)] px-4 py-3 text-xs leading-5 text-[#65584e]"
      >
        当前按临时阈值 {{ themeWorkspace.calibration.provisional_threshold?.toFixed(2) }} 自动保留或移出照片。技术异常照片仍会进入待复核。
      </div>
      <div
        v-else-if="themeWorkspace.calibration.status !== 'ready'"
        class="mt-4 border-l-2 border-[#b98643] bg-[rgba(185,134,67,0.08)] px-4 py-3 text-xs leading-5 text-[#65584e]"
      >
        当前向量模型无法自动判断照片范围，请完成待复核照片后再确认范围。
      </div>

      <ThemeSelectionPanel
        :phase="themeWorkspace.phase"
        :rechoosing="isRechoosingTheme"
        :fallback-used="Boolean(themeWorkspace.profile?.fallback_used)"
        :candidates="themeCandidates"
        :selected-candidate="selectedCandidate"
        :selected-candidate-id="selectedCandidateId"
        :selected-strategy="selectedStrategy"
        :strategies="themeWorkspace.strategies"
        :strategy-labels="strategyLabels"
        :custom-theme="customTheme"
        :loading="actionLoading || ['queued', 'running'].includes(latestThemeTask?.task_status || '')"
        @analyze="startThemeAnalysis"
        @back="returnToThemeReview"
        @choose="chooseCandidate"
        @confirm="confirmThemeSelection"
        @update:custom-theme="customTheme = $event"
        @update:selected-strategy="selectedStrategy = $event"
      />

      <ThemePhotoReview
        v-if="showThemePhotoReview"
        :assessments="visibleThemeAssessments"
        :kept-count="candidateThemeAssessments.length"
        :review-count="reviewThemeAssessments.length"
        :excluded-count="removedThemeAssessments.length"
        :view="themePhotoView"
        :selected-ids="selectedThemePhotoIds"
        :loading="actionLoading"
        @back="returnToThemeSelection"
        @update:view="themePhotoView = $event"
        @update:selected-ids="selectedThemePhotoIds = $event"
        @decision="applyThemeDecision"
        @confirm="confirmThemeReview"
      />

      <div v-if="themeWorkspace.phase === 'ready_to_cluster'" class="ready-theme-summary mt-6 flex flex-wrap items-center gap-4 border-l-2 border-[#5b714d] pl-4">
        <button class="story-button-secondary inline-flex items-center gap-2 px-4 py-2 text-xs" :disabled="actionLoading" @click="returnToThemeReview"><ArrowLeft :size="14" /> 返回照片确认</button>
        <div class="min-w-0 flex-1"><p class="text-sm font-semibold text-[#241c16]">{{ themeWorkspace.profile?.title || '完整记录' }}</p><p class="mt-1 text-xs text-[#78695c]">{{ strategyLabels[themeWorkspace.profile?.chapter_strategy || 'balanced'] }} · 已移出 {{ themeWorkspace.summary.excluded }} 张主题外照片</p></div>
      </div>

    </SectionCard>

    <SectionCard
      v-if="isThemeSelectionPhase && !needCleaning && allPhotos.length > 0"
      title="待归档镜头"
      :description="`${allPhotos.length} 张现有照片将在确认主题后进行筛选。`"
      tone="accent"
      eyebrow="Unassigned"
    >
      <div ref="archiveScrollRoot" class="progressive-photo-pool overflow-y-auto pr-2" tabindex="0" role="region" aria-label="待归档镜头照片池">
        <div class="grid gap-3 sm:grid-cols-3 lg:grid-cols-5">
          <article v-for="photo in visibleArchivePhotos" :key="photo.id" :data-photo-id="photo.id" class="overflow-hidden rounded-lg border border-[rgba(79,59,42,0.14)] bg-white/70">
            <ProtectedImage :src="photo.url" :alt="photo.filename" class="h-36 w-full object-cover" />
            <div class="px-3 py-3"><p class="truncate text-sm text-[#241c16]">{{ photo.filename }}</p></div>
          </article>
        </div>
        <div ref="archiveSentinel" class="h-px" />
      </div>
    </SectionCard>

    <SectionCard
      v-if="needCleaning || themeReady"
      title="章节整理"
      description="你可以先自动聚类，再手动重命名章节、调整照片归属，让叙事结构更符合你的想法。"
      tone="film"
      eyebrow="Step 3"
    >
      <div v-if="!loading && needCleaning" class="rounded-[22px] border border-[#8e6732] bg-[rgba(170,120,44,0.14)] px-4 py-4 text-sm text-[var(--story-muted)]">
        请先完成镜头筛选，再进入章节整理。
        <button class="story-button-secondary ml-3 px-4 py-2 text-sm" @click="goBack">返回筛选页</button>
      </div>

      <div v-if="themeReady" class="mt-4 flex flex-wrap items-center gap-3">
        <button class="story-button px-6 py-3 text-sm" :disabled="!albumId || actionLoading || needCleaning" @click="startCluster">
          <span class="text-sm">{{ actionLoading ? '整理中...' : '自动整理章节' }}</span>
        </button>
        <div class="min-w-[220px] rounded-lg border border-[rgba(224,177,106,0.18)] px-4 py-3">
          <div class="mb-2 flex items-center justify-between gap-3 text-xs text-[var(--story-muted)]">
            <span>章节粒度</span>
            <span>{{ ['更概括', '较概括', '自动', '较细致', '更细致'][granularity + 2] }}</span>
          </div>
          <input
            v-model.number="granularity"
            type="range"
            min="-2"
            max="2"
            step="1"
            class="w-full accent-[#b98643]"
            aria-label="章节粒度"
          />
        </div>
        <button v-if="themeWorkspace?.enabled && themeWorkspace.phase === 'ready_to_cluster' && chapters.length === 0" class="story-button-secondary inline-flex items-center gap-2 px-5 py-3 text-sm" :disabled="actionLoading" @click="returnToThemeReview">
          <ArrowLeft :size="15" /> 返回照片确认
        </button>
        <div class="flex flex-wrap items-center gap-2">
          <input
            v-model="newChapterName"
            type="text"
            placeholder="新章节名称"
            class="rounded-full border border-[rgba(224,177,106,0.18)] bg-[rgba(255,255,255,0.05)] px-4 py-3 text-sm text-[var(--story-text)] outline-none placeholder:text-[var(--story-faint)]"
            @keyup.enter="createChapter"
          />
          <button class="story-button-secondary px-4 py-3 text-sm" @click="createChapter">新增章节</button>
        </div>
        <button v-if="chapters.length > 0" class="story-button-secondary ml-auto px-6 py-3 text-sm" @click="goNext">
          进入页面编排 →
        </button>
      </div>

      <div v-if="themeReady" class="mt-4">
        <AlbumTaskStatusCard
          :task="displayTask"
          title="章节整理任务"
          running-hint="系统正在整理章节结构，页面会自动轮询最新状态。"
          empty-text="点击“自动整理章节”后，这里会显示任务状态、AI 回退信息和章节结果摘要。"
        />
      </div>
      <div
        v-if="reviewChapterCount > 0"
        class="mt-4 rounded-[20px] border border-[#8e6732] bg-[rgba(170,120,44,0.14)] px-4 py-3 text-sm text-[var(--story-muted)]"
      >
        有 {{ reviewChapterCount }} 个章节的自动归属依据较弱，建议展开章节并检查照片归属；这不会阻止继续编排。
      </div>

      <div v-if="successMessage || errorMessage" class="mt-4 flex flex-col gap-3">
        <p v-if="successMessage" class="rounded-[18px] bg-[#dcead5] px-4 py-3 text-sm text-[#47673d]">{{ successMessage }}</p>
        <p v-if="errorMessage" class="rounded-[18px] bg-[#f6d9d3] px-4 py-3 text-sm text-[#8b4339]">{{ errorMessage }}</p>
      </div>

    </SectionCard>

    <ChapterBoard
      v-if="hasGeneratedChapters"
      :chapters="chapters"
      :photos="allPhotos"
      :orphan-photos="orphanPhotos"
      @rename="renameChapter"
      @delete="deleteChapter"
      @move="movePhoto"
    />

    <div v-if="!loading && chapters.length === 0 && albumId && themeReady" class="story-panel rounded-[28px] px-6 py-12 text-center">
      <p class="font-story text-4xl text-[var(--story-gold-soft)]">No Chapters Yet</p>
      <p class="mt-3 text-sm text-[var(--story-muted)]">先点击“自动整理章节”，或者手动新建第一章。</p>
    </div>
  </div>
</template>

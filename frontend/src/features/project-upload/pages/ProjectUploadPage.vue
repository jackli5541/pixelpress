<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import SectionCard from '@/shared/components/SectionCard.vue'
import StoryHero from '@/shared/components/StoryHero.vue'
import WorkflowStepper from '@/shared/components/WorkflowStepper.vue'
import ProtectedImage from '@/shared/components/ProtectedImage.vue'
import AlbumShowcaseBackdrop from '@/shared/components/AlbumShowcaseBackdrop.vue'
import CurrentAlbumCard from '@/features/project-upload/components/CurrentAlbumCard.vue'
import ProjectBindingCard from '@/features/project-upload/components/ProjectBindingCard.vue'
import CreateAlbumCard from '@/features/project-upload/components/CreateAlbumCard.vue'
import RecentAlbumsList from '@/features/project-upload/components/RecentAlbumsList.vue'
import DeleteProjectDialog from '@/features/project-upload/components/DeleteProjectDialog.vue'
import { useProjectUploadPageState } from '@/features/project-upload/composables/useProjectUploadPageState'

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000/api/v1'

const route = useRoute()
const router = useRouter()
const currentAlbumId = computed(() => {
  const id = route.params.id
  return typeof id === 'string' ? id : ''
})

const {
  form,
  albums,
  projects,
  currentAlbum,
  photos,
  loading,
  projectsLoading,
  submitting,
  uploading,
  deletingProjectId,
  deletingAlbumIds,
  deletingPhotoIds,
  showDeleteProjectDialog,
  projectPendingDelete,
  deleteProjectError,
  errorMessage,
  successMessage,
  uploadProgress,
  uploadTotal,
  fileInput,
  isAuthenticated,
  currentProject,
  formatFileSize,
  submitAlbum,
  triggerFileSelect,
  goToAlbumResume,
  openDeleteProjectDialog,
  closeDeleteProjectDialog,
  confirmDeleteProject,
  deleteAlbum,
  handleFilesSelected,
  deletePhoto,
  goToCleaning,
} = useProjectUploadPageState({
  albumId: currentAlbumId,
  router,
  apiBase: API_BASE,
})
</script>

<template>
  <WorkflowStepper v-if="currentAlbumId" :album-id="currentAlbumId" :album-status="currentAlbum?.status" />

  <div class="space-y-6">
    <div class="relative overflow-hidden rounded-[32px]">
      <AlbumShowcaseBackdrop mode="hero" />
      <StoryHero
        eyebrow="Story Project"
        title="把散落的照片整理成一本有节奏的故事书"
        description="先选择项目，再创建相册并上传素材。每一步都围绕成册体验设计，而不是普通图库操作。"
      >
        <div class="grid gap-4 md:grid-cols-3">
          <div class="story-panel rounded-[24px] px-4 py-4">
            <p class="text-xs uppercase tracking-[0.24em] text-[var(--story-faint)]">Step 01</p>
            <p class="mt-2 font-story text-3xl text-[var(--story-gold-soft)]">Project</p>
            <p class="mt-2 text-sm text-[var(--story-muted)]">为故事书选择明确归属的项目。</p>
          </div>
          <div class="story-panel rounded-[24px] px-4 py-4">
            <p class="text-xs uppercase tracking-[0.24em] text-[var(--story-faint)]">Step 02</p>
            <p class="mt-2 font-story text-3xl text-[var(--story-gold-soft)]">Album</p>
            <p class="mt-2 text-sm text-[var(--story-muted)]">为这一册命名，定义作品主题。</p>
          </div>
          <div class="story-panel rounded-[24px] px-4 py-4">
            <p class="text-xs uppercase tracking-[0.24em] text-[var(--story-faint)]">Step 03</p>
            <p class="mt-2 font-story text-3xl text-[var(--story-gold-soft)]">Frames</p>
            <p class="mt-2 text-sm text-[var(--story-muted)]">上传镜头素材，开始成章成册。</p>
          </div>
        </div>
      </StoryHero>
    </div>

    <div v-if="currentAlbum" class="relative overflow-hidden rounded-[28px]">
      <AlbumShowcaseBackdrop mode="editorial" />
      <SectionCard
        title="当前作品"
        :description="`正在为《${currentAlbum.name}》收集素材。上传完成后即可进入镜头筛选。`"
        tone="film"
        eyebrow="Current Album"
      >
        <input ref="fileInput" type="file" accept="image/*,.heic" multiple class="hidden" @change="handleFilesSelected" />

        <div class="grid gap-4 lg:grid-cols-[1.2fr_0.8fr]">
          <CurrentAlbumCard
            :album="currentAlbum"
            :photos-count="photos.length"
            :uploading="uploading"
            :upload-progress="uploadProgress"
            :upload-total="uploadTotal"
            :deleting="currentAlbum ? deletingAlbumIds.includes(currentAlbum.id) : false"
            @upload-click="triggerFileSelect"
            @go-cleaning="goToCleaning"
            @delete-album="currentAlbum && deleteAlbum(currentAlbum)"
          />

          <ProjectBindingCard
            :project="currentProject"
            @delete-project="openDeleteProjectDialog"
          />
        </div>

        <div v-if="successMessage || errorMessage" class="mt-4 flex flex-col gap-3">
          <p v-if="successMessage" class="rounded-[18px] bg-[#dcead5] px-4 py-3 text-sm text-[#47673d]">{{ successMessage }}</p>
          <p v-if="errorMessage" class="rounded-[18px] bg-[#f6d9d3] px-4 py-3 text-sm text-[#8b4339]">{{ errorMessage }}</p>
        </div>
      </SectionCard>
    </div>

    <SectionCard
      v-if="photos.length > 0"
      title="素材接触表"
      :description="`已收录 ${photos.length} 张照片。这里保持作品打样感，而不是普通文件列表。`"
      tone="film"
      eyebrow="Contact Sheet"
    >
      <div class="contact-sheet rounded-[24px] border border-[rgba(224,177,106,0.16)] p-4">
        <div class="grid gap-3 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
          <div v-for="photo in photos" :key="photo.id" class="film-frame overflow-hidden rounded-[22px] bg-[rgba(255,255,255,0.04)]">
            <ProtectedImage :src="photo.url" :alt="photo.filename" class="h-44 w-full object-cover" />
            <div class="px-3 py-3">
              <div class="flex items-start justify-between gap-3">
                <div class="min-w-0 flex-1">
                  <p class="truncate text-sm text-[var(--story-text)]">{{ photo.filename }}</p>
                  <p class="mt-1 text-xs text-[var(--story-muted)]">{{ formatFileSize(photo.size) }}</p>
                </div>
                <button
                  class="rounded-full bg-[#f2d8d2] px-3 py-1.5 text-xs text-[#8b4339] transition hover:brightness-95 disabled:cursor-not-allowed disabled:opacity-50"
                  :disabled="deletingPhotoIds.includes(photo.id)"
                  @click="deletePhoto(photo)"
                >
                  {{ deletingPhotoIds.includes(photo.id) ? '删除中...' : '删除' }}
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </SectionCard>

    <div class="grid gap-6 lg:grid-cols-[1.08fr_0.92fr]">
      <SectionCard
        title="开始一本新故事书"
        description="明确项目归属后，再为相册命名并进入素材上传。这里刻意保持流程感，而不是堆很多字段。"
        tone="accent"
        eyebrow="Create Album"
      >
        <CreateAlbumCard
          :name="form.name"
          :project-id="form.project_id"
          :projects="projects"
          :projects-loading="projectsLoading"
          :submitting="submitting"
          :is-authenticated="isAuthenticated"
          @update:name="form.name = $event"
          @update:projectId="form.project_id = $event"
          @submit="submitAlbum"
        />
      </SectionCard>

      <SectionCard
        title="最近创作"
        description="继续此前的相册，直接回到素材收集或后续编排阶段。"
        tone="film"
        eyebrow="Recent Albums"
      >
        <RecentAlbumsList
          :albums="albums"
          :loading="loading"
          :is-authenticated="isAuthenticated"
          :deleting-album-ids="deletingAlbumIds"
          @resume="goToAlbumResume"
          @delete-album="deleteAlbum"
        />
      </SectionCard>
    </div>
    <DeleteProjectDialog
      :visible="showDeleteProjectDialog"
      :project="projectPendingDelete"
      :error-message="deleteProjectError"
      :loading="deletingProjectId === projectPendingDelete?.id"
      @close="closeDeleteProjectDialog"
      @confirm="confirmDeleteProject"
    />
  </div>
</template>

<script setup lang="ts">
import type { ProjectSummary } from '@/shared/types/admin'

const props = defineProps<{
  visible: boolean
  project: ProjectSummary | null
  errorMessage: string
  loading: boolean
}>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'confirm'): void
}>()

function handleMaskClose() {
  emit('close')
}

function handleConfirmClick() {
  emit('confirm')
}
</script>

<template>
  <div v-if="visible && props.project" class="fixed inset-0 z-50 flex items-center justify-center bg-black/55 px-4" @click.self="handleMaskClose">
    <div class="paper-panel w-full max-w-lg rounded-[28px] p-6">
      <p class="text-xs uppercase tracking-[0.24em] text-[#8e6d45]">Danger Zone</p>
      <p class="mt-3 font-story text-3xl text-[#241c16]">删除项目《{{ props.project.name }}》</p>
      <p class="mt-4 text-sm leading-7 text-[#5f5347]">
        该操作只会删除当前项目本身。若项目下仍有关联相册，系统会阻止删除，请先把这些相册迁移到其他项目或清空后再试。
      </p>
      <p v-if="errorMessage" class="mt-4 rounded-[16px] bg-[#f6d9d3] px-4 py-3 text-sm text-[#8b4339]">{{ errorMessage }}</p>
      <div class="mt-6 flex flex-wrap justify-end gap-3">
        <button class="rounded-[18px] border border-[rgba(79,59,42,0.14)] px-5 py-3 text-sm text-[#5f5347]" @click="handleMaskClose">
          取消
        </button>
        <button
          class="rounded-[18px] bg-[#8b4339] px-5 py-3 text-sm text-white disabled:cursor-not-allowed disabled:opacity-50"
          :disabled="loading"
          @click="handleConfirmClick"
        >
          {{ loading ? '删除中...' : '确认删除项目' }}
        </button>
      </div>
    </div>
  </div>
</template>

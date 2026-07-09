<script setup lang="ts">
import type { ProjectSummary } from '@/shared/types/admin'

const props = defineProps<{
  project: ProjectSummary | null
}>()

const emit = defineEmits<{
  (e: 'delete-project', project: ProjectSummary): void
}>()

function handleDeleteClick() {
  if (props.project) {
    emit('delete-project', props.project)
  }
}
</script>

<template>
  <div class="paper-panel rounded-[24px] p-5">
    <p class="text-xs uppercase tracking-[0.24em] text-[#8e6d45]">Project Binding</p>
    <p class="font-story mt-3 text-3xl text-[#2a211a]">{{ props.project?.name || '当前项目' }}</p>
    <p class="mt-3 text-sm leading-7 text-[#5f5347]">
      该相册会和当前项目绑定，后续章节、排版、模型选择和审计记录都归档在同一项目内。
    </p>
    <div class="mt-5 rounded-[20px] bg-white/70 px-4 py-4">
      <p class="text-sm text-[#3f342b]">项目编码</p>
      <p class="mt-1 text-lg font-medium text-[#1f1712]">{{ props.project?.code || '-' }}</p>
    </div>
    <button
      v-if="props.project"
      class="mt-4 w-full rounded-[18px] border border-[#d8b983] px-4 py-3 text-sm text-[#6f4c1f] transition hover:bg-[rgba(216,185,131,0.15)]"
      @click="handleDeleteClick"
    >
      删除当前项目
    </button>
  </div>
</template>

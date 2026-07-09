<script setup lang="ts">
import type { ProjectSummary } from '@/shared/types/admin'

const props = defineProps<{
  name: string
  projectId: string
  projects: ProjectSummary[]
  projectsLoading: boolean
  submitting: boolean
  isAuthenticated: boolean
}>()

const emit = defineEmits<{
  (e: 'update:name', value: string): void
  (e: 'update:projectId', value: string): void
  (e: 'submit'): void
}>()

function handleNameInput(event: Event) {
  emit('update:name', (event.target as HTMLInputElement).value)
}

function handleProjectChange(event: Event) {
  emit('update:projectId', (event.target as HTMLSelectElement).value)
}

function handleSubmit() {
  emit('submit')
}
</script>

<template>
  <div class="space-y-4">
    <label class="block space-y-2">
      <span class="text-sm font-medium text-[#3f342b]">相册名称</span>
      <input
        :value="props.name"
        type="text"
        placeholder="例如：2025 夏日家庭故事"
        class="w-full rounded-[20px] border border-[rgba(79,59,42,0.14)] bg-white/75 px-4 py-3 text-sm text-[#231b16] outline-none transition focus:border-[var(--story-gold)]"
        @input="handleNameInput"
      />
    </label>

    <label class="block space-y-2">
      <span class="text-sm font-medium text-[#3f342b]">选择项目</span>
      <select
        :value="props.projectId"
        class="w-full rounded-[20px] border border-[rgba(79,59,42,0.14)] bg-white/75 px-4 py-3 text-sm text-[#231b16] outline-none transition focus:border-[var(--story-gold)]"
        :disabled="!props.isAuthenticated || props.projectsLoading"
        @change="handleProjectChange"
      >
        <option value="">{{ props.projectsLoading ? '项目加载中...' : '请选择所属项目' }}</option>
        <option v-for="project in props.projects" :key="project.id" :value="project.id">
          {{ project.name }} ({{ project.code }})
        </option>
      </select>
    </label>

    <div class="rounded-[20px] bg-white/70 px-4 py-4">
      <p class="text-xs uppercase tracking-[0.22em] text-[#8e6d45]">为什么要选项目</p>
      <p class="mt-2 text-sm leading-7 text-[#5f5347]">
        项目是这本故事书的归档单位。后续模型配置、日志、任务和相册都会与该项目关联。
      </p>
    </div>

    <button class="story-button px-6 py-3 text-sm" :disabled="props.submitting" @click="handleSubmit">
      {{ props.submitting ? '创建中...' : props.isAuthenticated ? '创建并进入上传' : '登录后开始创建' }}
    </button>
  </div>
</template>

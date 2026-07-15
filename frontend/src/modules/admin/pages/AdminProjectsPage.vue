<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { httpGet } from '@/shared/api/http'
import type { ProjectSummary } from '@/shared/types/admin'
import SectionCard from '@/shared/components/SectionCard.vue'

const projects = ref<ProjectSummary[]>([])
const loading = ref(false)
const errorMessage = ref('')

async function loadProjects() {
  loading.value = true
  errorMessage.value = ''
  try {
    projects.value = (await httpGet<ProjectSummary[]>('/admin/projects')).data
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '加载项目失败。'
  } finally {
    loading.value = false
  }
}

onMounted(() => void loadProjects())
</script>

<template>
  <div class="space-y-6">
    <SectionCard title="项目管理" description="每个用户对应一个项目；在详情页维护项目名称、状态和安全删除。" eyebrow="Business" tone="admin">
      <div class="flex flex-wrap items-center justify-between gap-3">
        <p class="text-sm text-[var(--admin-muted)]">共 {{ projects.length }} 位用户项目</p>
      </div>
      <p v-if="errorMessage" class="mt-4 rounded-xl bg-[#f6e2de] px-4 py-3 text-sm text-[#9b4d42]">{{ errorMessage }}</p>
      <div v-if="loading" class="mt-5 text-sm text-[var(--admin-muted)]">加载中...</div>
      <div v-else-if="projects.length === 0" class="mt-5 rounded-2xl border border-dashed border-[var(--admin-border)] px-4 py-10 text-center text-sm text-[var(--admin-muted)]">暂无项目</div>
      <div v-else class="mt-5 overflow-hidden rounded-2xl border border-[var(--admin-border)]">
        <router-link v-for="project in projects" :key="project.id" :to="`/admin/projects/${project.id}`" class="flex flex-wrap items-center gap-x-5 gap-y-2 border-b border-[var(--admin-border)] bg-white px-4 py-4 last:border-b-0 hover:bg-[#faf7f1]">
          <div class="min-w-[180px] flex-1"><p class="font-medium text-[var(--admin-text)]">{{ project.username }}</p><p class="mt-1 text-xs text-[var(--admin-muted)]">{{ project.name }} · {{ project.code }}</p></div>
          <span class="rounded-full bg-[#f1efe9] px-3 py-1 text-xs text-[var(--admin-muted)]">{{ project.status }}</span>
          <span class="text-sm text-[var(--admin-accent)]">查看 →</span>
        </router-link>
      </div>
    </SectionCard>
  </div>
</template>

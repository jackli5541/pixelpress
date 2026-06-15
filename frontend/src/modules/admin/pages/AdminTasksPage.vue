<script setup lang="ts">
import { onMounted, ref } from 'vue'
import SectionCard from '@/shared/components/SectionCard.vue'
import { httpGet } from '@/shared/api/http'
import type { TaskItem } from '@/shared/types/album'

const tasks = ref<TaskItem[]>([])
const loading = ref(false)
const errorMessage = ref('')

async function loadTasks() {
  loading.value = true; errorMessage.value = ''
  try { const response = await httpGet<TaskItem[]>('/tasks'); tasks.value = response.data } catch (error) { errorMessage.value = error instanceof Error ? error.message : '加载失败' } finally { loading.value = false }
}

onMounted(loadTasks)
</script>

<template>
  <div class="space-y-6">
    <SectionCard title="管理后台" description="查看所有后台任务状态。" eyebrow="管理端">
      <div v-if="loading" class="text-sm text-slate-500">加载中...</div>
      <div v-else-if="tasks.length === 0" class="rounded-2xl border border-dashed border-slate-300 px-4 py-8 text-sm text-slate-500">暂无任务。</div>
      <div v-else class="overflow-hidden rounded-3xl border border-slate-200">
        <div class="grid grid-cols-[1fr_100px_160px] border-b border-slate-200 bg-slate-50 px-4 py-3 text-xs text-slate-500"><span>任务类型</span><span>状态</span><span>创建时间</span></div>
        <div v-for="task in tasks" :key="task.id" class="grid grid-cols-[1fr_100px_160px] items-center border-b border-slate-100 px-4 py-4 text-sm last:border-b-0">
          <span class="text-slate-800">{{ task.task_type }}</span>
          <span class="inline-flex w-fit rounded-full px-3 py-1" :class="task.task_status === 'succeeded' ? 'bg-emerald-100 text-emerald-700' : task.task_status === 'failed' ? 'bg-rose-100 text-rose-700' : 'bg-slate-100 text-slate-600'">{{ task.task_status }}</span>
          <span class="text-xs text-slate-500">{{ task.created_at }}</span>
        </div>
      </div>
      <p v-if="errorMessage" class="mt-3 text-sm text-rose-600">{{ errorMessage }}</p>
    </SectionCard>
  </div>
</template>

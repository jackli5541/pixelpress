<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { httpGet } from '@/shared/api/http'
import type { TaskItem } from '@/shared/types/album'
import SectionCard from '@/shared/components/SectionCard.vue'

const tasks = ref<TaskItem[]>([])
const expandedIds = ref<string[]>([])
const loading = ref(false)
const errorMessage = ref('')

function isExpanded(id: string) { return expandedIds.value.includes(id) }
function toggle(id: string) { expandedIds.value = isExpanded(id) ? expandedIds.value.filter((item) => item !== id) : [...expandedIds.value, id] }
async function loadTasks() {
  loading.value = true
  errorMessage.value = ''
  try { tasks.value = (await httpGet<TaskItem[]>('/tasks')).data } catch (error) { errorMessage.value = error instanceof Error ? error.message : '加载任务失败。' } finally { loading.value = false }
}
onMounted(() => void loadTasks())
</script>

<template>
  <SectionCard title="任务监控" description="优先展示任务状态和关键错误；诊断数据按需展开。" eyebrow="Operations" tone="admin">
    <div class="flex items-center justify-between gap-3"><p class="text-sm text-[var(--admin-muted)]">共 {{ tasks.length }} 个任务</p><button class="rounded-xl border border-[var(--admin-border)] px-4 py-2 text-sm hover:bg-[#faf7f1]" @click="loadTasks">刷新</button></div>
    <p v-if="errorMessage" class="mt-4 rounded-xl bg-[#f6e2de] px-4 py-3 text-sm text-[#9b4d42]">{{ errorMessage }}</p>
    <div v-if="loading" class="mt-5 text-sm text-[var(--admin-muted)]">加载中...</div>
    <div v-else-if="tasks.length === 0" class="mt-5 rounded-2xl border border-dashed border-[var(--admin-border)] px-4 py-10 text-center text-sm text-[var(--admin-muted)]">暂无任务</div>
    <div v-else class="mt-5 space-y-3"><article v-for="task in tasks" :key="task.id" class="admin-card rounded-2xl p-4"><div class="flex flex-wrap items-center gap-2"><p class="mr-auto font-medium">{{ task.task_type }}</p><span class="rounded-full px-3 py-1 text-xs" :class="task.task_status === 'succeeded' ? 'bg-[#e5f0e1] text-[#4b6f49]' : task.task_status === 'failed' ? 'bg-[#f6e2de] text-[#9b4d42]' : 'bg-[#f1efe9] text-[var(--admin-muted)]'">{{ task.task_status }}</span><span class="text-xs text-[var(--admin-muted)]">{{ task.created_at }}</span></div><div class="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-xs text-[var(--admin-muted)]"><span>阶段：{{ task.progress_step || '-' }}</span><span v-if="task.pipeline_name">流程：{{ task.pipeline_name }}</span><span v-if="task.provider">{{ task.provider }}{{ task.model ? ` / ${task.model}` : '' }}</span><span v-if="task.error_message" class="text-[#9b4d42]">错误：{{ task.error_message }}</span></div><button class="mt-3 text-sm text-[var(--admin-accent)] hover:underline" @click="toggle(task.id)">{{ isExpanded(task.id) ? '收起详情' : '查看详情' }}</button><div v-if="isExpanded(task.id)" class="mt-3 grid gap-3 text-xs xl:grid-cols-3"><pre class="overflow-auto rounded-xl bg-[#faf7f1] p-3">{{ JSON.stringify(task.debug_payload || {}, null, 2) }}</pre><pre class="overflow-auto rounded-xl bg-[#faf7f1] p-3">{{ JSON.stringify(task.metrics_payload || {}, null, 2) }}</pre><pre class="overflow-auto rounded-xl bg-[#faf7f1] p-3">{{ JSON.stringify(task.result_payload || {}, null, 2) }}</pre></div></article></div>
  </SectionCard>
</template>

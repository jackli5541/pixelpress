<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { httpGet } from '@/shared/api/http'
import type { AdminAuditLogItem, ProjectSummary } from '@/shared/types/admin'
import SectionCard from '@/shared/components/SectionCard.vue'

const projects = ref<ProjectSummary[]>([])
const selectedProjectId = ref('')
const logs = ref<AdminAuditLogItem[]>([])
const expandedIds = ref<string[]>([])
const loading = ref(false)
const errorMessage = ref('')
function isExpanded(id: string) { return expandedIds.value.includes(id) }
function toggle(id: string) { expandedIds.value = isExpanded(id) ? expandedIds.value.filter((item) => item !== id) : [...expandedIds.value, id] }
async function loadLogs() {
  loading.value = true
  errorMessage.value = ''
  try { const query = selectedProjectId.value ? `?project_id=${encodeURIComponent(selectedProjectId.value)}` : ''; logs.value = (await httpGet<AdminAuditLogItem[]>(`/admin/audit-logs${query}`)).data } catch (error) { errorMessage.value = error instanceof Error ? error.message : '加载操作日志失败。' } finally { loading.value = false }
}
onMounted(async () => { try { projects.value = (await httpGet<ProjectSummary[]>('/admin/projects')).data; await loadLogs() } catch (error) { errorMessage.value = error instanceof Error ? error.message : '加载项目失败。' } })
watch(selectedProjectId, () => void loadLogs())
</script>

<template>
  <SectionCard title="操作日志" description="查看后台操作记录；可按项目筛选，并按需展开完整记录。" eyebrow="Operations" tone="admin">
    <div class="flex flex-wrap items-end justify-between gap-3"><label class="block text-sm font-medium">项目筛选<select v-model="selectedProjectId" class="mt-2 block min-w-[250px] rounded-xl border border-[var(--admin-border)] bg-white px-3 py-2.5 font-normal outline-none focus:border-[var(--admin-accent)]"><option value="">全部项目</option><option v-for="project in projects" :key="project.id" :value="project.id">{{ project.name }} ({{ project.code }})</option></select></label><button class="rounded-xl border border-[var(--admin-border)] px-4 py-2 text-sm hover:bg-[#faf7f1]" @click="loadLogs">刷新</button></div>
    <p v-if="errorMessage" class="mt-4 rounded-xl bg-[#f6e2de] px-4 py-3 text-sm text-[#9b4d42]">{{ errorMessage }}</p>
    <div v-if="loading" class="mt-5 text-sm text-[var(--admin-muted)]">加载中...</div><div v-else-if="logs.length === 0" class="mt-5 rounded-2xl border border-dashed border-[var(--admin-border)] px-4 py-10 text-center text-sm text-[var(--admin-muted)]">当前筛选下没有日志</div><div v-else class="mt-5 space-y-3"><article v-for="log in logs" :key="log.id" class="admin-card rounded-2xl p-4"><div class="flex flex-wrap items-center gap-3"><span class="rounded-full bg-[#f1efe9] px-3 py-1 text-xs text-[var(--admin-muted)]">{{ log.action }}</span><span class="text-sm">{{ log.resource_type }} / {{ log.resource_id }}</span><span class="ml-auto text-xs text-[var(--admin-muted)]">{{ log.created_at }}</span></div><button class="mt-3 text-sm text-[var(--admin-accent)] hover:underline" @click="toggle(log.id)">{{ isExpanded(log.id) ? '收起详情' : '查看详情' }}</button><pre v-if="isExpanded(log.id)" class="mt-3 overflow-auto rounded-xl bg-[#faf7f1] p-3 text-xs">{{ JSON.stringify(log.payload || {}, null, 2) }}</pre></article></div>
  </SectionCard>
</template>

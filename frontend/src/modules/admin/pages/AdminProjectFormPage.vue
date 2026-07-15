<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { httpDelete, httpGet, httpPatch, httpPost } from '@/shared/api/http'
import type { AdminUserSummary, ProjectSummary } from '@/shared/types/admin'
import SectionCard from '@/shared/components/SectionCard.vue'

const route = useRoute()
const router = useRouter()
const projectId = computed(() => typeof route.params.id === 'string' ? route.params.id : '')
const isCreate = computed(() => !projectId.value)
const loading = ref(false)
const saving = ref(false)
const deleting = ref(false)
const showForceDeleteConfirmation = ref(false)
const forceDeleteConfirmation = ref('')
const errorMessage = ref('')
const users = ref<AdminUserSummary[]>([])
const form = reactive({ user_id: '', name: '', code: '', status: 'active' })

async function loadUsers() {
  users.value = (await httpGet<AdminUserSummary[]>('/admin/users')).data
}

async function loadProject() {
  if (isCreate.value) return
  const projects = (await httpGet<ProjectSummary[]>('/admin/projects')).data
  const project = projects.find((item) => item.id === projectId.value)
  if (!project) throw new Error('项目不存在或已被删除。')
  form.user_id = project.user_id ?? ''
  form.name = project.name
  form.code = project.code
  form.status = project.status
}

async function saveProject() {
  if (!form.name.trim()) {
    errorMessage.value = '请输入项目名称。'
    return
  }
  saving.value = true
  errorMessage.value = ''
  try {
    if (isCreate.value) {
      const project = (await httpPost<ProjectSummary>('/admin/projects', { user_id: form.user_id || null, name: form.name.trim(), code: form.code.trim() || null, status: form.status })).data
      await router.replace(`/admin/projects/${project.id}`)
    } else {
      await httpPatch<ProjectSummary>(`/admin/projects/${projectId.value}`, { name: form.name.trim(), code: form.code.trim() || null, status: form.status })
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '保存项目失败。'
  } finally {
    saving.value = false
  }
}

async function deleteProject(force = false) {
  if (force && forceDeleteConfirmation.value !== 'DELETE') return
  if (isCreate.value || !window.confirm(force ? '确认强制删除此项目及全部相册文件？' : '确认删除此项目？项目内存在相册或运行任务时，系统会拒绝删除。')) return
  deleting.value = true
  errorMessage.value = ''
  try {
    await httpDelete(`/admin/projects/${projectId.value}${force ? '?force=true' : ''}`)
    await router.replace('/admin/projects')
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '删除项目失败。'
  } finally {
    deleting.value = false
  }
}

onMounted(async () => {
  loading.value = true
  try { await Promise.all([loadUsers(), loadProject()]) } catch (error) { errorMessage.value = error instanceof Error ? error.message : '加载项目失败。' } finally { loading.value = false }
})
</script>

<template>
  <SectionCard :title="isCreate ? '新建项目' : '编辑项目'" :description="isCreate ? '填写项目基础信息，创建后将进入该项目详情。' : '更新项目的名称、编码和状态。'" eyebrow="Business" tone="admin">
    <router-link to="/admin/projects" class="text-sm text-[var(--admin-accent)] hover:underline">← 返回项目列表</router-link>
    <p v-if="errorMessage" class="mt-4 rounded-xl bg-[#f6e2de] px-4 py-3 text-sm text-[#9b4d42]">{{ errorMessage }}</p>
    <div v-if="loading" class="mt-5 text-sm text-[var(--admin-muted)]">加载中...</div>
    <form v-else class="mt-5 max-w-2xl space-y-4" @submit.prevent="saveProject">
      <label v-if="isCreate" class="block text-sm font-medium">归属用户<select v-model="form.user_id" class="mt-2 w-full rounded-xl border border-[var(--admin-border)] bg-white px-3 py-2.5 font-normal outline-none focus:border-[var(--admin-accent)]"><option value="">不绑定用户</option><option v-for="user in users" :key="user.id" :value="user.id">{{ user.username }} ({{ user.role }})</option></select></label>
      <label class="block text-sm font-medium">项目名称<input v-model="form.name" class="mt-2 w-full rounded-xl border border-[var(--admin-border)] px-3 py-2.5 font-normal outline-none focus:border-[var(--admin-accent)]" /></label>
      <label class="block text-sm font-medium">项目编码<input v-model="form.code" placeholder="留空则自动生成" class="mt-2 w-full rounded-xl border border-[var(--admin-border)] px-3 py-2.5 font-normal outline-none focus:border-[var(--admin-accent)]" /></label>
      <label class="block text-sm font-medium">状态<select v-model="form.status" class="mt-2 w-full rounded-xl border border-[var(--admin-border)] bg-white px-3 py-2.5 font-normal outline-none focus:border-[var(--admin-accent)]"><option value="active">active</option><option value="inactive">inactive</option><option value="archived">archived</option></select></label>
      <div class="flex flex-wrap gap-3"><button class="rounded-xl bg-[var(--admin-accent)] px-5 py-2.5 text-sm text-white disabled:opacity-50" :disabled="saving">{{ saving ? '保存中...' : isCreate ? '创建项目' : '保存修改' }}</button><button v-if="!isCreate" type="button" class="rounded-xl border border-[#d79288] px-5 py-2.5 text-sm text-[#9b4d42] disabled:opacity-50" :disabled="deleting" @click="deleteProject()">{{ deleting ? '删除中...' : '安全删除项目' }}</button><button v-if="!isCreate" type="button" class="rounded-xl bg-[#9b4d42] px-5 py-2.5 text-sm text-white disabled:opacity-50" :disabled="deleting" @click="showForceDeleteConfirmation = !showForceDeleteConfirmation; forceDeleteConfirmation = ''">强制删除全部内容</button></div>
      <div v-if="showForceDeleteConfirmation" class="rounded-2xl border border-[#e5c2bc] bg-[#fbefec] p-4 text-sm text-[#7f3930]"><p class="font-medium">危险操作：将删除该项目中的所有相册、照片、预览和导出文件，无法恢复。</p><label class="mt-3 block">请输入 <code class="font-semibold">DELETE</code> 确认<input v-model="forceDeleteConfirmation" class="mt-2 w-full rounded-xl border border-[#e5c2bc] bg-white px-3 py-2.5 text-[var(--admin-text)] outline-none" autocomplete="off" /></label><div class="mt-3 flex gap-2"><button type="button" class="rounded-xl bg-[#9b4d42] px-4 py-2.5 text-sm text-white disabled:opacity-50" :disabled="forceDeleteConfirmation !== 'DELETE' || deleting" @click="deleteProject(true)">确认强制删除</button><button type="button" class="rounded-xl border border-[#e5c2bc] px-4 py-2.5 text-sm" @click="showForceDeleteConfirmation = false; forceDeleteConfirmation = ''">取消</button></div></div>
    </form>
  </SectionCard>
</template>

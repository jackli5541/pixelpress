<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import SectionCard from '@/shared/components/SectionCard.vue'
import { ApiError, httpGet, httpPatch, httpPost } from '@/shared/api/http'
import type { TaskItem } from '@/shared/types/album'
import type {
  AdminAuditLogItem,
  AdminUserSummary,
  AIConfigSummary,
  AIConfigTestResult,
  ProjectSummary,
} from '@/shared/types/admin'

type AdminTab = 'projects' | 'models' | 'audit-logs' | 'tasks'

const route = useRoute()
const router = useRouter()

const tabLinks: Array<{ key: AdminTab; label: string; to: string }> = [
  { key: 'projects', label: '项目管理', to: '/admin/projects' },
  { key: 'models', label: '模型配置', to: '/admin/models' },
  { key: 'audit-logs', label: '审计日志', to: '/admin/audit-logs' },
  { key: 'tasks', label: '任务列表', to: '/admin/tasks' },
]

const activeTab = computed<AdminTab>(() => {
  if (route.name === 'admin-models') return 'models'
  if (route.name === 'admin-audit-logs') return 'audit-logs'
  if (route.name === 'admin-tasks') return 'tasks'
  return 'projects'
})

const users = ref<AdminUserSummary[]>([])
const projects = ref<ProjectSummary[]>([])
const configs = ref<AIConfigSummary[]>([])
const logs = ref<AdminAuditLogItem[]>([])
const tasks = ref<TaskItem[]>([])
const expandedTaskIds = ref<string[]>([])

const selectedProjectId = ref('')
const selectedConfigId = ref('')
const errorMessage = ref('')
const successMessage = ref('')
const configTestState = ref<{ kind: 'success' | 'error'; message: string; result?: AIConfigTestResult } | null>(null)

const loading = reactive({
  users: false,
  projects: false,
  configs: false,
  logs: false,
  tasks: false,
  createProject: false,
  updateProject: false,
  createConfig: false,
  updateConfig: false,
  testConfig: false,
})

const projectCreateForm = reactive({
  user_id: '',
  name: '',
  code: '',
  status: 'active',
})

const projectEditForm = reactive({
  name: '',
  code: '',
  status: 'active',
})

const configCreateForm = reactive({
  provider_type: 'openai_compatible',
  base_url: '',
  model: '',
  api_key: '',
  is_active: true,
  priority: 100,
  remark: '',
})

const configEditForm = reactive({
  provider_type: 'openai_compatible',
  base_url: '',
  model: '',
  api_key: '',
  is_active: true,
  priority: 100,
  remark: '',
})

const selectedProject = computed(() => projects.value.find((item) => item.id === selectedProjectId.value) ?? null)
const selectedConfig = computed(() => configs.value.find((item) => item.id === selectedConfigId.value) ?? null)

function showError(error: unknown, fallback: string) {
  if (error instanceof ApiError) {
    errorMessage.value = error.detail
    return
  }
  errorMessage.value = error instanceof Error ? error.message : fallback
}

function showSuccess(message: string) {
  successMessage.value = message
  setTimeout(() => {
    if (successMessage.value === message) {
      successMessage.value = ''
    }
  }, 2500)
}

function toggleTaskDetails(taskId: string) {
  if (expandedTaskIds.value.includes(taskId)) {
    expandedTaskIds.value = expandedTaskIds.value.filter((item) => item !== taskId)
    return
  }
  expandedTaskIds.value = [...expandedTaskIds.value, taskId]
}

function isTaskExpanded(taskId: string) {
  return expandedTaskIds.value.includes(taskId)
}

function syncProjectEditor(project: ProjectSummary | null) {
  projectEditForm.name = project?.name ?? ''
  projectEditForm.code = project?.code ?? ''
  projectEditForm.status = project?.status ?? 'active'
}

function syncConfigEditor(config: AIConfigSummary | null) {
  configEditForm.provider_type = config?.provider_type ?? 'openai_compatible'
  configEditForm.base_url = config?.base_url ?? ''
  configEditForm.model = config?.model ?? ''
  configEditForm.api_key = ''
  configEditForm.is_active = config?.is_active ?? true
  configEditForm.priority = config?.priority ?? 100
  configEditForm.remark = config?.remark ?? ''
}

async function runLoad<T>(key: keyof typeof loading, action: () => Promise<T>, onSuccess: (result: T) => void, fallback: string) {
  loading[key] = true
  try {
    const result = await action()
    onSuccess(result)
  } catch (error) {
    showError(error, fallback)
  } finally {
    loading[key] = false
  }
}

async function loadUsers() {
  await runLoad('users', () => httpGet<AdminUserSummary[]>('/admin/users'), (response) => {
    users.value = response.data
  }, '加载用户失败。')
}

async function loadProjects() {
  errorMessage.value = ''
  await runLoad('projects', () => httpGet<ProjectSummary[]>('/admin/projects'), (response) => {
    projects.value = response.data
    if (!selectedProjectId.value && response.data.length > 0) {
      selectedProjectId.value = response.data[0].id
    } else if (selectedProjectId.value && !response.data.some((item) => item.id === selectedProjectId.value)) {
      selectedProjectId.value = response.data[0]?.id ?? ''
    }
  }, '加载项目失败。')
}

async function loadConfigs(projectId = selectedProjectId.value) {
  if (!projectId) {
    configs.value = []
    selectedConfigId.value = ''
    return
  }
  await runLoad('configs', () => httpGet<AIConfigSummary[]>(`/admin/projects/${projectId}/ai-configs`), (response) => {
    configs.value = response.data
    if (!selectedConfigId.value && response.data.length > 0) {
      selectedConfigId.value = response.data[0].id
    } else if (selectedConfigId.value && !response.data.some((item) => item.id === selectedConfigId.value)) {
      selectedConfigId.value = response.data[0]?.id ?? ''
    }
  }, '加载模型配置失败。')
}

async function loadLogs(projectId = selectedProjectId.value) {
  const query = projectId ? `?project_id=${encodeURIComponent(projectId)}` : ''
  await runLoad('logs', () => httpGet<AdminAuditLogItem[]>(`/admin/audit-logs${query}`), (response) => {
    logs.value = response.data
  }, '加载审计日志失败。')
}

async function loadTasks() {
  await runLoad('tasks', () => httpGet<TaskItem[]>('/tasks'), (response) => {
    tasks.value = response.data
  }, '加载任务失败。')
}

async function createProject() {
  if (!projectCreateForm.name.trim()) {
    errorMessage.value = '请输入项目名称。'
    return
  }
  loading.createProject = true
  errorMessage.value = ''
  try {
    await httpPost<ProjectSummary>('/admin/projects', {
      user_id: projectCreateForm.user_id || null,
      name: projectCreateForm.name.trim(),
      code: projectCreateForm.code.trim() || null,
      status: projectCreateForm.status,
    })
    projectCreateForm.user_id = ''
    projectCreateForm.name = ''
    projectCreateForm.code = ''
    projectCreateForm.status = 'active'
    await loadProjects()
    await loadLogs()
    showSuccess('项目已创建。')
  } catch (error) {
    showError(error, '创建项目失败。')
  } finally {
    loading.createProject = false
  }
}

async function updateProject() {
  if (!selectedProject.value) return
  loading.updateProject = true
  errorMessage.value = ''
  try {
    await httpPatch<ProjectSummary>(`/admin/projects/${selectedProject.value.id}`, {
      name: projectEditForm.name.trim(),
      code: projectEditForm.code.trim() || null,
      status: projectEditForm.status,
    })
    await loadProjects()
    await loadLogs()
    showSuccess('项目已更新。')
  } catch (error) {
    showError(error, '更新项目失败。')
  } finally {
    loading.updateProject = false
  }
}

async function createConfig() {
  if (!selectedProjectId.value) {
    errorMessage.value = '请先选择项目。'
    return
  }
  if (!configCreateForm.model.trim() || !configCreateForm.api_key.trim()) {
    errorMessage.value = '模型名称和 API Key 不能为空。'
    return
  }
  loading.createConfig = true
  errorMessage.value = ''
  try {
    await httpPost<AIConfigSummary>(`/admin/projects/${selectedProjectId.value}/ai-configs`, {
      provider_type: configCreateForm.provider_type,
      base_url: configCreateForm.base_url.trim() || null,
      model: configCreateForm.model.trim(),
      api_key: configCreateForm.api_key.trim(),
      is_active: configCreateForm.is_active,
      priority: configCreateForm.priority,
      remark: configCreateForm.remark.trim() || null,
    })
    configCreateForm.base_url = ''
    configCreateForm.model = ''
    configCreateForm.api_key = ''
    configCreateForm.is_active = true
    configCreateForm.priority = 100
    configCreateForm.remark = ''
    await loadConfigs()
    await loadLogs()
    showSuccess('模型配置已创建。')
  } catch (error) {
    showError(error, '创建模型配置失败。')
  } finally {
    loading.createConfig = false
  }
}

async function updateConfig(nextActive?: boolean) {
  if (!selectedConfig.value) return
  loading.updateConfig = true
  errorMessage.value = ''
  try {
    await httpPatch<AIConfigSummary>(`/admin/ai-configs/${selectedConfig.value.id}`, {
      provider_type: configEditForm.provider_type,
      base_url: configEditForm.base_url.trim() || null,
      model: configEditForm.model.trim(),
      api_key: configEditForm.api_key.trim() || undefined,
      is_active: nextActive ?? configEditForm.is_active,
      priority: configEditForm.priority,
      remark: configEditForm.remark.trim() || null,
    })
    await loadConfigs()
    await loadLogs()
    showSuccess('模型配置已更新。')
  } catch (error) {
    showError(error, '更新模型配置失败。')
  } finally {
    loading.updateConfig = false
  }
}

async function testConfig() {
  if (!selectedConfig.value) return
  loading.testConfig = true
  configTestState.value = null
  errorMessage.value = ''
  try {
    const response = await httpPost<AIConfigTestResult>(`/admin/ai-configs/${selectedConfig.value.id}/test`)
    configTestState.value = {
      kind: 'success',
      message: '配置测试成功。',
      result: response.data,
    }
    await loadLogs()
  } catch (error) {
    const detail = error instanceof ApiError ? error.detail : error instanceof Error ? error.message : '测试失败。'
    configTestState.value = {
      kind: 'error',
      message: detail,
      result: selectedConfig.value
        ? {
            config_id: selectedConfig.value.id,
            provider: selectedConfig.value.provider_type,
            model: selectedConfig.value.model,
            source: 'project_config',
            debug: null,
            payload: null,
          }
        : undefined,
    }
    showError(error, '测试失败。')
  } finally {
    loading.testConfig = false
  }
}

async function ensureTabData(tab: AdminTab) {
  if (projects.value.length === 0 && !loading.projects) {
    await loadProjects()
  }
  if (tab === 'projects' && users.value.length === 0 && !loading.users) {
    await loadUsers()
  }
  if (tab === 'models') {
    await loadConfigs()
  }
  if (tab === 'audit-logs') {
    await loadLogs()
  }
  if (tab === 'tasks') {
    await loadTasks()
  }
}

watch(selectedProject, (project) => {
  syncProjectEditor(project)
})

watch(selectedConfig, (config) => {
  syncConfigEditor(config)
})

watch(selectedProjectId, async () => {
  if (activeTab.value === 'models') {
    await loadConfigs()
  }
  if (activeTab.value === 'audit-logs') {
    await loadLogs()
  }
})

watch(activeTab, async (tab) => {
  await ensureTabData(tab)
})

onMounted(async () => {
  await loadProjects()
  await ensureTabData(activeTab.value)
})
</script>

<template>
  <div class="space-y-6 text-[var(--admin-text)]">
    <SectionCard
      title="后台管理"
      description="保持简单、有序。先选项目，再维护模型配置、查看日志或检查任务状态。"
      eyebrow="Admin"
      tone="admin"
    >
      <div class="flex flex-wrap gap-2">
        <button
          v-for="tab in tabLinks"
          :key="tab.key"
          class="rounded-full px-4 py-2 text-sm transition"
          :class="activeTab === tab.key ? 'bg-[var(--admin-accent)] text-white' : 'border border-[var(--admin-border)] text-[var(--admin-muted)] hover:bg-white'"
          @click="router.push(tab.to)"
        >
          {{ tab.label }}
        </button>
      </div>

      <div class="mt-5 flex flex-wrap items-center gap-3 rounded-[20px] bg-[#faf7f1] px-4 py-3">
        <label class="text-sm font-medium text-[var(--admin-text)]">当前项目</label>
        <select
          v-model="selectedProjectId"
          class="min-w-[260px] rounded-xl border border-[var(--admin-border)] bg-white px-3 py-2 text-sm outline-none focus:border-[var(--admin-accent)]"
        >
          <option v-for="project in projects" :key="project.id" :value="project.id">
            {{ project.name }} ({{ project.code }})
          </option>
        </select>
        <span v-if="selectedProject" class="text-xs text-[var(--admin-muted)]">
          归属：{{ selectedProject.username || '未绑定用户' }} | 状态：{{ selectedProject.status }}
        </span>
      </div>

      <p v-if="successMessage" class="mt-4 rounded-[16px] bg-[#e5f0e1] px-4 py-3 text-sm text-[#4b6f49]">{{ successMessage }}</p>
      <p v-if="errorMessage" class="mt-3 rounded-[16px] bg-[#f6e2de] px-4 py-3 text-sm text-[#9b4d42]">{{ errorMessage }}</p>
    </SectionCard>

    <template v-if="activeTab === 'projects'">
      <SectionCard title="项目管理" description="左侧选择项目，右侧查看并编辑。新建项目放在独立区域，不与当前编辑混在一起。" tone="admin">
        <div class="grid gap-5 lg:grid-cols-[320px_1fr]">
          <div class="space-y-2">
            <div v-if="loading.projects" class="text-sm text-[var(--admin-muted)]">加载中...</div>
            <div v-else-if="projects.length === 0" class="rounded-[20px] border border-dashed border-[var(--admin-border)] px-4 py-8 text-center text-sm text-[var(--admin-muted)]">
              暂无项目
            </div>
            <button
              v-for="project in projects"
              :key="project.id"
              class="w-full rounded-[20px] border px-4 py-4 text-left transition"
              :class="selectedProjectId === project.id ? 'border-[var(--admin-accent)] bg-[#f4f8f8]' : 'border-[var(--admin-border)] bg-white hover:bg-[#fcfbf8]'"
              @click="selectedProjectId = project.id"
            >
              <p class="text-sm font-semibold text-[var(--admin-text)]">{{ project.name }}</p>
              <p class="mt-1 text-xs text-[var(--admin-muted)]">{{ project.code }} | {{ project.username || '未绑定用户' }}</p>
            </button>
          </div>

          <div class="grid gap-5 xl:grid-cols-2">
            <div class="admin-card rounded-[24px] p-5">
              <p class="text-sm font-semibold text-[var(--admin-text)]">新建项目</p>
              <div class="mt-4 space-y-3">
                <select v-model="projectCreateForm.user_id" class="w-full rounded-xl border border-[var(--admin-border)] px-3 py-2 text-sm outline-none focus:border-[var(--admin-accent)]">
                  <option value="">不绑定用户</option>
                  <option v-for="user in users" :key="user.id" :value="user.id">{{ user.username }} ({{ user.role }})</option>
                </select>
                <input v-model="projectCreateForm.name" type="text" placeholder="项目名称" class="w-full rounded-xl border border-[var(--admin-border)] px-3 py-2 text-sm outline-none focus:border-[var(--admin-accent)]" />
                <input v-model="projectCreateForm.code" type="text" placeholder="项目编码，可留空自动生成" class="w-full rounded-xl border border-[var(--admin-border)] px-3 py-2 text-sm outline-none focus:border-[var(--admin-accent)]" />
                <select v-model="projectCreateForm.status" class="w-full rounded-xl border border-[var(--admin-border)] px-3 py-2 text-sm outline-none focus:border-[var(--admin-accent)]">
                  <option value="active">active</option>
                  <option value="inactive">inactive</option>
                  <option value="archived">archived</option>
                </select>
                <button class="w-full rounded-xl bg-[var(--admin-accent)] px-4 py-2.5 text-sm text-white hover:brightness-110 disabled:opacity-50" :disabled="loading.createProject" @click="createProject">
                  {{ loading.createProject ? '创建中...' : '创建项目' }}
                </button>
              </div>
            </div>

            <div class="admin-card rounded-[24px] p-5">
              <p class="text-sm font-semibold text-[var(--admin-text)]">编辑当前项目</p>
              <div v-if="selectedProject" class="mt-4 space-y-3">
                <input v-model="projectEditForm.name" type="text" placeholder="项目名称" class="w-full rounded-xl border border-[var(--admin-border)] px-3 py-2 text-sm outline-none focus:border-[var(--admin-accent)]" />
                <input v-model="projectEditForm.code" type="text" placeholder="项目编码" class="w-full rounded-xl border border-[var(--admin-border)] px-3 py-2 text-sm outline-none focus:border-[var(--admin-accent)]" />
                <select v-model="projectEditForm.status" class="w-full rounded-xl border border-[var(--admin-border)] px-3 py-2 text-sm outline-none focus:border-[var(--admin-accent)]">
                  <option value="active">active</option>
                  <option value="inactive">inactive</option>
                  <option value="archived">archived</option>
                </select>
                <button class="w-full rounded-xl border border-[var(--admin-border)] px-4 py-2.5 text-sm text-[var(--admin-text)] hover:bg-[#faf7f1] disabled:opacity-50" :disabled="loading.updateProject" @click="updateProject">
                  {{ loading.updateProject ? '保存中...' : '保存修改' }}
                </button>
              </div>
              <div v-else class="mt-4 rounded-[20px] border border-dashed border-[var(--admin-border)] px-4 py-8 text-center text-sm text-[var(--admin-muted)]">
                请先从左侧选择项目
              </div>
            </div>
          </div>
        </div>
      </SectionCard>
    </template>

    <template v-else-if="activeTab === 'models'">
      <SectionCard title="模型配置" description="配置区保持低密度：左侧看列表，右侧做编辑和测试，不把太多信息挤在一个地方。" tone="admin">
        <div class="grid gap-5 lg:grid-cols-[320px_1fr]">
          <div class="space-y-2">
            <div v-if="loading.configs" class="text-sm text-[var(--admin-muted)]">加载中...</div>
            <div v-else-if="configs.length === 0" class="rounded-[20px] border border-dashed border-[var(--admin-border)] px-4 py-8 text-center text-sm text-[var(--admin-muted)]">
              当前项目还没有模型配置
            </div>
            <button
              v-for="config in configs"
              :key="config.id"
              class="w-full rounded-[20px] border px-4 py-4 text-left transition"
              :class="selectedConfigId === config.id ? 'border-[var(--admin-accent)] bg-[#f4f8f8]' : 'border-[var(--admin-border)] bg-white hover:bg-[#fcfbf8]'"
              @click="selectedConfigId = config.id"
            >
              <div class="flex items-center justify-between gap-3">
                <p class="text-sm font-semibold text-[var(--admin-text)]">{{ config.model }}</p>
                <span class="rounded-full px-2.5 py-1 text-[11px]" :class="config.is_active ? 'bg-[#e5f0e1] text-[#4b6f49]' : 'bg-[#f1efe9] text-[#6c6a64]'">
                  {{ config.is_active ? 'active' : 'inactive' }}
                </span>
              </div>
              <p class="mt-1 text-xs text-[var(--admin-muted)]">{{ config.provider_type }} | priority {{ config.priority }}</p>
            </button>
          </div>

          <div class="space-y-5">
            <div class="grid gap-5 xl:grid-cols-2">
              <div class="admin-card rounded-[24px] p-5">
                <p class="text-sm font-semibold text-[var(--admin-text)]">新增配置</p>
                <div class="mt-4 space-y-3">
                  <input v-model="configCreateForm.provider_type" type="text" placeholder="provider_type" class="w-full rounded-xl border border-[var(--admin-border)] px-3 py-2 text-sm outline-none focus:border-[var(--admin-accent)]" />
                  <input v-model="configCreateForm.base_url" type="text" placeholder="base_url，例如 https://api.openai.com/v1" class="w-full rounded-xl border border-[var(--admin-border)] px-3 py-2 text-sm outline-none focus:border-[var(--admin-accent)]" />
                  <input v-model="configCreateForm.model" type="text" placeholder="模型名" class="w-full rounded-xl border border-[var(--admin-border)] px-3 py-2 text-sm outline-none focus:border-[var(--admin-accent)]" />
                  <input v-model="configCreateForm.api_key" type="password" placeholder="API Key" class="w-full rounded-xl border border-[var(--admin-border)] px-3 py-2 text-sm outline-none focus:border-[var(--admin-accent)]" />
                  <input v-model.number="configCreateForm.priority" type="number" min="0" class="w-full rounded-xl border border-[var(--admin-border)] px-3 py-2 text-sm outline-none focus:border-[var(--admin-accent)]" />
                  <input v-model="configCreateForm.remark" type="text" placeholder="备注" class="w-full rounded-xl border border-[var(--admin-border)] px-3 py-2 text-sm outline-none focus:border-[var(--admin-accent)]" />
                  <label class="flex items-center gap-2 text-sm text-[var(--admin-muted)]">
                    <input v-model="configCreateForm.is_active" type="checkbox" class="rounded border-[var(--admin-border)]" />
                    创建后立即启用
                  </label>
                  <button class="w-full rounded-xl bg-[var(--admin-accent)] px-4 py-2.5 text-sm text-white hover:brightness-110 disabled:opacity-50" :disabled="loading.createConfig" @click="createConfig">
                    {{ loading.createConfig ? '创建中...' : '创建配置' }}
                  </button>
                </div>
              </div>

              <div class="admin-card rounded-[24px] p-5">
                <p class="text-sm font-semibold text-[var(--admin-text)]">编辑当前配置</p>
                <div v-if="selectedConfig" class="mt-4 space-y-3">
                  <input v-model="configEditForm.provider_type" type="text" class="w-full rounded-xl border border-[var(--admin-border)] px-3 py-2 text-sm outline-none focus:border-[var(--admin-accent)]" />
                  <input v-model="configEditForm.base_url" type="text" class="w-full rounded-xl border border-[var(--admin-border)] px-3 py-2 text-sm outline-none focus:border-[var(--admin-accent)]" />
                  <input v-model="configEditForm.model" type="text" class="w-full rounded-xl border border-[var(--admin-border)] px-3 py-2 text-sm outline-none focus:border-[var(--admin-accent)]" />
                  <input v-model="configEditForm.api_key" type="password" placeholder="留空则不修改 API Key" class="w-full rounded-xl border border-[var(--admin-border)] px-3 py-2 text-sm outline-none focus:border-[var(--admin-accent)]" />
                  <input v-model.number="configEditForm.priority" type="number" min="0" class="w-full rounded-xl border border-[var(--admin-border)] px-3 py-2 text-sm outline-none focus:border-[var(--admin-accent)]" />
                  <input v-model="configEditForm.remark" type="text" class="w-full rounded-xl border border-[var(--admin-border)] px-3 py-2 text-sm outline-none focus:border-[var(--admin-accent)]" />
                  <label class="flex items-center gap-2 text-sm text-[var(--admin-muted)]">
                    <input v-model="configEditForm.is_active" type="checkbox" class="rounded border-[var(--admin-border)]" />
                    启用此配置
                  </label>
                  <div class="flex flex-wrap gap-2">
                    <button class="rounded-xl border border-[var(--admin-border)] px-4 py-2.5 text-sm text-[var(--admin-text)] hover:bg-[#faf7f1] disabled:opacity-50" :disabled="loading.updateConfig" @click="updateConfig()">
                      {{ loading.updateConfig ? '保存中...' : '保存修改' }}
                    </button>
                    <button class="rounded-xl border border-[#b7d1bd] bg-[#edf6eb] px-4 py-2.5 text-sm text-[#4b6f49] hover:brightness-95 disabled:opacity-50" :disabled="loading.updateConfig" @click="updateConfig(true)">
                      设为启用
                    </button>
                    <button class="rounded-xl border border-[var(--admin-border)] px-4 py-2.5 text-sm text-[var(--admin-text)] hover:bg-[#faf7f1] disabled:opacity-50" :disabled="loading.updateConfig" @click="updateConfig(false)">
                      停用
                    </button>
                    <button class="rounded-xl bg-[var(--admin-text)] px-4 py-2.5 text-sm text-white hover:brightness-110 disabled:opacity-50" :disabled="loading.testConfig" @click="testConfig">
                      {{ loading.testConfig ? '测试中...' : '测试配置' }}
                    </button>
                  </div>
                  <p class="text-xs text-[var(--admin-muted)]">当前 Key：{{ selectedConfig.api_key_masked }}</p>
                </div>
                <div v-else class="mt-4 rounded-[20px] border border-dashed border-[var(--admin-border)] px-4 py-8 text-center text-sm text-[var(--admin-muted)]">
                  请先从左侧选择配置
                </div>
              </div>
            </div>

            <div v-if="configTestState" class="rounded-[22px] border px-4 py-4" :class="configTestState.kind === 'success' ? 'border-[#b7d1bd] bg-[#edf6eb]' : 'border-[#e5c2bc] bg-[#fbefec]'">
              <div class="flex flex-wrap items-center gap-3">
                <span class="rounded-full px-3 py-1 text-xs font-medium" :class="configTestState.kind === 'success' ? 'bg-[#d8ead6] text-[#4b6f49]' : 'bg-[#f4d8d2] text-[#9b4d42]'">
                  {{ configTestState.kind === 'success' ? '成功' : '失败' }}
                </span>
                <span class="text-sm text-[var(--admin-text)]">模型：{{ configTestState.result?.model || '-' }}</span>
                <span class="text-sm text-[var(--admin-text)]">Provider：{{ configTestState.result?.provider || '-' }}</span>
              </div>
              <p class="mt-3 text-sm text-[var(--admin-text)]">{{ configTestState.message }}</p>
              <pre v-if="configTestState.result?.payload" class="mt-3 overflow-auto rounded-xl bg-white/80 p-3 text-xs text-[var(--admin-text)]">{{ JSON.stringify(configTestState.result.payload, null, 2) }}</pre>
            </div>
          </div>
        </div>
      </SectionCard>
    </template>

    <template v-else-if="activeTab === 'audit-logs'">
      <SectionCard title="审计日志" description="按当前项目查看后台操作记录，重点是清楚地知道谁在什么时候改了什么。" tone="admin">
        <div v-if="loading.logs" class="text-sm text-[var(--admin-muted)]">加载中...</div>
        <div v-else-if="logs.length === 0" class="rounded-[20px] border border-dashed border-[var(--admin-border)] px-4 py-8 text-center text-sm text-[var(--admin-muted)]">
          当前筛选下没有日志
        </div>
        <div v-else class="space-y-3">
          <article v-for="log in logs" :key="log.id" class="admin-card rounded-[22px] px-4 py-4">
            <div class="flex flex-wrap items-center gap-3">
              <span class="rounded-full bg-[#f1efe9] px-3 py-1 text-xs text-[var(--admin-muted)]">{{ log.action }}</span>
              <span class="text-sm text-[var(--admin-text)]">{{ log.resource_type }} / {{ log.resource_id }}</span>
              <span class="ml-auto text-xs text-[var(--admin-muted)]">{{ log.created_at }}</span>
            </div>
            <pre class="mt-3 overflow-auto rounded-xl bg-[#faf7f1] p-3 text-xs text-[var(--admin-text)]">{{ JSON.stringify(log.payload || {}, null, 2) }}</pre>
          </article>
        </div>
      </SectionCard>
    </template>

    <template v-else>
      <SectionCard title="任务列表" description="管理员可在这里查看任务阶段、失败原因和关键 debug/metrics 摘要；原始容器日志仍只在 Docker/Sentry 中查看。" tone="admin">
        <div v-if="loading.tasks" class="text-sm text-[var(--admin-muted)]">加载中...</div>
        <div v-else-if="tasks.length === 0" class="rounded-[20px] border border-dashed border-[var(--admin-border)] px-4 py-8 text-center text-sm text-[var(--admin-muted)]">
          暂无任务
        </div>
        <div v-else class="space-y-3">
          <article v-for="task in tasks" :key="task.id" class="admin-card rounded-[22px] px-4 py-4">
            <div class="flex flex-wrap items-center gap-3">
              <p class="text-sm font-medium text-[var(--admin-text)]">{{ task.task_type }}</p>
              <span class="rounded-full px-3 py-1 text-xs" :class="task.task_status === 'succeeded' ? 'bg-[#e5f0e1] text-[#4b6f49]' : task.task_status === 'failed' ? 'bg-[#f6e2de] text-[#9b4d42]' : 'bg-[#f1efe9] text-[#6c6a64]'">
                {{ task.task_status }}
              </span>
              <span v-if="task.pipeline_name" class="rounded-full bg-[#f1efe9] px-3 py-1 text-xs text-[var(--admin-muted)]">{{ task.pipeline_name }}</span>
              <span class="ml-auto text-xs text-[var(--admin-muted)]">{{ task.created_at }}</span>
            </div>
            <div class="mt-2 space-y-1 text-xs text-[var(--admin-muted)]">
              <p>任务 ID：{{ task.id }}</p>
              <p>请求号：{{ task.request_id || '—' }}</p>
              <p>关联相册：{{ task.album_id || '—' }} | Worker：{{ task.worker_name || '—' }}</p>
              <p>阶段：{{ task.progress_step || '—' }} | 尝试：{{ task.attempt_count ?? 0 }} / {{ task.max_attempts ?? 0 }}</p>
              <p v-if="task.provider">Provider：{{ task.provider }}{{ task.model ? ` / ${task.model}` : '' }}</p>
              <p v-if="task.error_code || task.error_message">错误：{{ task.error_code || '—' }} / {{ task.error_message || '—' }}</p>
              <p v-if="task.debug_payload && typeof task.debug_payload === 'object'">说明：{{ task.debug_payload.stage || '—' }} / {{ task.debug_payload.reason || '—' }}</p>
              <p v-if="task.metrics_payload && typeof task.metrics_payload === 'object'">
                耗时：{{ task.metrics_payload.duration_ms ?? '—' }} ms
                <span v-if="task.metrics_payload.photo_count != null"> | 照片 {{ task.metrics_payload.photo_count }}</span>
                <span v-if="task.metrics_payload.chapter_count != null"> | 章节 {{ task.metrics_payload.chapter_count }}</span>
                <span v-if="task.metrics_payload.page_count != null"> | 页面 {{ task.metrics_payload.page_count }}</span>
              </p>
            </div>
            <button class="mt-3 rounded-xl border border-[var(--admin-border)] px-3 py-1.5 text-xs text-[var(--admin-text)] hover:bg-[#faf7f1]" @click="toggleTaskDetails(task.id)">
              {{ isTaskExpanded(task.id) ? '收起详情' : '展开详情' }}
            </button>
            <div v-if="isTaskExpanded(task.id)" class="mt-3 grid gap-3 xl:grid-cols-3">
              <pre class="overflow-auto rounded-xl bg-[#faf7f1] p-3 text-xs text-[var(--admin-text)]">{{ JSON.stringify(task.debug_payload || {}, null, 2) }}</pre>
              <pre class="overflow-auto rounded-xl bg-[#faf7f1] p-3 text-xs text-[var(--admin-text)]">{{ JSON.stringify(task.metrics_payload || {}, null, 2) }}</pre>
              <pre class="overflow-auto rounded-xl bg-[#faf7f1] p-3 text-xs text-[var(--admin-text)]">{{ JSON.stringify(task.result_payload || {}, null, 2) }}</pre>
            </div>
          </article>
        </div>
      </SectionCard>
    </template>
  </div>
</template>

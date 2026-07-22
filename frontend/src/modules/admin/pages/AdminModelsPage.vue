<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ApiError, httpGet, httpPatch, httpPost } from '@/shared/api/http'
import type { AIConfigSummary, AIConfigTestResult, DefaultAIConfigSummary, ProjectSummary } from '@/shared/types/admin'
import SectionCard from '@/shared/components/SectionCard.vue'
import DefaultAIConfigCard from '@/modules/admin/components/DefaultAIConfigCard.vue'

const projects = ref<ProjectSummary[]>([])
const selectedProjectId = ref('')
const configs = ref<AIConfigSummary[]>([])
const selectedConfigId = ref('')
const loading = ref(false)
const saving = ref(false)
const testing = ref(false)
const errorMessage = ref('')
const testResult = ref<{ ok: boolean; message: string; data?: AIConfigTestResult } | null>(null)
const defaultConfigs = ref<DefaultAIConfigSummary[]>([])
const form = reactive({ stage: 'chapter' as 'chapter' | 'chapter_embedding' | 'layout', provider_type: 'openai_compatible', base_url: '', model: '', api_key: '', is_active: true, priority: 100, remark: '' })

const defaultConfigLabels = {
  chapter: { title: '章节分析', description: '用于提取匿名场景属性并生成章节名称。' },
  chapter_embedding: { title: '章节视觉向量', description: '用于照片内容相似度与事件边界判断。' },
  layout: { title: '排版规划', description: '用于页面规划与排版。' },
} as const

const selectedConfig = computed(() => configs.value.find((item) => item.id === selectedConfigId.value) ?? null)
const isCreating = computed(() => !selectedConfig.value)

function resetForm(config: AIConfigSummary | null = null) {
  form.stage = config?.stage ?? 'chapter'
  form.provider_type = config?.provider_type ?? 'openai_compatible'
  form.base_url = config?.base_url ?? ''
  form.model = config?.model ?? ''
  form.api_key = ''
  form.is_active = config?.is_active ?? true
  form.priority = config?.priority ?? 100
  form.remark = config?.remark ?? ''
  testResult.value = null
}

async function loadConfigs() {
  configs.value = []
  selectedConfigId.value = ''
  resetForm()
  if (!selectedProjectId.value) return
  loading.value = true
  errorMessage.value = ''
  try {
    configs.value = (await httpGet<AIConfigSummary[]>(`/admin/projects/${selectedProjectId.value}/ai-configs`)).data
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '加载模型配置失败。'
  } finally {
    loading.value = false
  }
}

async function loadDefaultConfigs() {
  try {
    defaultConfigs.value = (await httpGet<DefaultAIConfigSummary[]>('/admin/ai-default-configs')).data
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '加载默认配置失败。'
  }
}

function selectConfig(id: string) {
  selectedConfigId.value = id
  resetForm(configs.value.find((item) => item.id === id) ?? null)
}

async function saveConfig(nextActive?: boolean) {
  if (!selectedProjectId.value || !form.model.trim() || (isCreating.value && !form.api_key.trim())) {
    errorMessage.value = '请选择项目，并填写模型名称和 API Key。'
    return
  }
  saving.value = true
  errorMessage.value = ''
  try {
    const payload = {
      stage: form.stage,
      provider_type: form.provider_type,
      base_url: form.base_url.trim() || null,
      model: form.model.trim(),
      api_key: form.api_key.trim() || undefined,
      is_active: nextActive ?? form.is_active,
      priority: form.priority,
      remark: form.remark.trim() || null,
    }
    if (isCreating.value) {
      const created = (await httpPost<AIConfigSummary>(`/admin/projects/${selectedProjectId.value}/ai-configs`, { ...payload, api_key: form.api_key.trim() })).data
      await loadConfigs()
      selectConfig(created.id)
    } else {
      const configId = selectedConfig.value.id
      await httpPatch<AIConfigSummary>(`/admin/ai-configs/${configId}`, payload)
      await loadConfigs()
      selectConfig(configId)
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '保存模型配置失败。'
  } finally {
    saving.value = false
  }
}

async function testConfig() {
  if (!selectedConfig.value) return
  testing.value = true
  testResult.value = null
  try {
    const data = (await httpPost<AIConfigTestResult>(`/admin/ai-configs/${selectedConfig.value.id}/test`)).data
    testResult.value = { ok: true, message: '配置测试成功。', data }
  } catch (error) {
    testResult.value = { ok: false, message: error instanceof ApiError ? error.detail : error instanceof Error ? error.message : '配置测试失败。' }
  } finally {
    testing.value = false
  }
}

watch(selectedProjectId, () => void loadConfigs())
onMounted(async () => {
  try {
    await loadDefaultConfigs()
    projects.value = (await httpGet<ProjectSummary[]>('/admin/projects')).data
    selectedProjectId.value = projects.value[0]?.id ?? ''
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '加载项目失败。'
  }
})
</script>

<template>
  <SectionCard title="模型配置" description="先选择项目，再管理该项目的模型配置与连接测试。" eyebrow="Operations" tone="admin">
    <p v-if="errorMessage" class="rounded-xl bg-[#f6e2de] px-4 py-3 text-sm text-[#9b4d42]">{{ errorMessage }}</p>

    <div class="mb-8 rounded-2xl bg-[#faf7f1] p-4"><div><h2 class="font-medium text-[var(--admin-text)]">默认运行时配置</h2><p class="mt-1 text-sm text-[var(--admin-muted)]">未设置项目专属配置时，任务会使用此处的阶段默认配置。</p></div><div class="mt-4 grid gap-4 xl:grid-cols-2"><DefaultAIConfigCard v-for="config in defaultConfigs" :key="config.stage" :config="config" :title="defaultConfigLabels[config.stage].title" :description="defaultConfigLabels[config.stage].description" @updated="loadDefaultConfigs" /></div></div>

    <div class="border-t border-[var(--admin-border)] pt-6">
    <h2 class="font-medium text-[var(--admin-text)]">项目专属覆盖配置</h2>
    <p class="mt-1 text-sm text-[var(--admin-muted)]">项目配置优先于默认运行时配置。</p>

    <label class="mt-5 block max-w-md text-sm font-medium">
      所属项目
      <select v-model="selectedProjectId" class="mt-2 w-full rounded-xl border border-[var(--admin-border)] bg-white px-3 py-2.5 font-normal outline-none focus:border-[var(--admin-accent)]">
        <option value="" disabled>请选择项目</option>
        <option v-for="project in projects" :key="project.id" :value="project.id">{{ project.name }} ({{ project.code }})</option>
      </select>
    </label>

    <div class="mt-6 grid gap-5 lg:grid-cols-[300px_minmax(0,1fr)]">
      <div class="space-y-2">
        <button class="w-full rounded-xl border border-dashed border-[var(--admin-border)] px-4 py-3 text-left text-sm text-[var(--admin-accent)] hover:bg-[#faf7f1]" @click="selectedConfigId = ''; resetForm()">+ 新增配置</button>
        <p v-if="loading" class="text-sm text-[var(--admin-muted)]">加载中...</p>
        <button v-for="config in configs" :key="config.id" class="w-full rounded-xl border px-4 py-3 text-left" :class="selectedConfigId === config.id ? 'border-[var(--admin-accent)] bg-[#f4f8f8]' : 'border-[var(--admin-border)] bg-white hover:bg-[#faf7f1]'" @click="selectConfig(config.id)">
          <div class="flex items-center justify-between gap-2">
            <span class="font-medium">{{ config.model }}</span>
            <span class="text-xs" :class="config.is_active ? 'text-[#4b6f49]' : 'text-[var(--admin-muted)]'">{{ config.is_active ? '启用' : '停用' }}</span>
          </div>
          <p class="mt-1 text-xs text-[var(--admin-muted)]">{{ config.provider_type }} · 优先级 {{ config.priority }}</p>
        </button>
      </div>

      <form class="admin-card rounded-2xl p-5" @submit.prevent="() => saveConfig()">
        <div class="flex items-center justify-between gap-3"><h2 class="font-medium">{{ isCreating ? '新增配置' : '编辑配置' }}</h2><span v-if="selectedConfig" class="text-xs text-[var(--admin-muted)]">Key：{{ selectedConfig.api_key_masked }}</span></div>
        <div class="mt-4 grid gap-3 md:grid-cols-2">
          <select v-model="form.stage" class="rounded-xl border border-[var(--admin-border)] px-3 py-2.5 text-sm outline-none focus:border-[var(--admin-accent)]"><option value="chapter">章节生成</option><option value="chapter_embedding">图片嵌入</option><option value="layout">版式规划</option></select>
          <input v-model="form.provider_type" placeholder="Provider 类型" class="rounded-xl border border-[var(--admin-border)] px-3 py-2.5 text-sm outline-none focus:border-[var(--admin-accent)]" />
          <input v-model="form.model" placeholder="模型名称" class="rounded-xl border border-[var(--admin-border)] px-3 py-2.5 text-sm outline-none focus:border-[var(--admin-accent)]" />
          <input v-model="form.base_url" placeholder="Base URL（可选）" class="rounded-xl border border-[var(--admin-border)] px-3 py-2.5 text-sm outline-none focus:border-[var(--admin-accent)] md:col-span-2" />
          <input v-model="form.api_key" type="password" :placeholder="isCreating ? 'API Key' : '留空则不修改 API Key'" class="rounded-xl border border-[var(--admin-border)] px-3 py-2.5 text-sm outline-none focus:border-[var(--admin-accent)] md:col-span-2" />
          <input v-model.number="form.priority" type="number" min="0" class="rounded-xl border border-[var(--admin-border)] px-3 py-2.5 text-sm outline-none focus:border-[var(--admin-accent)]" />
          <input v-model="form.remark" placeholder="备注（可选）" class="rounded-xl border border-[var(--admin-border)] px-3 py-2.5 text-sm outline-none focus:border-[var(--admin-accent)]" />
        </div>
        <label class="mt-4 flex items-center gap-2 text-sm"><input v-model="form.is_active" type="checkbox" /> 启用此配置</label>
        <div class="mt-5 flex flex-wrap gap-2">
          <button class="rounded-xl bg-[var(--admin-accent)] px-4 py-2.5 text-sm text-white disabled:opacity-50" :disabled="saving">{{ saving ? '保存中...' : '保存配置' }}</button>
          <template v-if="selectedConfig">
            <button type="button" class="rounded-xl border border-[#b7d1bd] bg-[#edf6eb] px-4 py-2.5 text-sm text-[#4b6f49]" :disabled="saving" @click="saveConfig(true)">设为启用</button>
            <button type="button" class="rounded-xl border border-[var(--admin-border)] px-4 py-2.5 text-sm" :disabled="saving" @click="saveConfig(false)">停用</button>
            <button type="button" class="rounded-xl bg-[var(--admin-text)] px-4 py-2.5 text-sm text-white disabled:opacity-50" :disabled="testing" @click="testConfig">{{ testing ? '测试中...' : '测试配置' }}</button>
          </template>
        </div>
        <div v-if="testResult" class="mt-5 rounded-xl border p-4 text-sm" :class="testResult.ok ? 'border-[#b7d1bd] bg-[#edf6eb]' : 'border-[#e5c2bc] bg-[#fbefec]'">
          {{ testResult.message }}
          <pre v-if="testResult.data?.payload" class="mt-3 overflow-auto rounded-lg bg-white/70 p-3 text-xs">{{ JSON.stringify(testResult.data.payload, null, 2) }}</pre>
        </div>
      </form>
    </div>
    </div>
  </SectionCard>
</template>

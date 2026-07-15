<script setup lang="ts">
import { reactive, ref, watch } from 'vue'
import { ApiError, httpPatch, httpPost } from '@/shared/api/http'
import type { AIConfigTestResult, DefaultAIConfigSummary } from '@/shared/types/admin'

const props = defineProps<{ config: DefaultAIConfigSummary; title: string; description: string }>()
const emit = defineEmits<{ (e: 'updated'): void }>()
const saving = ref(false)
const testing = ref(false)
const message = ref('')
const form = reactive({ provider_type: '', base_url: '', model: '', api_key: '', is_active: true, priority: 100, remark: '' })

function sync() {
  form.provider_type = props.config.provider_type
  form.base_url = props.config.base_url ?? ''
  form.model = props.config.model
  form.api_key = ''
  form.is_active = props.config.is_active
  form.priority = props.config.priority
  form.remark = props.config.remark ?? ''
}

async function save() {
  saving.value = true
  message.value = ''
  try {
    await httpPatch(`/admin/ai-default-configs/${props.config.stage}`, { ...form, base_url: form.base_url.trim() || null, api_key: form.api_key.trim() || undefined, remark: form.remark.trim() || null })
    message.value = '已保存。'
    emit('updated')
  } catch (error) { message.value = error instanceof Error ? error.message : '保存失败。' } finally { saving.value = false }
}

async function testConfig() {
  testing.value = true
  message.value = ''
  try {
    const result = (await httpPost<AIConfigTestResult>(`/admin/ai-default-configs/${props.config.stage}/test`)).data
    message.value = `测试成功：${result.model}`
  } catch (error) { message.value = error instanceof ApiError ? error.detail : error instanceof Error ? error.message : '测试失败。' } finally { testing.value = false }
}

watch(() => props.config, sync, { immediate: true })
</script>

<template>
  <form class="admin-card rounded-2xl p-5" @submit.prevent="save">
    <div class="flex items-start justify-between gap-3"><div><h2 class="font-medium">{{ title }}</h2><p class="mt-1 text-xs text-[var(--admin-muted)]">{{ description }}</p></div><span class="text-xs text-[var(--admin-muted)]">Key：{{ config.api_key_masked || '未设置' }}</span></div>
    <div class="mt-4 grid gap-3 md:grid-cols-2"><input v-model="form.provider_type" placeholder="Provider 类型" class="rounded-xl border border-[var(--admin-border)] px-3 py-2.5 text-sm" /><input v-model="form.model" placeholder="模型名称" class="rounded-xl border border-[var(--admin-border)] px-3 py-2.5 text-sm" /><input v-model="form.base_url" placeholder="Base URL（可选）" class="rounded-xl border border-[var(--admin-border)] px-3 py-2.5 text-sm md:col-span-2" /><input v-model="form.api_key" type="password" placeholder="留空则保留现有 API Key" class="rounded-xl border border-[var(--admin-border)] px-3 py-2.5 text-sm md:col-span-2" /><input v-model.number="form.priority" type="number" min="0" class="rounded-xl border border-[var(--admin-border)] px-3 py-2.5 text-sm" /><input v-model="form.remark" placeholder="备注（可选）" class="rounded-xl border border-[var(--admin-border)] px-3 py-2.5 text-sm" /></div>
    <label class="mt-4 flex items-center gap-2 text-sm"><input v-model="form.is_active" type="checkbox" /> 启用此默认配置</label><p v-if="message" class="mt-3 text-sm text-[var(--admin-muted)]">{{ message }}</p><div class="mt-4 flex gap-2"><button class="rounded-xl bg-[var(--admin-accent)] px-4 py-2.5 text-sm text-white disabled:opacity-50" :disabled="saving">{{ saving ? '保存中...' : '保存' }}</button><button type="button" class="rounded-xl border border-[var(--admin-border)] px-4 py-2.5 text-sm disabled:opacity-50" :disabled="testing" @click="testConfig">{{ testing ? '测试中...' : '测试' }}</button></div>
  </form>
</template>

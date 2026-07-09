<script setup lang="ts">
import { computed } from 'vue'
import type { TaskItem } from '@/shared/types/album'

const props = defineProps<{
  task: TaskItem | null
  title?: string
  runningHint?: string
  emptyText?: string
}>()

const statusClass = computed(() => {
  const status = props.task?.task_status
  if (status === 'running' || status === 'queued') {
    return 'bg-[rgba(203,143,57,0.18)] text-[var(--story-gold-soft)]'
  }
  if (status === 'succeeded') {
    return 'bg-[#dcead5] text-[#47673d]'
  }
  if (status === 'failed' || status === 'cancelled') {
    return 'bg-[#f6d9d3] text-[#8b4339]'
  }
  return 'bg-[rgba(43,31,24,0.08)] text-[#5f5347]'
})

const summaryLines = computed(() => {
  const task = props.task
  if (!task) return []

  const lines: string[] = []
  const resultPayload = task.result_payload ?? {}
  const debugPayload = task.debug_payload ?? {}
  const metricsPayload = task.metrics_payload ?? {}
  const summary = typeof resultPayload.summary === 'object' && resultPayload.summary ? resultPayload.summary as Record<string, unknown> : null

  if (summary) {
    const total = summary.total
    const keep = summary.keep
    const remove = summary.remove
    if (typeof total === 'number') {
      lines.push(`总计 ${total} 张${typeof keep === 'number' ? `，保留 ${keep}` : ''}${typeof remove === 'number' ? `，移除 ${remove}` : ''}`)
    }
    const duplicateGroups = summary.duplicate_groups
    if (typeof duplicateGroups === 'number') {
      lines.push(`重复组 ${duplicateGroups}`)
    }
  }

  const pageCount = resultPayload.page_count
  if (typeof pageCount === 'number') {
    lines.push(`生成 ${pageCount} 页`)
  }

  const exportFormat = resultPayload.format
  if (typeof exportFormat === 'string') {
    lines.push(`导出格式：${exportFormat.toUpperCase()}`)
  }

  const durationMs = metricsPayload.duration_ms
  if (typeof durationMs === 'number') {
    lines.push(`耗时：${durationMs} ms`)
  }

  const warnings = Array.isArray(resultPayload.warnings) ? resultPayload.warnings.filter((item): item is string => typeof item === 'string' && item.length > 0) : []
  if (warnings.length > 0) {
    lines.push(`提示：${warnings.join('；')}`)
  }

  if (typeof task.error_code === 'string' && task.error_code) {
    lines.push(`错误码：${task.error_code}`)
  }

  if (typeof task.progress_step === 'string' && task.progress_step) {
    lines.push(`任务阶段：${task.progress_step}`)
  }

  if (typeof task.provider === 'string' && task.provider) {
    lines.push(`Provider：${task.provider}${task.model ? ` / ${task.model}` : ''}`)
  }

  if (debugPayload && typeof debugPayload === 'object') {
    if (typeof debugPayload.stage === 'string' && debugPayload.stage) {
      lines.push(`失败阶段：${debugPayload.stage}`)
    }
    if (typeof debugPayload.reason === 'string' && debugPayload.reason) {
      lines.push(`说明：${debugPayload.reason}`)
    }
    if (debugPayload.fallback_used === true) {
      lines.push('已自动回退到规则流程')
    }
  }

  if (typeof task.request_id === 'string' && task.request_id) {
    lines.push(`请求号：${task.request_id}`)
  }

  return lines.slice(0, 6)
})
</script>

<template>
  <div class="rounded-[18px] border border-[rgba(224,177,106,0.18)] bg-[rgba(255,255,255,0.04)] px-4 py-3 text-sm text-[var(--story-text)]">
    <template v-if="task">
      <div class="flex flex-wrap items-center gap-3">
        <span class="rounded-full px-3 py-1 text-xs" :class="statusClass">
          {{ task.task_status }}
        </span>
        <span>{{ title || task.task_type }}</span>
        <span v-if="task.updated_at" class="text-xs text-[var(--story-faint)]">{{ task.updated_at }}</span>
      </div>
      <p
        v-if="(task.task_status === 'running' || task.task_status === 'queued') && runningHint"
        class="mt-2 text-xs text-[var(--story-faint)]"
      >
        {{ runningHint }}
      </p>
      <p v-else-if="task.error_message" class="mt-2 text-xs text-[#8b4339]">
        {{ task.error_message }}
      </p>
      <ul v-if="summaryLines.length > 0" class="mt-2 space-y-1 text-xs text-[var(--story-faint)]">
        <li v-for="line in summaryLines" :key="line">{{ line }}</li>
      </ul>
    </template>
    <p v-else class="text-xs text-[var(--story-faint)]">
      {{ emptyText || '当前还没有任务记录。' }}
    </p>
  </div>
</template>

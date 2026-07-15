<script setup lang="ts">
import type { ProjectSummary } from '@/shared/types/admin'

defineProps<{ project: ProjectSummary | null }>()
</script>

<template>
  <div class="paper-panel rounded-[24px] p-5">
    <p class="text-xs uppercase tracking-[0.24em] text-[#8e6d45]">Project Binding</p>
    <p class="font-story mt-3 text-3xl text-[#2a211a]">{{ project?.name || '当前项目' }}</p>
    <p class="mt-3 text-sm leading-7 text-[#5f5347]">相册归属于当前项目；项目名称和删除由后台管理员统一管理。</p>
    <div class="mt-5 rounded-[20px] bg-white/70 px-4 py-4"><p class="text-sm text-[#3f342b]">项目编码</p><p class="mt-1 text-lg font-medium text-[#1f1712]">{{ project?.code || '-' }}</p></div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { httpGet } from '@/shared/api/http'
import { getAlbumResumeRoute } from '@/shared/workflow/albumWorkflow'
import type { AlbumCard } from '@/shared/types/album'

const route = useRoute()
const router = useRouter()
const errorMessage = ref('')

async function loadAlbumAndRedirect() {
  const id = typeof route.params.id === 'string' ? route.params.id : ''
  if (!id) {
    await router.replace('/')
    return
  }

  try {
    const response = await httpGet<AlbumCard>(`/albums/${id}`)
    const album = response.data
    const target = album.resume_route || getAlbumResumeRoute(album.id, album.status)
    if (router.currentRoute.value.fullPath !== target) {
      await router.replace(target)
    }
  } catch (error: any) {
    errorMessage.value = error.message || '恢复相册失败，请稍后重试。'
    window.setTimeout(() => {
      void router.replace('/')
    }, 1200)
  }
}

onMounted(() => {
  void loadAlbumAndRedirect()
})
</script>

<template>
  <div class="story-panel rounded-[28px] px-6 py-10 text-center">
    <p class="font-story text-3xl text-[var(--story-gold-soft)]">正在恢复你的创作进度...</p>
    <p class="mt-3 text-sm text-[var(--story-muted)]">
      {{ errorMessage || '系统会根据上次完成的步骤自动带你回到对应页面。' }}
    </p>
  </div>
</template>

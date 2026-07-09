<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { getAccessToken, resolveApiUrl } from '@/shared/api/http'

const props = defineProps<{
  src: string
  alt?: string
  className?: string
}>()

const blobUrl = ref('')
const loading = ref(false)
const failed = ref(false)

async function loadImage() {
  if (!props.src) return
  loading.value = true
  failed.value = false
  try {
    const token = getAccessToken()
    const response = await fetch(resolveApiUrl(props.src), {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
    if (!response.ok) throw new Error(`image request failed: ${response.status}`)
    const blob = await response.blob()
    if (blobUrl.value) URL.revokeObjectURL(blobUrl.value)
    blobUrl.value = URL.createObjectURL(blob)
  } catch {
    failed.value = true
  } finally {
    loading.value = false
  }
}

watch(() => props.src, () => { void loadImage() })
onMounted(() => { void loadImage() })
onBeforeUnmount(() => { if (blobUrl.value) URL.revokeObjectURL(blobUrl.value) })
</script>

<template>
  <div v-if="loading" :class="props.className" class="flex items-center justify-center bg-slate-100 text-[10px] text-slate-400">加载中</div>
  <div v-else-if="failed || !blobUrl" :class="props.className" class="flex items-center justify-center bg-slate-100 text-[10px] text-slate-400">图片</div>
  <img v-else :src="blobUrl" :alt="alt || ''" :class="props.className" />
</template>

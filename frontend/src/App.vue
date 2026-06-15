<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()

const currentAlbumId = computed(() => {
  const id = route.params.id
  return typeof id === 'string' ? id : ''
})

const navLinks = [
  { label: '项目列表', to: () => '/' },
  { label: '管理后台', to: () => '/admin/tasks' },
]
</script>

<template>
  <div class="min-h-screen bg-slate-50 text-slate-800">
    <header class="border-b border-slate-200 bg-white/90 backdrop-blur sticky top-0 z-40">
      <div class="mx-auto max-w-7xl px-4 py-3 lg:px-8">
        <div class="flex items-center justify-between">
          <div class="flex items-center gap-4">
            <router-link to="/" class="flex items-center gap-2">
              <span class="text-lg font-bold tracking-tight text-slate-900">Pixpress1</span>
              <span class="hidden sm:inline text-xs uppercase tracking-[0.2em] text-cyan-600">相册排版</span>
            </router-link>
          </div>
          <nav class="flex items-center gap-2">
            <router-link
              v-for="link in navLinks" :key="link.label"
              :to="link.to()" custom
              v-slot="{ href, navigate, isActive }">
              <a :href="href"
                class="rounded-full px-4 py-2 text-sm transition"
                :class="isActive
                  ? 'bg-slate-900 text-white'
                  : 'text-slate-600 hover:bg-slate-100'"
                @click="navigate">{{ link.label }}</a>
            </router-link>
          </nav>
        </div>
      </div>
    </header>

    <main class="mx-auto max-w-7xl px-4 py-6 lg:px-8">
      <router-view />
    </main>
  </div>
</template>

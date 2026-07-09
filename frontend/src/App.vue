<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { currentUser, loadCurrentUser, logout } from '@/shared/auth'

const route = useRoute()
const router = useRouter()

const isAdminRoute = computed(() => route.path.startsWith('/admin'))

const navLinks = computed(() => {
  const links = [{ label: '故事项目', to: '/' }]
  if (currentUser.value?.role === 'admin') {
    links.push({ label: '后台管理', to: '/admin/projects' })
  }
  return links
})

function getLoginTarget() {
  return route.fullPath.startsWith('/') ? route.fullPath : '/'
}

function goToLogin() {
  void router.push({ name: 'login', query: { redirect: getLoginTarget() } })
}

function handleLogout() {
  logout()
  void router.push({ name: 'login' })
}

onMounted(() => {
  void loadCurrentUser()
})
</script>

<template>
  <div :class="isAdminRoute ? 'admin-shell min-h-screen' : 'story-shell min-h-screen'">
    <header
      class="sticky top-0 z-40 border-b backdrop-blur"
      :class="
        isAdminRoute
          ? 'border-[var(--admin-border)] bg-[rgba(246,242,235,0.92)] text-[var(--admin-text)]'
          : 'border-[rgba(203,143,57,0.22)] bg-[rgba(43,25,16,0.82)] text-[var(--story-text)]'
      "
    >
      <div class="mx-auto max-w-7xl px-4 py-3 lg:px-8">
        <div class="flex items-center justify-between gap-4">
          <router-link to="/" class="flex items-center gap-3">
            <div class="h-10 w-1 rounded-full" :class="isAdminRoute ? 'bg-[var(--admin-accent)]' : 'bg-[var(--story-gold)]'" />
            <div>
              <p class="font-story text-2xl leading-none" :class="isAdminRoute ? 'text-[var(--admin-text)]' : 'text-[var(--story-gold-soft)]'">
                Pixpress1
              </p>
              <p class="mt-1 text-[11px] uppercase tracking-[0.28em]" :class="isAdminRoute ? 'text-[var(--admin-muted)]' : 'text-[var(--story-faint)]'">
                {{ isAdminRoute ? 'Admin Console' : 'Cinematic Storybook' }}
              </p>
            </div>
          </router-link>

          <nav class="flex items-center gap-2">
            <router-link
              v-for="link in navLinks"
              :key="link.label"
              :to="link.to"
              custom
              v-slot="{ href, navigate, isActive }"
            >
              <a
                :href="href"
                class="rounded-full px-4 py-2 text-sm transition"
                :class="
                  isActive
                    ? isAdminRoute
                      ? 'bg-[var(--admin-accent)] text-white'
                      : 'bg-[rgba(203,143,57,0.18)] text-[var(--story-gold-soft)]'
                    : isAdminRoute
                      ? 'text-[var(--admin-muted)] hover:bg-white'
                      : 'text-[var(--story-muted)] hover:bg-[rgba(255,255,255,0.05)]'
                "
                @click="navigate"
              >
                {{ link.label }}
              </a>
            </router-link>

            <template v-if="currentUser">
              <span class="ml-2 hidden text-xs sm:inline" :class="isAdminRoute ? 'text-[var(--admin-muted)]' : 'text-[var(--story-muted)]'">
                {{ currentUser.username }} | {{ currentUser.role }}
              </span>
              <button
                class="rounded-full border px-4 py-2 text-sm transition"
                :class="
                  isAdminRoute
                    ? 'border-[var(--admin-border)] text-[var(--admin-text)] hover:bg-white'
                    : 'border-[rgba(203,143,57,0.26)] text-[var(--story-text)] hover:bg-[rgba(255,255,255,0.05)]'
                "
                @click="handleLogout"
              >
                退出
              </button>
            </template>

            <button
              v-else
              class="rounded-full px-5 py-2 text-sm font-medium transition"
              :class="
                isAdminRoute
                  ? 'bg-[var(--admin-accent)] text-white hover:brightness-110'
                  : 'story-button'
              "
              @click="goToLogin"
            >
              登录
            </button>
          </nav>
        </div>
      </div>
    </header>

    <main class="mx-auto max-w-7xl px-4 py-6 lg:px-8 lg:py-8">
      <router-view />
    </main>
  </div>
</template>

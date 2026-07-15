<script setup lang="ts">
import { ref } from 'vue'

const mobileOpen = ref(false)

const groups = [
  { label: '业务管理', links: [{ label: '项目管理', to: '/admin/projects' }] },
  {
    label: '系统运维',
    links: [
      { label: '模型配置', to: '/admin/models' },
      { label: '任务监控', to: '/admin/tasks' },
      { label: '操作日志', to: '/admin/audit-logs' },
    ],
  },
]
</script>

<template>
  <div class="lg:grid lg:grid-cols-[220px_minmax(0,1fr)] lg:gap-8">
    <button
      class="mb-4 flex w-full items-center justify-between rounded-2xl border border-[var(--admin-border)] bg-white px-4 py-3 text-sm font-medium lg:hidden"
      @click="mobileOpen = !mobileOpen"
    >
      后台导航
      <span>{{ mobileOpen ? '收起' : '展开' }}</span>
    </button>

    <aside :class="mobileOpen ? 'block' : 'hidden'" class="mb-6 lg:sticky lg:top-24 lg:block lg:h-fit">
      <nav class="admin-card rounded-[24px] p-3" aria-label="后台管理导航">
        <div v-for="group in groups" :key="group.label" class="px-2 py-3 first:pt-2">
          <p class="mb-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--admin-muted)]">{{ group.label }}</p>
          <div class="space-y-1">
            <router-link
              v-for="link in group.links"
              :key="link.to"
              :to="link.to"
              class="block rounded-xl px-3 py-2.5 text-sm text-[var(--admin-muted)] transition hover:bg-white"
              active-class="bg-[var(--admin-accent)] text-white"
              @click="mobileOpen = false"
            >
              {{ link.label }}
            </router-link>
          </div>
        </div>
      </nav>
    </aside>

    <router-view />
  </div>
</template>

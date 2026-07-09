<script setup lang="ts">
defineProps<{
  title: string
  description: string
  tone?: 'default' | 'accent' | 'film' | 'admin'
  eyebrow?: string
}>()
</script>

<template>
  <section
    class="rounded-[28px] p-6 md:p-7"
    :class="
      tone === 'film'
        ? 'story-panel text-[var(--story-text)]'
        : tone === 'admin'
          ? 'admin-card text-[var(--admin-text)]'
          : tone === 'accent'
            ? 'paper-panel ring-1 ring-[rgba(203,143,57,0.22)]'
            : 'paper-panel'
    "
  >
    <p
      v-if="eyebrow"
      class="text-[11px] uppercase tracking-[0.24em]"
      :class="tone === 'film' ? 'text-[var(--story-gold-soft)]' : 'text-[#9a6a2f]'"
    >
      {{ eyebrow }}
    </p>
    <h3
      class="font-story mt-2 text-3xl tracking-tight"
      :class="tone === 'film' ? 'text-[var(--story-text)]' : 'text-[#261d17]'"
    >
      {{ title }}
    </h3>
    <p
      class="mt-3 max-w-3xl text-sm leading-7"
      :class="tone === 'film' ? 'text-[var(--story-muted)]' : 'text-[#5f5347]'"
    >
      {{ description }}
    </p>
    <div class="mt-6">
      <slot />
    </div>
  </section>
</template>

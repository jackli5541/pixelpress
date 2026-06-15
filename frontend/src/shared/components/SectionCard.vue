<script setup lang="ts">
defineProps<{
  title: string
  description: string
  tone?: 'default' | 'accent'
  eyebrow?: string
}>()
</script>

<template>
  <section
    class="rounded-3xl border bg-white p-6 shadow-sm"
    :class="
      tone === 'accent'
        ? 'border-cyan-200 ring-1 ring-cyan-500/10'
        : 'border-slate-200'
    "
  >
    <p v-if="eyebrow" class="text-[11px] uppercase tracking-[0.24em] text-cyan-500">{{ eyebrow }}</p>
    <h3 class="mt-1 text-xl font-semibold tracking-tight text-slate-900">{{ title }}</h3>
    <p class="mt-2 max-w-3xl text-sm leading-6 text-slate-500">{{ description }}</p>
    <div class="mt-4">
      <slot />
    </div>
  </section>
</template>

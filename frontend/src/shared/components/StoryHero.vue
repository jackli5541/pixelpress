<script setup lang="ts">
defineProps<{
  eyebrow?: string
  title: string
  description: string
  align?: 'left' | 'center'
}>()
</script>

<template>
  <section class="story-panel-strong film-frame overflow-hidden rounded-[32px] px-6 py-8 md:px-10 md:py-12">
    <div :class="align === 'center' ? 'mx-auto max-w-4xl text-center' : 'max-w-4xl'">
      <p v-if="eyebrow" class="font-story text-sm uppercase tracking-[0.34em] text-[var(--story-gold-soft)]">
        {{ eyebrow }}
      </p>
      <h1 class="font-story mt-4 text-4xl leading-none text-[var(--story-text)] md:text-6xl lg:text-7xl">
        {{ title }}
      </h1>
      <p class="mt-4 max-w-3xl text-sm leading-7 text-[var(--story-muted)] md:text-base">
        {{ description }}
      </p>
      <div class="mt-8">
        <slot />
      </div>
    </div>
  </section>
</template>

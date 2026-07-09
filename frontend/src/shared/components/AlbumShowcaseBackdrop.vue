<script setup lang="ts">
defineProps<{
  mode?: 'hero' | 'editorial'
}>()
</script>

<template>
  <div
    class="pointer-events-none absolute inset-0 overflow-hidden rounded-[32px]"
    :class="mode === 'editorial' ? 'opacity-80' : 'opacity-100'"
    aria-hidden="true"
  >
    <div class="absolute inset-0 bg-[radial-gradient(circle_at_16%_22%,rgba(203,143,57,0.22),transparent_18%),radial-gradient(circle_at_82%_18%,rgba(125,69,35,0.26),transparent_16%),linear-gradient(180deg,rgba(18,13,10,0.12),rgba(18,13,10,0.5))]" />

    <div
      class="absolute left-[-4%] top-[9%] h-[68%] w-[36%] rounded-[50%] bg-[radial-gradient(circle,rgba(201,132,49,0.24),rgba(201,132,49,0.08)_44%,transparent_68%)] blur-[1px]"
    />
    <div
      class="absolute bottom-[-12%] right-[-6%] h-[46%] w-[34%] rounded-[50%] bg-[radial-gradient(circle,rgba(166,92,43,0.20),rgba(166,92,43,0.08)_42%,transparent_70%)]"
    />

    <div class="absolute right-[8%] top-[12%] h-[16%] w-[12%] rounded-[28px] border border-[rgba(224,177,106,0.12)] bg-[rgba(255,255,255,0.03)] shadow-[0_28px_50px_rgba(0,0,0,0.2)]" />
    <div class="absolute right-[10%] top-[15%] h-[10%] w-[8%] rounded-[999px] bg-[radial-gradient(circle,rgba(248,227,191,0.18),rgba(248,227,191,0.02)_58%,transparent_72%)]" />

    <div
      class="absolute left-[10%] top-[16%] h-[54%] w-[32%] rotate-[-7deg] rounded-[28px] border border-[rgba(255,241,220,0.12)] bg-[linear-gradient(180deg,rgba(250,244,233,0.96),rgba(238,222,193,0.95))] shadow-[0_32px_58px_rgba(0,0,0,0.26)]"
    >
      <div class="absolute inset-x-[8%] top-[8%] h-[42%] rounded-[18px] border border-[rgba(120,86,53,0.14)] bg-[linear-gradient(135deg,#d6b58a,#8e5f34_58%,#4f3323)]" />
      <div class="absolute inset-x-[8%] top-[55%] grid h-[22%] grid-cols-3 gap-3">
        <div class="rounded-[12px] border border-[rgba(120,86,53,0.12)] bg-[linear-gradient(145deg,#cfab7c,#6e432b)]" />
        <div class="rounded-[12px] border border-[rgba(120,86,53,0.12)] bg-[linear-gradient(145deg,#dbc59b,#8e6039)]" />
        <div class="rounded-[12px] border border-[rgba(120,86,53,0.12)] bg-[linear-gradient(145deg,#bc8d57,#50301f)]" />
      </div>
      <div class="absolute bottom-[8%] left-[8%] right-[8%] h-[8%] rounded-full bg-[rgba(91,64,42,0.10)]" />
    </div>

    <div
      class="absolute left-[36%] top-[11%] h-[58%] w-[40%] rotate-[3deg] rounded-[30px] border border-[rgba(224,177,106,0.14)] bg-[rgba(25,17,13,0.78)] shadow-[0_34px_62px_rgba(0,0,0,0.30)] backdrop-blur-[4px]"
    >
      <div class="absolute inset-x-[7%] top-[8%] h-[8%] rounded-full bg-[rgba(224,177,106,0.10)]" />
      <div class="absolute inset-x-[7%] top-[20%] grid h-[46%] grid-cols-[0.9fr_1.1fr] gap-4">
        <div class="rounded-[18px] border border-[rgba(224,177,106,0.12)] bg-[linear-gradient(145deg,#4d2f21,#160f0b)]" />
        <div class="rounded-[18px] border border-[rgba(224,177,106,0.12)] bg-[linear-gradient(145deg,#2d2018,#6d452d)]" />
      </div>
      <div class="absolute inset-x-[7%] top-[72%] flex items-center justify-between">
        <span class="font-story text-3xl text-[rgba(240,220,187,0.84)]">Chapter I</span>
        <span class="text-xs uppercase tracking-[0.24em] text-[rgba(203,178,145,0.66)]">Story Layout</span>
      </div>
      <div class="absolute inset-x-[7%] top-[82%] h-[7%] rounded-full bg-[rgba(255,255,255,0.06)]" />
    </div>

    <div
      class="absolute bottom-[9%] right-[11%] h-[30%] w-[22%] rotate-[8deg] overflow-hidden rounded-[24px] border border-[rgba(224,177,106,0.16)] bg-[rgba(255,255,255,0.06)] shadow-[0_24px_42px_rgba(0,0,0,0.25)]"
    >
      <div class="absolute inset-[10%] rounded-[16px] bg-[linear-gradient(155deg,#caa16d,#5b3726_58%,#1d120c)]" />
      <div class="absolute left-[12%] top-[10%] right-[12%] flex justify-between text-[9px] uppercase tracking-[0.22em] text-[rgba(255,245,226,0.64)]">
        <span>Contact</span>
        <span>Roll 03</span>
      </div>
      <div class="absolute inset-y-[10%] left-[6%] w-[4%] rounded-full bg-[linear-gradient(180deg,rgba(255,240,215,0.55),rgba(255,240,215,0.15))]" />
      <div class="absolute inset-y-[10%] right-[6%] w-[4%] rounded-full bg-[linear-gradient(180deg,rgba(255,240,215,0.55),rgba(255,240,215,0.15))]" />
    </div>

    <div
      v-if="mode !== 'editorial'"
      class="absolute bottom-[12%] left-[46%] h-[12%] w-[32%] rounded-[999px] bg-[linear-gradient(180deg,rgba(255,255,255,0.08),rgba(255,255,255,0.03))]"
    />
  </div>
</template>

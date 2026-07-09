<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import SectionCard from '@/shared/components/SectionCard.vue'
import StoryHero from '@/shared/components/StoryHero.vue'
import AlbumShowcaseBackdrop from '@/shared/components/AlbumShowcaseBackdrop.vue'
import { authLoading, currentUser, login, register } from '@/shared/auth'

const route = useRoute()
const router = useRouter()

const authMode = ref<'login' | 'register'>('login')
const authForm = reactive({ username: '', password: '' })
const authError = ref('')
const authSuccess = ref('')

const redirectTarget = computed(() => {
  const redirect = route.query.redirect
  return typeof redirect === 'string' && redirect.startsWith('/') ? redirect : '/'
})

watch(
  () => currentUser.value,
  (user) => {
    if (user) {
      void router.replace(redirectTarget.value)
    }
  },
  { immediate: true },
)

async function submitAuth() {
  authError.value = ''
  authSuccess.value = ''

  if (!authForm.username.trim() || !authForm.password.trim()) {
    authError.value = '请输入用户名和密码。'
    return
  }

  try {
    if (authMode.value === 'register') {
      await register(authForm.username.trim(), authForm.password)
      authSuccess.value = '注册成功，请使用新账号登录。'
      authMode.value = 'login'
      authForm.password = ''
      return
    }

    await login(authForm.username.trim(), authForm.password)
    await router.replace(redirectTarget.value)
  } catch (error) {
    authError.value = error instanceof Error ? error.message : '认证失败。'
  }
}
</script>

<template>
  <div class="space-y-6">
    <div class="relative overflow-hidden rounded-[32px]">
      <AlbumShowcaseBackdrop mode="hero" />
      <StoryHero
        eyebrow="Welcome Back"
        title="把照片剪辑成一本会讲故事的相册"
        description="登录后继续你的故事项目：从素材整理、镜头筛选，到章节成形、书页编排与最终导出。"
      >
        <div class="grid gap-4 text-left md:grid-cols-3">
          <div class="story-panel rounded-[24px] px-4 py-4">
            <p class="font-story text-3xl text-[var(--story-gold-soft)]">01</p>
            <p class="mt-2 text-sm text-[var(--story-text)]">整理素材</p>
            <p class="mt-1 text-xs text-[var(--story-muted)]">上传照片并归档到你的项目。</p>
          </div>
          <div class="story-panel rounded-[24px] px-4 py-4">
            <p class="font-story text-3xl text-[var(--story-gold-soft)]">02</p>
            <p class="mt-2 text-sm text-[var(--story-text)]">塑造故事</p>
            <p class="mt-1 text-xs text-[var(--story-muted)]">筛选镜头、划分章节、编排叙事节奏。</p>
          </div>
          <div class="story-panel rounded-[24px] px-4 py-4">
            <p class="font-story text-3xl text-[var(--story-gold-soft)]">03</p>
            <p class="mt-2 text-sm text-[var(--story-text)]">导出成册</p>
            <p class="mt-1 text-xs text-[var(--story-muted)]">预览成品后导出 HTML 或 PDF。</p>
          </div>
        </div>
      </StoryHero>
    </div>

    <div class="grid gap-6 lg:grid-cols-[1.1fr_0.9fr]">
      <SectionCard
        title="故事入口"
        description="用户侧不追求 AI 炫技，而是更像一本电影化的相册编辑器。这里保留简洁的身份认证入口。"
        tone="film"
        eyebrow="Access"
      >
        <div class="grid gap-4 md:grid-cols-2">
          <div class="rounded-[24px] border border-[rgba(224,177,106,0.18)] bg-[rgba(255,255,255,0.03)] p-5">
            <p class="font-story text-3xl text-[var(--story-gold-soft)]">Project</p>
            <p class="mt-3 text-sm text-[var(--story-muted)]">
              为每一本相册绑定项目，让模型配置、审计记录与作品流程都有明确归属。
            </p>
          </div>
          <div class="rounded-[24px] border border-[rgba(224,177,106,0.18)] bg-[rgba(255,255,255,0.03)] p-5">
            <p class="font-story text-3xl text-[var(--story-gold-soft)]">Narrative</p>
            <p class="mt-3 text-sm text-[var(--story-muted)]">
              从镜头筛选到章节编排，都围绕“故事感”来组织，而不是纯文件管理。
            </p>
          </div>
        </div>
      </SectionCard>

      <SectionCard
        title="登录 Pixpress1"
        :description="authMode === 'login' ? '登录后继续当前项目和故事流程。' : '注册普通账号后即可开始创建故事书。'"
        tone="accent"
        eyebrow="Account"
      >
        <div class="space-y-5">
          <div class="flex flex-wrap items-center gap-2">
            <button
              class="rounded-full px-4 py-2 text-sm transition"
              :class="authMode === 'login' ? 'bg-[#2b1f18] text-[var(--story-paper-soft)]' : 'bg-[rgba(43,31,24,0.08)] text-[#5f5347] hover:bg-[rgba(43,31,24,0.12)]'"
              @click="authMode = 'login'"
            >
              登录
            </button>
            <button
              class="rounded-full px-4 py-2 text-sm transition"
              :class="authMode === 'register' ? 'bg-[#2b1f18] text-[var(--story-paper-soft)]' : 'bg-[rgba(43,31,24,0.08)] text-[#5f5347] hover:bg-[rgba(43,31,24,0.12)]'"
              @click="authMode = 'register'"
            >
              注册
            </button>
            <span v-if="route.query.redirect" class="text-xs text-[#7e6e60]">登录后将返回原页面。</span>
          </div>

          <div class="grid gap-4">
            <label class="space-y-2">
              <span class="text-sm font-medium text-[#3f342b]">用户名</span>
              <input
                v-model="authForm.username"
                type="text"
                autocomplete="username"
                placeholder="请输入用户名"
                class="w-full rounded-[20px] border border-[rgba(79,59,42,0.14)] bg-white/70 px-4 py-3 text-sm text-[#231b16] outline-none transition focus:border-[var(--story-gold)]"
              />
            </label>
            <label class="space-y-2">
              <span class="text-sm font-medium text-[#3f342b]">密码</span>
              <input
                v-model="authForm.password"
                type="password"
                autocomplete="current-password"
                placeholder="请输入密码"
                class="w-full rounded-[20px] border border-[rgba(79,59,42,0.14)] bg-white/70 px-4 py-3 text-sm text-[#231b16] outline-none transition focus:border-[var(--story-gold)]"
                @keyup.enter="submitAuth"
              />
            </label>
          </div>

          <div class="flex flex-wrap items-center gap-3">
            <button class="story-button px-6 py-3 text-sm" :disabled="authLoading" @click="submitAuth">
              {{ authLoading ? '处理中...' : authMode === 'login' ? '进入故事项目' : '创建账号' }}
            </button>
            <router-link to="/" class="story-button-secondary px-5 py-3 text-sm !text-[#2e241d] !bg-[rgba(43,31,24,0.08)]">
              返回首页
            </router-link>
          </div>

          <p v-if="authError" class="rounded-[18px] bg-[#f7d7d3] px-4 py-3 text-sm text-[#8a433a]">{{ authError }}</p>
          <p v-if="authSuccess" class="rounded-[18px] bg-[#dfeeda] px-4 py-3 text-sm text-[#486f41]">{{ authSuccess }}</p>
        </div>
      </SectionCard>
    </div>
  </div>
</template>

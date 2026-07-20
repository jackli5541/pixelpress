import {
  computed,
  nextTick,
  onBeforeUnmount,
  onMounted,
  ref,
  toValue,
  watch,
  type MaybeRefOrGetter,
  type WatchSource,
} from 'vue'

interface ProgressiveListOptions {
  initialCount?: number
  batchSize?: number
  rootMargin?: string
  resetKey?: WatchSource<unknown>
}

export function useProgressiveList<T>(
  items: MaybeRefOrGetter<readonly T[]>,
  options: ProgressiveListOptions = {},
) {
  const initialCount = options.initialCount ?? 24
  const batchSize = options.batchSize ?? 24
  const rootMargin = options.rootMargin ?? '240px 0px'
  const renderedCount = ref(initialCount)
  const scrollRoot = ref<HTMLElement | null>(null)
  const sentinel = ref<HTMLElement | null>(null)
  const visibleItems = computed(() => toValue(items).slice(0, renderedCount.value))
  let observer: IntersectionObserver | null = null
  let stopObservingRefs: (() => void) | null = null

  function loadMore() {
    const length = toValue(items).length
    renderedCount.value = Math.min(length, renderedCount.value + batchSize)
  }

  function connectObserver() {
    observer?.disconnect()
    observer = null
    if (!scrollRoot.value || !sentinel.value || typeof IntersectionObserver === 'undefined') return

    observer = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting)) loadMore()
    }, { root: scrollRoot.value, rootMargin })
    observer.observe(sentinel.value)
  }

  function reset() {
    observer?.disconnect()
    renderedCount.value = initialCount
    void nextTick(() => {
      scrollRoot.value?.scrollTo({ top: 0 })
      connectObserver()
    })
  }

  watch(() => toValue(items).length, (length) => {
    renderedCount.value = Math.min(
      Math.max(initialCount, renderedCount.value),
      Math.max(initialCount, length),
    )
  })

  if (options.resetKey) watch(options.resetKey, reset)

  onMounted(() => {
    stopObservingRefs = watch([scrollRoot, sentinel], connectObserver, {
      flush: 'post',
      immediate: true,
    })
  })

  onBeforeUnmount(() => {
    stopObservingRefs?.()
    observer?.disconnect()
  })

  return {
    renderedCount,
    scrollRoot,
    sentinel,
    visibleItems,
    reset,
  }
}

import { onBeforeUnmount, ref, watch, type Ref } from 'vue'
import { httpGet } from '@/shared/api/http'
import type { TaskItem } from '@/shared/types/album'

interface UseAlbumTaskMonitorOptions {
  albumId: Ref<string>
  matches: (task: TaskItem) => boolean
  pollInterval?: number
}

export function useAlbumTaskMonitor(options: UseAlbumTaskMonitorOptions) {
  const latestTask = ref<TaskItem | null>(null)
  const polling = ref(false)
  let pollTimer: number | null = null

  function stopPolling() {
    if (pollTimer != null) {
      window.clearInterval(pollTimer)
      pollTimer = null
    }
    polling.value = false
  }

  async function refreshTask(taskId?: string) {
    if (!options.albumId.value) {
      latestTask.value = null
      return null
    }
    const response = await httpGet<TaskItem[]>(`/albums/${options.albumId.value}/tasks`)
    latestTask.value = taskId
      ? response.data.find((task) => task.id === taskId) ?? null
      : response.data.find(options.matches) ?? null
    return latestTask.value
  }

  function startPolling(taskId?: string, onTerminal?: (task: TaskItem | null) => void | Promise<void>) {
    stopPolling()
    polling.value = true
    const interval = options.pollInterval ?? 1500
    const poll = async () => {
      try {
        const task = await refreshTask(taskId)
        if (task && ['succeeded', 'failed', 'cancelled', 'skipped'].includes(task.task_status)) {
          await onTerminal?.(task)
          stopPolling()
        }
      } catch {
        // Swallow polling errors and let the initiating action surface failures.
      }
    }
    void poll()
    pollTimer = window.setInterval(() => {
      void poll()
    }, interval)
  }

  watch(
    () => options.albumId.value,
    () => {
      stopPolling()
      latestTask.value = null
    },
  )

  onBeforeUnmount(() => {
    stopPolling()
  })

  return {
    latestTask,
    polling,
    refreshTask,
    startPolling,
    stopPolling,
  }
}

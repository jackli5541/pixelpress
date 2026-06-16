import { ref, type Ref } from 'vue'

export interface PhotoDragOptions {
  /** 当照片被放到目标区域时调用 */
  onPhotoMove: (photoId: string, targetAreaId: string) => Promise<void>
  /** 未分配/孤立区域的标识符，默认 '__orphan__' */
  orphanAreaId?: string
}

export interface PhotoDragReturn {
  isDragging: Ref<boolean>
  dragPhotoId: Ref<string | null>
  dragSourceId: Ref<string | null>
  dragOverTargetId: Ref<string | null>
  onDragStart: (event: DragEvent, photoId: string, sourceAreaId: string) => void
  onDragOver: (event: DragEvent, targetAreaId: string) => void
  onDragLeave: (targetAreaId: string) => void
  onDrop: (event: DragEvent, targetAreaId: string) => Promise<void>
  onDragEnd: () => void
  getDragPhotoClass: (photoId: string) => string
  getDropTargetClass: (targetId: string) => string
}

export function usePhotoDrag(options: PhotoDragOptions): PhotoDragReturn {
  const orphanId = options.orphanAreaId ?? '__orphan__'

  // ── 响应式拖拽状态 ──
  const isDragging = ref(false)
  const dragPhotoId = ref<string | null>(null)
  const dragSourceId = ref<string | null>(null)
  const dragOverTargetId = ref<string | null>(null)

  // ── 事件处理器 ──
  function onDragStart(event: DragEvent, photoId: string, sourceAreaId: string): void {
    isDragging.value = true
    dragPhotoId.value = photoId
    dragSourceId.value = sourceAreaId

    const dt = event.dataTransfer
    if (!dt) return

    dt.effectAllowed = 'move'
    dt.setData('text/plain', JSON.stringify({ photoId, sourceAreaId }))

    // 用照片缩略图作为拖拽幽灵图
    const target = event.target as HTMLElement | null
    if (target) {
      const img = target.querySelector('img')
      if (img && dt.setDragImage) {
        dt.setDragImage(img, 20, 20)
      }
    }
  }

  function onDragOver(event: DragEvent, targetAreaId: string): void {
    event.preventDefault()
    if (event.dataTransfer) {
      event.dataTransfer.dropEffect = 'move'
    }
    dragOverTargetId.value = targetAreaId
  }

  function onDragLeave(targetAreaId: string): void {
    // 仅当离开的是当前高亮目标时才清除，避免子元素间穿越导致的闪烁
    if (dragOverTargetId.value === targetAreaId) {
      dragOverTargetId.value = null
    }
  }

  async function onDrop(event: DragEvent, targetAreaId: string): Promise<void> {
    event.preventDefault()
    event.stopPropagation()

    const photoId = dragPhotoId.value
    const sourceId = dragSourceId.value

    // 立即重置本地状态
    resetState()

    // 防呆
    if (!photoId || !sourceId) return
    if (sourceId === targetAreaId) return

    // 两个都是孤儿区 → 跳过
    if (sourceId === orphanId && targetAreaId === orphanId) return

    await options.onPhotoMove(photoId, targetAreaId)
  }

  function onDragEnd(): void {
    resetState()
  }

  function resetState(): void {
    isDragging.value = false
    dragPhotoId.value = null
    dragSourceId.value = null
    dragOverTargetId.value = null
  }

  // ── CSS 类名辅助函数 ──

  function getDragPhotoClass(photoId: string): string {
    if (dragPhotoId.value === photoId) {
      return 'opacity-30 scale-95 transition-all duration-150'
    }
    return 'cursor-grab active:cursor-grabbing transition-all duration-150'
  }

  function getDropTargetClass(targetId: string): string {
    if (dragOverTargetId.value === targetId) {
      return 'ring-2 ring-cyan-400 bg-cyan-50/40 ring-offset-1 transition-all duration-150'
    }
    return 'transition-all duration-150'
  }

  return {
    isDragging,
    dragPhotoId,
    dragSourceId,
    dragOverTargetId,
    onDragStart,
    onDragOver,
    onDragLeave,
    onDrop,
    onDragEnd,
    getDragPhotoClass,
    getDropTargetClass,
  }
}

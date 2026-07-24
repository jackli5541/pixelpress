<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import ProtectedImage from '@/shared/components/ProtectedImage.vue'

export interface LayoutElement {
  type: 'photo'
  photo_id: string
  x: number
  y: number
  width: number
  height: number
  aspect_ratio: number
  fit: 'cover' | 'contain'
  order: number
}

export interface PageLayoutMeta {
  layout_version: 3
  description: { text: string; x: number; y: number; width: number; height: number }
  elements: LayoutElement[]
  [key: string]: unknown
}

interface EditorPage { id: string; page_number: number; meta: PageLayoutMeta }
interface EditorPhoto { id: string; filename: string; url: string }

const props = withDefaults(defineProps<{ pages: EditorPage[]; photos: EditorPhoto[]; savingPageId?: string; pageAspectRatio?: number }>(), { pageAspectRatio: 210 / 297 })
const emit = defineEmits<{ save: [page: EditorPage, meta: PageLayoutMeta] }>()
const selected = ref<{ pageId: string; kind: 'photo' | 'description'; id?: string } | null>(null)
const history = reactive<Record<string, PageLayoutMeta[]>>({})
const future = reactive<Record<string, PageLayoutMeta[]>>({})
const editorError = reactive<Record<string, string>>({})
const photoMap = computed(() => new Map(props.photos.map((photo) => [photo.id, photo])))
const descriptionEdges = ['left', 'right', 'top', 'bottom'] as const

function clone(meta: PageLayoutMeta): PageLayoutMeta {
  return JSON.parse(JSON.stringify(meta))
}

function remember(page: EditorPage) {
  ;(history[page.id] ||= []).push(clone(page.meta))
  if (history[page.id].length > 30) history[page.id].shift()
  future[page.id] = []
}

function undo(page: EditorPage) {
  const previous = history[page.id]?.pop()
  if (!previous) return
  ;(future[page.id] ||= []).push(clone(page.meta))
  page.meta = previous
  emit('save', page, clone(page.meta))
}

function redo(page: EditorPage) {
  const next = future[page.id]?.pop()
  if (!next) return
  ;(history[page.id] ||= []).push(clone(page.meta))
  page.meta = next
  emit('save', page, clone(page.meta))
}

function snap(value: number) {
  const guides = [0, 0.25, 0.5, 0.75, 1]
  const guide = guides.find((item) => Math.abs(item - value) < 0.012)
  return guide ?? value
}

function overlaps(a: { x: number; y: number; width: number; height: number }, b: { x: number; y: number; width: number; height: number }) {
  const gap = 0.018
  return a.x < b.x + b.width + gap && a.x + a.width + gap > b.x && a.y < b.y + b.height + gap && a.y + a.height + gap > b.y
}

function layoutIsValid(page: EditorPage) {
  const boxes = page.meta.elements.map((item) => ({ x: item.x, y: item.y, width: item.width, height: item.height }))
  if (page.meta.description.text.trim()) boxes.push(page.meta.description)
  const boundedBoxes = [...boxes, page.meta.description]
  if (boundedBoxes.some((box) => box.x < 0 || box.y < 0 || box.x + box.width > 1 || box.y + box.height > 0.92)) return false
  return boxes.every((box, index) => boxes.slice(index + 1).every((other) => !overlaps(box, other)))
}

function commit(page: EditorPage) {
  if (!layoutIsValid(page)) {
    const previous = history[page.id]?.pop()
    if (previous) page.meta = previous
    editorError[page.id] = '元素不能重叠、越出安全区或占用页码区域，已恢复调整前的位置。'
    return
  }
  editorError[page.id] = ''
  emit('save', page, clone(page.meta))
}

function startMove(event: PointerEvent, page: EditorPage, kind: 'photo' | 'description', id?: string) {
  if ((event.target as HTMLElement).closest('textarea,button,.resize-handle')) return
  event.preventDefault()
  remember(page)
  selected.value = { pageId: page.id, kind, id }
  const startX = event.clientX
  const startY = event.clientY
  const target = kind === 'photo' ? page.meta.elements.find((item) => item.photo_id === id)! : page.meta.description
  const originalX = target.x
  const originalY = target.y
  const canvas = (event.currentTarget as HTMLElement).closest('.page-canvas') as HTMLElement
  const move = (moveEvent: PointerEvent) => {
    const dx = (moveEvent.clientX - startX) / canvas.clientWidth
    const dy = (moveEvent.clientY - startY) / canvas.clientHeight
    const height = kind === 'photo' ? (target as LayoutElement).height : page.meta.description.height
    target.x = Math.max(0, Math.min(1 - target.width, snap(originalX + dx)))
    target.y = Math.max(0, Math.min(0.92 - height, snap(originalY + dy)))
  }
  const end = () => {
    window.removeEventListener('pointermove', move)
    window.removeEventListener('pointerup', end)
    commit(page)
  }
  window.addEventListener('pointermove', move)
  window.addEventListener('pointerup', end, { once: true })
}

function startResizePhoto(event: PointerEvent, page: EditorPage, element: LayoutElement) {
  event.preventDefault()
  event.stopPropagation()
  remember(page)
  const startX = event.clientX
  const originalWidth = element.width
  const originalHeight = element.height
  const ratio = originalHeight / originalWidth
  const canvas = (event.currentTarget as HTMLElement).closest('.page-canvas') as HTMLElement
  const move = (moveEvent: PointerEvent) => {
    const width = Math.max(0.12, Math.min(1 - element.x, originalWidth + (moveEvent.clientX - startX) / canvas.clientWidth))
    const height = width * ratio
    if (element.y + height <= 0.92) {
      element.width = width
      element.height = height
    }
  }
  const end = () => {
    window.removeEventListener('pointermove', move)
    window.removeEventListener('pointerup', end)
    commit(page)
  }
  window.addEventListener('pointermove', move)
  window.addEventListener('pointerup', end, { once: true })
}

function startResizeDescription(event: PointerEvent, page: EditorPage, edge: 'left' | 'right' | 'top' | 'bottom') {
  event.preventDefault()
  event.stopPropagation()
  remember(page)
  const startX = event.clientX
  const startY = event.clientY
  const originalX = page.meta.description.x
  const originalY = page.meta.description.y
  const originalWidth = page.meta.description.width
  const originalHeight = page.meta.description.height
  const originalRight = originalX + originalWidth
  const originalBottom = originalY + originalHeight
  const canvas = (event.currentTarget as HTMLElement).closest('.page-canvas') as HTMLElement
  const move = (moveEvent: PointerEvent) => {
    if (edge === 'right') {
      page.meta.description.width = Math.max(0.2, Math.min(1 - originalX, originalWidth + (moveEvent.clientX - startX) / canvas.clientWidth))
    } else if (edge === 'left') {
      const nextX = Math.max(0, Math.min(originalRight - 0.2, originalX + (moveEvent.clientX - startX) / canvas.clientWidth))
      page.meta.description.x = nextX
      page.meta.description.width = originalRight - nextX
    }
    const minimumHeight = estimateDescriptionHeight(page.meta.description)
    if (edge === 'bottom') {
      page.meta.description.height = Math.max(minimumHeight, Math.min(0.92 - originalY, originalHeight + (moveEvent.clientY - startY) / canvas.clientHeight))
    } else if (edge === 'top') {
      const nextY = Math.max(0, Math.min(originalBottom - minimumHeight, originalY + (moveEvent.clientY - startY) / canvas.clientHeight))
      page.meta.description.y = nextY
      page.meta.description.height = originalBottom - nextY
    }
  }
  const end = () => {
    window.removeEventListener('pointermove', move)
    window.removeEventListener('pointerup', end)
    commit(page)
  }
  window.addEventListener('pointermove', move)
  window.addEventListener('pointerup', end, { once: true })
}

function estimateDescriptionHeight(description: PageLayoutMeta['description']) {
  if (!description.text.trim()) return 0.06
  const chars = Math.max(8, Math.floor(description.width * 46))
  return Math.min(0.24, 0.035 + Math.ceil(description.text.length / chars) * 0.028)
}

function centerGroup(page: EditorPage) {
  remember(page)
  const boxes = page.meta.elements.map((item) => ({ x: item.x, y: item.y, width: item.width, height: item.height }))
  if (page.meta.description.text.trim()) boxes.push(page.meta.description)
  if (!boxes.length) return
  const left = Math.min(...boxes.map((item) => item.x))
  const right = Math.max(...boxes.map((item) => item.x + item.width))
  const top = Math.min(...boxes.map((item) => item.y))
  const bottom = Math.max(...boxes.map((item) => item.y + item.height))
  const dx = 0.5 - (left + right) / 2
  const dy = 0.46 - (top + bottom) / 2
  page.meta.elements.forEach((item) => { item.x += dx; item.y += dy })
  if (page.meta.description.text.trim()) {
    page.meta.description.x += dx
    page.meta.description.y += dy
  }
  commit(page)
}

let descriptionTimer: number | undefined
function descriptionChanged(page: EditorPage) {
  page.meta.description.height = Math.max(page.meta.description.height, estimateDescriptionHeight(page.meta.description))
  window.clearTimeout(descriptionTimer)
  descriptionTimer = window.setTimeout(() => commit(page), 500)
}
</script>

<template>
  <div class="spread-list">
    <div v-for="spreadIndex in Math.ceil(pages.length / 2)" :key="spreadIndex" class="spread">
      <article v-for="page in pages.slice((spreadIndex - 1) * 2, spreadIndex * 2)" :key="page.id" class="page-wrap">
        <div class="page-toolbar">
          <span>第 {{ page.page_number }} 页 <small v-if="savingPageId === page.id">保存中…</small></span>
          <div><button @click="undo(page)">撤销</button><button @click="redo(page)">重做</button><button @click="centerGroup(page)">居中内容</button></div>
        </div>
        <p v-if="editorError[page.id]" class="editor-error">{{ editorError[page.id] }}</p>
        <div class="page-canvas" :style="{ aspectRatio: String(pageAspectRatio) }">
          <div class="center-guide vertical" /><div class="center-guide horizontal" />
          <div
            v-for="element in page.meta.elements"
            :key="element.photo_id"
            class="photo-element"
            :class="{ selected: selected?.pageId === page.id && selected.id === element.photo_id }"
            :style="{ left: `${element.x * 100}%`, top: `${element.y * 100}%`, width: `${element.width * 100}%`, height: `${element.height * 100}%` }"
            @pointerdown="startMove($event, page, 'photo', element.photo_id)"
          >
            <ProtectedImage v-if="photoMap.get(element.photo_id)" :src="photoMap.get(element.photo_id)!.url" :alt="photoMap.get(element.photo_id)!.filename" :style="{ objectFit: element.fit }" />
            <button class="resize-handle photo-resize" aria-label="等比缩放照片" @pointerdown="startResizePhoto($event, page, element)" />
          </div>
          <div
            class="description-element"
            :class="{ selected: selected?.pageId === page.id && selected.kind === 'description' }"
            :style="{ left: `${page.meta.description.x * 100}%`, top: `${page.meta.description.y * 100}%`, width: `${page.meta.description.width * 100}%`, height: `${page.meta.description.height * 100}%` }"
            @pointerdown="startMove($event, page, 'description')"
          >
            <textarea v-model="page.meta.description.text" maxlength="500" placeholder="点击填写本页描述" @focus="remember(page); selected = { pageId: page.id, kind: 'description' }" @input="descriptionChanged(page)" />
            <button v-for="edge in descriptionEdges" :key="edge" class="resize-handle description-resize" :class="`resize-${edge}`" :aria-label="`调整描述框${edge}`" @pointerdown="startResizeDescription($event, page, edge)" />
          </div>
          <div class="page-number">· {{ page.page_number }} ·</div>
        </div>
      </article>
    </div>
  </div>
</template>

<style scoped>
.editor-error{margin:0;background:#f6d9d3;padding:.4rem .7rem;font-size:.7rem;color:#8b4339}.description-element textarea{field-sizing:content}
.spread-list{display:grid;gap:2rem}.spread{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));max-width:1050px;margin:auto;background:#302c29;padding:1.25rem;border-radius:1rem;gap:2px}.page-wrap{min-width:0}.page-toolbar{display:flex;justify-content:space-between;gap:.5rem;align-items:center;background:#f3eee7;padding:.5rem .75rem;font-size:.75rem;color:#554b43}.page-toolbar div{display:flex;gap:.3rem}.page-toolbar button{padding:.25rem .45rem;border-radius:.4rem;background:#fff}.page-canvas{position:relative;background:#fff;overflow:hidden;box-shadow:inset 0 0 12px #0001}.photo-element{position:absolute;cursor:move;touch-action:none}.photo-element img{display:block;width:100%;height:100%;pointer-events:none}.photo-element.selected{outline:2px solid #b98743}.resize-handle{display:none;position:absolute;width:12px;height:12px;border:0;border-radius:50%;background:#b98743}.selected .resize-handle,.description-element:hover .resize-handle{display:block}.photo-resize{right:-6px;bottom:-6px;cursor:nwse-resize}.description-element{position:absolute;min-height:6%;cursor:move;touch-action:none;border:1px dashed transparent;padding:.2rem}.description-element.selected,.description-element:hover{border-color:#b98743}.description-element textarea{width:100%;height:100%;resize:none;overflow:hidden;border:0;background:transparent;padding:.25rem;font-size:clamp(8px,1vw,13px);line-height:1.55;color:#4f4a46}.description-element textarea:focus{outline:none}.description-resize{z-index:2}.resize-left{left:-6px;top:50%;transform:translateY(-50%);cursor:ew-resize}.resize-right{right:-6px;top:50%;transform:translateY(-50%);cursor:ew-resize}.resize-top{left:50%;top:-6px;transform:translateX(-50%);cursor:ns-resize}.resize-bottom{left:50%;bottom:-6px;transform:translateX(-50%);cursor:ns-resize}.page-number{position:absolute;left:50%;bottom:2.4%;transform:translateX(-50%);font:11px Georgia,serif;color:#625d58}.center-guide{position:absolute;pointer-events:none;background:#b9874322}.center-guide.vertical{left:50%;top:0;width:1px;height:92%}.center-guide.horizontal{left:0;top:46%;width:100%;height:1px}@media(max-width:800px){.spread{grid-template-columns:1fr;gap:1rem;max-width:540px}.page-toolbar{font-size:.68rem}}
.spread-list{gap:3rem}.spread{width:min(100%,1600px);max-width:none;padding:1.5rem}
</style>

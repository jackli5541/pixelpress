export type AlbumWorkflowStep = 'upload' | 'cleaning' | 'chapters' | 'planning' | 'export'

export const WORKFLOW_STEP_ORDER: AlbumWorkflowStep[] = ['upload', 'cleaning', 'chapters', 'planning', 'export']

export function getAlbumStepKey(status?: string | null): AlbumWorkflowStep {
  if (status === 'uploaded') return 'cleaning'
  if (status === 'cleaned') return 'chapters'
  if (status === 'clustered') return 'planning'
  if (status === 'planned') return 'planning'
  if (status === 'rendered' || status === 'exported') return 'export'
  return 'upload'
}

export function getAlbumResumeRoute(albumId: string, status?: string | null): string {
  const step = getAlbumStepKey(status)
  if (step === 'cleaning') return `/albums/${albumId}/cleaning`
  if (step === 'chapters') return `/albums/${albumId}/chapters`
  if (step === 'planning') return `/albums/${albumId}/planning`
  if (step === 'export') return `/albums/${albumId}/export`
  return `/albums/${albumId}/upload`
}

export function getStepIndex(step: AlbumWorkflowStep): number {
  return WORKFLOW_STEP_ORDER.indexOf(step)
}

export function isStepCompleted(status: string | null | undefined, step: AlbumWorkflowStep): boolean {
  return getStepIndex(step) < getStepIndex(getAlbumStepKey(status))
}

export function isStepCurrent(status: string | null | undefined, step: AlbumWorkflowStep): boolean {
  return getAlbumStepKey(status) === step
}

export function isStepAccessible(status: string | null | undefined, step: AlbumWorkflowStep): boolean {
  return getStepIndex(step) <= getStepIndex(getAlbumStepKey(status))
}

export function getRouteStepKey(path: string): AlbumWorkflowStep | null {
  if (path.includes('/upload')) return 'upload'
  if (path.includes('/cleaning')) return 'cleaning'
  if (path.includes('/chapters')) return 'chapters'
  if (path.includes('/planning')) return 'planning'
  if (path.includes('/export')) return 'export'
  return null
}

export function getAlbumResumeLabel(status?: string | null): string {
  const step = getAlbumStepKey(status)
  if (step === 'cleaning') return '将返回镜头筛选'
  if (step === 'chapters') return '将返回章节整理'
  if (step === 'planning') return '将返回页面编排'
  if (step === 'export') return '将返回导出中心'
  return '将返回素材上传'
}

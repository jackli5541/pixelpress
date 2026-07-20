import { computed, ref, type Ref } from 'vue'
import { httpPatch, httpPost } from '@/shared/api/http'

export type ChapterStrategy = 'balanced' | 'activity_first' | 'time_first' | 'location_first'
export type ThemePhotoDecision = 'keep' | 'exclude' | 'review'

export interface ThemeCandidate {
  id: string
  title: string
  constraints: Record<string, unknown>
  recommended_strategy: ChapterStrategy
  source: string
}

export interface ThemeProfile {
  id: string
  status: string
  title: string | null
  candidates: ThemeCandidate[]
  constraints?: Record<string, unknown>
  chapter_strategy: ChapterStrategy
  fallback_used: boolean
  custom_input?: string | null
}

export interface ThemeAssessment<Photo> {
  photo: Photo
  relevance_score: number
  relevance_label: 'relevant' | 'uncertain' | 'off_theme'
  suggested_decision: ThemePhotoDecision
  user_decision: 'keep' | 'exclude' | null
  effective_decision: ThemePhotoDecision
  reasons: string[]
  relevance_evidence?: {
    method?: string
    calibrated?: boolean
    score_kind?: string
    raw_query_similarity?: number | null
    expanded_query_similarity?: number | null
    positive_similarity?: number | null
    negative_similarity?: number | null
    margin?: number | null
    calibration_version?: string
    calibration_status?: 'ready' | 'missing' | 'disabled' | 'mismatch'
    decision_mode?: 'calibrated' | 'provisional_binary' | 'manual_review'
    provisional_threshold?: number | null
    model?: string | null
    dimension?: number | null
  }
  scoring_version?: string | null
}

export interface ThemeWorkspace<Photo> {
  enabled: boolean
  phase: 'needs_analysis' | 'choose_theme' | 'review_theme_photos' | 'ready_to_cluster'
  strategies: ChapterStrategy[]
  profile: ThemeProfile | null
  assessments: ThemeAssessment<Photo>[]
  calibration: {
    status: 'ready' | 'missing' | 'disabled' | 'mismatch'
    auto_decision_enabled: boolean
    decision_mode: 'calibrated' | 'provisional_binary' | 'manual_review'
    provisional_threshold: number | null
    version: string
    provider: string
    model: string
    dimension: number
    query_version: string
    scoring_version: string
  }
  summary: {
    total: number
    kept: number
    suggested_exclude: number
    uncertain: number
    review: number
    excluded: number
  }
}

export function useThemeCuration<Photo extends { id: string }>(albumId: Ref<string>) {
  const workspace = ref<ThemeWorkspace<Photo> | null>(null)
  const customTheme = ref('')
  const selectedCandidateId = ref('')
  const selectedStrategy = ref<ChapterStrategy>('balanced')
  const selectedPhotoIds = ref(new Set<string>())
  const photoView = ref<'candidate' | 'review' | 'removed'>('review')
  const isRechoosing = ref(false)

  const ready = computed(() => !workspace.value?.enabled || workspace.value.phase === 'ready_to_cluster')
  const isSelectionPhase = computed(() => isRechoosing.value || ['needs_analysis', 'choose_theme'].includes(workspace.value?.phase || ''))
  const isReviewPhase = computed(() => !isRechoosing.value && workspace.value?.phase === 'review_theme_photos')
  const candidates = computed(() => workspace.value?.profile?.candidates || [])
  const assessments = computed(() => [...(workspace.value?.assessments || [])].sort((left, right) => (
    right.relevance_score - left.relevance_score || left.photo.id.localeCompare(right.photo.id)
  )))
  const selectedCandidate = computed(() => candidates.value.find((item) => item.id === selectedCandidateId.value) || null)
  const kept = computed(() => assessments.value.filter((item) => item.effective_decision === 'keep'))
  const review = computed(() => assessments.value.filter((item) => item.effective_decision === 'review'))
  const excluded = computed(() => assessments.value.filter((item) => item.effective_decision === 'exclude'))
  const visible = computed(() => photoView.value === 'removed' ? excluded.value : photoView.value === 'review' ? review.value : kept.value)
  const excludedIds = computed(() => new Set(excluded.value.map((item) => item.photo.id)))

  function setWorkspace(value: ThemeWorkspace<Photo>) {
    const previousPhase = workspace.value?.phase
    workspace.value = value
    if (value.phase !== 'review_theme_photos') isRechoosing.value = false
    if (value.phase === 'ready_to_cluster') photoView.value = 'candidate'
    if (value.phase === 'review_theme_photos' && previousPhase !== value.phase) {
      photoView.value = value.summary.review > 0 ? 'review' : 'candidate'
      selectedPhotoIds.value = new Set()
    }
    if (value.phase === 'choose_theme' && !selectedCandidateId.value) {
      const candidate = value.profile?.fallback_used ? null : value.profile?.candidates?.[0]
      if (candidate) chooseCandidate(candidate)
    }
  }

  function chooseCandidate(candidate: ThemeCandidate) {
    selectedCandidateId.value = candidate.id
    selectedStrategy.value = candidate.recommended_strategy
  }

  async function requestAnalysis(useCustomTheme: boolean) {
    return httpPost<{ task: { id: string } }>(`/albums/${albumId.value}/theme-analysis`, {
      custom_theme: useCustomTheme ? customTheme.value.trim() : null,
    })
  }

  async function requestSelection(confirmRebuild: boolean) {
    const profile = workspace.value?.profile
    if (!profile || !selectedCandidateId.value) return null
    return httpPost<{ task: { id: string } }>(`/albums/${albumId.value}/theme-selection`, {
      profile_id: profile.id,
      candidate_id: selectedCandidateId.value,
      chapter_strategy: selectedStrategy.value,
      confirm_rebuild: confirmRebuild,
    })
  }

  async function updateDecisions(photoIds: string[], decision: 'keep' | 'exclude' | null) {
    return httpPatch(`/albums/${albumId.value}/theme-review/decisions`, { photo_ids: photoIds, decision })
  }

  async function reopenReview(confirmRebuild: boolean) {
    return httpPost(`/albums/${albumId.value}/theme-review/reopen`, { confirm_rebuild: confirmRebuild })
  }

  async function confirmReview() {
    return httpPost(`/albums/${albumId.value}/theme-review/confirm`)
  }

  return {
    workspace,
    customTheme,
    selectedCandidateId,
    selectedStrategy,
    selectedPhotoIds,
    photoView,
    isRechoosing,
    ready,
    isSelectionPhase,
    isReviewPhase,
    candidates,
    assessments,
    selectedCandidate,
    kept,
    review,
    excluded,
    visible,
    excludedIds,
    setWorkspace,
    chooseCandidate,
    requestAnalysis,
    requestSelection,
    updateDecisions,
    reopenReview,
    confirmReview,
  }
}

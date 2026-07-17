export type Suggestion = 'keep' | 'review' | 'remove' | null
export type Decision = 'keep' | 'remove' | null
export type ReviewStatus = 'pending_review' | 'included' | 'kept' | 'removed' | 'unanalyzed'
export type PoolMode = 'retained' | 'removed'
export type ReviewAction = 'keep' | 'remove' | 'accept_preferred' | 'keep_all'

export interface CleaningFeatures {
  fallback_used?: boolean
  sharpness?: {
    variance?: number
    score?: number
    severity?: string
    hard_reject?: boolean
    motion_blur_suspected?: boolean
  }
  exposure?: { mean?: number; score?: number | null; severity?: string; applicable?: boolean }
  content_profile?: {
    capture_kind?: 'camera_photo' | 'screenshot_or_graphic' | 'unknown'
    visual_domain?: 'photographic' | 'illustration' | 'mixed' | 'unknown'
    confidence?: number
    signals?: string[]
  }
  resolution?: { width?: number; height?: number; min_side?: number; score?: number; severity?: string }
  composition?: { orientation?: string; aspect_ratio?: number }
  faces?: {
    available?: boolean
    detected_count?: number
    real_face_count?: number
    anime_face_count?: number
    aggregate?: {
      clarity_p20?: number
      closed_eye_suspected_count?: number
      edge_crop_suspected_count?: number
      occlusion_suspected_count?: number
      expression_attention_count?: number
    }
  }
}

export interface PhotoItem {
  id: string
  filename: string
  size: number
  url: string
  width?: number | null
  height?: number | null
  quality_score?: number | null
  cleaning_issues?: string[] | null
  cleaning: {
    suggestion: Suggestion
    review_status: ReviewStatus
    confidence?: number | null
    decision: Decision
    decision_source?: string | null
    excluded: boolean
    analysis_version?: string | null
    features?: CleaningFeatures | null
  }
}

export interface DuplicateMember {
  photo_id: string
  relation_type: string
  hamming_distance?: number | null
  burst_time_delta_ms?: number | null
  preferred_score: number
  rank: number
  is_preferred: boolean
  auto_excluded: boolean
  factors?: Record<string, number | null>
}

export interface DuplicateGroup {
  id: string
  group_type: string
  confidence: number
  preferred_photo_id: string
  thresholds?: { near_phash?: number; burst_phash?: number; burst_window_ms?: number }
  members: DuplicateMember[]
}

export interface CleaningSummary {
  total: number
  retained: number
  keep: number
  review: number
  remove: number
  excluded: number
  pending_review: number
  included: number
  kept: number
  removed: number
  duplicate_groups: number
  analysis_failures: number
}

export interface ReviewQueueItem {
  id: string
  kind: 'single_photo' | 'duplicate_group'
  photo_ids: string[]
  group_id?: string | null
  preferred_photo_id?: string | null
  reason_codes: string[]
  priority: number
  suggested_action: string
  explanation?: Record<string, unknown>
  policy_version: string
}

export interface CleaningResults {
  album_id: string
  analysis_version?: string | null
  review_session_id?: string | null
  content_revision: number
  summary: CleaningSummary
  review_queue: ReviewQueueItem[]
  groups: DuplicateGroup[]
  items: PhotoItem[]
}

export interface CleaningMutationResult {
  changed_items: PhotoItem[]
  summary: CleaningSummary
  content_revision: number
  remaining_review_count: number
  resolved_review_count?: number
}

export const ISSUE_LABELS: Record<string, string> = {
  sharpness_warning: '清晰度偏低',
  sharpness_severe: '严重模糊',
  sharpness_undetermined: '低纹理，无法确认清晰度',
  exposure_warning: '曝光需检查',
  exposure_severe: '曝光异常',
  resolution_warning: '分辨率偏低',
  resolution_severe: '分辨率过低',
  analysis_failed: '分析回退',
  face_analysis_failed: '人脸分析不可用',
  face_edge_crop_suspected: '人脸靠近画面边缘',
  face_blur_suspected: '人脸清晰度偏低',
  closed_eyes_suspected: '疑似闭眼',
  face_occlusion_suspected: '疑似脸部遮挡',
  body_crop_suspected: '疑似主体裁切',
  expression_attention: '表情需关注',
  duplicate_exact: '完全重复',
  duplicate_near: '近似重复',
  duplicate_burst: '连拍相似',
  duplicate_mixed: '混合重复',
}

export function issueLabel(code: string) {
  return ISSUE_LABELS[code] ?? code
}

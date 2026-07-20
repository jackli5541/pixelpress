export interface PhotoItem {
  id: string
  filename: string
  size: number
  url: string
}

export interface ChapterSegmentItem {
  id: string
  name: string
  description: string
  order: number
  segment_type: string
  time_range: string | null
  photo_ids: string[]
  clustering?: {
    quality_score: number | null
    needs_review: boolean
    boundary_stability?: number[]
    feature_coverage?: Record<string, number>
    auto_selected_k?: number
    selected_k?: number
    peak_k?: number
    k_selection_stability?: number | null
    selection_method?: string | null
    partition_method?: string | null
    representative_photo_ids: string[]
  }
}

export interface ChapterItem {
  id: string
  name: string
  description: string
  order: number
  photo_ids: string[]
  segments?: ChapterSegmentItem[]
  clustering?: {
    source: 'algorithm' | 'user' | 'legacy'
    algorithm_version: string | null
    quality_score: number | null
    needs_review: boolean
    strategy?: string
    weights?: Record<string, number>
    auto_selected_k?: number
    selected_k?: number
    peak_k?: number
    granularity?: number
    k_selection_stability?: number | null
    selection_method?: string | null
    partition_method?: string | null
    boundary_stability?: { left?: number; right?: number }
    representative_photo_ids: string[]
    naming_source: 'multimodal_llm' | 'rule'
    feature_coverage?: Record<string, number>
    embedding_model?: string | null
    degraded_photo_count?: number
  }
}

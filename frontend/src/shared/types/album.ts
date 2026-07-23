export type AlbumStatus =
  | 'draft'
  | 'uploaded'
  | 'cleaned'
  | 'clustered'
  | 'planned'
  | 'rendered'
  | 'exported'
  | 'failed'

export interface AlbumCard {
  id: string
  name: string
  project_id?: string | null
  album_type: string
  book_size: string
  theme_style: string
  layout_version?: 'legacy_page_v1' | 'spread_v2'
  status: AlbumStatus
  cover_title?: string | null
  photo_count: number
  resume_step?: string
  resume_route?: string
  updated_at: string
}

export interface TaskItem {
  id: string
  album_id: string
  task_type: string
  task_status: string
  job_id?: string | null
  provider?: string | null
  model?: string | null
  error_code?: string | null
  error_message?: string | null
  retryable?: boolean | null
  progress_step?: string | null
  attempt_count?: number | null
  max_attempts?: number | null
  worker_name?: string | null
  pipeline_name?: string | null
  pipeline_version?: string | null
  request_id?: string | null
  result_payload?: Record<string, unknown> | null
  debug_payload?: Record<string, unknown> | null
  metrics_payload?: Record<string, unknown> | null
  created_at: string
  started_at?: string | null
  heartbeat_at?: string | null
  updated_at?: string | null
  finished_at?: string | null
}

export interface ExportItem {
  id: string
  album_id: string
  status: string
  file_path: string | null
  created_at: string
  task_id: string
  format?: string
  file_size?: number | null
  render_revision?: number | null
  profile_hash?: string | null
}

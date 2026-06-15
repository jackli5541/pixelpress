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
  album_type: string
  book_size: string
  theme_style: string
  status: AlbumStatus
  cover_title?: string | null
  photo_count: number
  updated_at: string
}

export interface TaskItem {
  id: string
  album_id: string
  task_type: string
  task_status: string
  created_at: string
}

export interface ExportItem {
  id: string
  album_id: string
  status: string
  file_path: string | null
  created_at: string
  task_id: string
}

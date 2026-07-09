export interface ProjectSummary {
  id: string
  user_id: string | null
  username: string | null
  name: string
  code: string
  status: string
  created_at: string | null
  updated_at: string | null
}

export interface AdminUserSummary {
  id: string
  username: string
  role: string
  is_active: boolean
  created_at: string | null
}

export interface AIConfigSummary {
  id: string
  project_id: string
  provider_type: string
  base_url: string | null
  model: string
  api_key_masked: string
  is_active: boolean
  priority: number
  remark: string | null
  created_by_admin_id: string | null
  updated_by_admin_id: string | null
  created_at: string | null
  updated_at: string | null
}

export interface AdminAuditLogItem {
  id: string
  admin_user_id: string | null
  action: string
  resource_type: string
  resource_id: string
  payload: Record<string, unknown> | null
  created_at: string | null
}

export interface AIConfigTestResult {
  config_id: string
  provider: string
  model: string
  source: string
  debug: Record<string, unknown> | null
  payload: Record<string, unknown> | null
}

export interface ApiEnvelope<T> {
  code: number
  message: string
  request_id: string
  data: T
}

export class ApiError extends Error {
  status: number
  detail: string
  retryAfterSeconds?: number

  constructor(status: number, detail: string, retryAfterSeconds?: number) {
    super(detail || `Request failed with status ${status}`)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail || `Request failed with status ${status}`
    this.retryAfterSeconds = retryAfterSeconds
  }
}

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000/api/v1'
const TOKEN_KEY = 'pixpress1_access_token'

function getApiBaseUrl() {
  if (typeof window === 'undefined') return new URL(API_BASE_URL)
  return new URL(API_BASE_URL, window.location.origin)
}

export function resolveApiUrl(path: string) {
  if (!path) return path
  if (/^(?:https?:|blob:|data:)/i.test(path)) return path
  const apiBaseUrl = getApiBaseUrl()
  return new URL(path, `${apiBaseUrl.origin}/`).toString()
}

function getPersistentTokenStorage(): Storage | null {
  if (typeof window === 'undefined') return null
  return window.localStorage
}

function getSessionTokenStorage(): Storage | null {
  if (typeof window === 'undefined') return null
  return window.sessionStorage
}

export function getAccessToken(): string | null {
  const persistentStorage = getPersistentTokenStorage()
  const persistentToken = persistentStorage?.getItem(TOKEN_KEY) ?? null
  if (persistentToken) return persistentToken

  const sessionStorage = getSessionTokenStorage()
  const sessionToken = sessionStorage?.getItem(TOKEN_KEY) ?? null
  if (sessionToken && persistentStorage) {
    persistentStorage.setItem(TOKEN_KEY, sessionToken)
    sessionStorage?.removeItem(TOKEN_KEY)
  }
  return sessionToken
}

export function hasAccessToken() {
  return Boolean(getAccessToken())
}

function getAuthHeaders(): Record<string, string> {
  const token = getAccessToken()
  return token ? { Authorization: `Bearer ${token}` } : {}
}

export function setAccessToken(token: string | null) {
  const persistentStorage = getPersistentTokenStorage()
  const sessionStorage = getSessionTokenStorage()
  if (token) {
    persistentStorage?.setItem(TOKEN_KEY, token)
    sessionStorage?.removeItem(TOKEN_KEY)
    return
  }
  persistentStorage?.removeItem(TOKEN_KEY)
  sessionStorage?.removeItem(TOKEN_KEY)
}

export function clearLegacyAccessToken() {
  if (typeof window === 'undefined') return
  window.localStorage.removeItem(TOKEN_KEY)
}

export function clearSessionAccessToken() {
  getSessionTokenStorage()?.removeItem(TOKEN_KEY)
}

function parsePayload(raw: string) {
  if (!raw) return null
  try {
    return JSON.parse(raw)
  } catch {
    return null
  }
}

function parseRetryAfter(value: string | null) {
  if (!value) return undefined
  const seconds = Number(value)
  if (Number.isFinite(seconds)) return Math.max(0, seconds)
  const timestamp = Date.parse(value)
  if (Number.isNaN(timestamp)) return undefined
  return Math.max(0, Math.ceil((timestamp - Date.now()) / 1000))
}

async function request<T>(path: string, init?: RequestInit): Promise<ApiEnvelope<T>> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      ...getAuthHeaders(),
      ...(init?.body instanceof FormData ? {} : init?.body === undefined ? {} : { 'Content-Type': 'application/json' }),
      ...(init?.headers ?? {}),
    },
  })

  const raw = await response.text()
  const payload = parsePayload(raw)

  if (!response.ok) {
    const detail = payload?.detail || payload?.message || raw || `Request failed with status ${response.status}`
    throw new ApiError(response.status, detail, parseRetryAfter(response.headers.get('Retry-After')))
  }

  return payload as ApiEnvelope<T>
}

export async function httpGet<T>(path: string): Promise<ApiEnvelope<T>> {
  return request<T>(path)
}

export async function httpPost<T>(path: string, body?: unknown): Promise<ApiEnvelope<T>> {
  return request<T>(path, {
    method: 'POST',
    body: body === undefined ? undefined : JSON.stringify(body),
  })
}

export async function httpPostForm<T>(path: string, body: FormData): Promise<ApiEnvelope<T>> {
  return request<T>(path, {
    method: 'POST',
    body,
  })
}

export async function httpPatch<T>(path: string, body?: unknown): Promise<ApiEnvelope<T>> {
  return request<T>(path, {
    method: 'PATCH',
    body: body === undefined ? undefined : JSON.stringify(body),
  })
}

export async function httpDelete<T>(path: string): Promise<ApiEnvelope<T>> {
  return request<T>(path, {
    method: 'DELETE',
  })
}

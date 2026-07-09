import { ref } from 'vue'
import { clearLegacyAccessToken, clearSessionAccessToken, hasAccessToken, httpGet, httpPost, setAccessToken } from '@/shared/api/http'

export interface CurrentUser {
  authenticated: boolean
  id: string
  username: string
  role: string
}

export const currentUser = ref<CurrentUser | null>(null)
export const authLoading = ref(false)
export const authResolved = ref(false)

export function resetAuthBootState() {
  clearLegacyAccessToken()
  clearSessionAccessToken()
  currentUser.value = null
  authResolved.value = false
}

export async function loadCurrentUser() {
  if (!hasAccessToken()) {
    currentUser.value = null
    authResolved.value = true
    return null
  }
  authLoading.value = true
  try {
    const response = await httpGet<CurrentUser>('/users/me')
    currentUser.value = response.data
    authResolved.value = true
    return response.data
  } catch {
    currentUser.value = null
    if (hasAccessToken()) setAccessToken(null)
    authResolved.value = true
    return null
  } finally {
    authLoading.value = false
  }
}

export async function login(username: string, password: string) {
  const response = await httpPost<{ access_token: string; token_type: string; role: string; username: string }>('/auth/login', { username, password })
  setAccessToken(response.data.access_token)
  await loadCurrentUser()
  return response.data
}

export async function register(username: string, password: string, role = 'user') {
  return httpPost('/auth/register', { username, password, role })
}

export function logout() {
  setAccessToken(null)
  currentUser.value = null
  authResolved.value = true
}

export function isAuthenticated() {
  return Boolean(currentUser.value)
}

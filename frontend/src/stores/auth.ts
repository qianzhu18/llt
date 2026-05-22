import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import client from '../api/client'

export interface User {
  id: number
  email: string
  nickname: string
  points: number
  is_admin: boolean
  email_verified: boolean
}

export const useAuthStore = defineStore('auth', () => {
  const user = ref<User | null>(null)
  const loading = ref(false)
  const initialized = ref(false)

  const isLoggedIn = computed(() => user.value !== null)
  const isAdmin = computed(() => user.value?.is_admin ?? false)

  async function fetchMe() {
    try {
      const { data } = await client.get<User>('/auth/me')
      user.value = data
    } catch {
      user.value = null
    } finally {
      initialized.value = true
    }
  }

  async function login(email: string, password: string) {
    loading.value = true
    try {
      const { data } = await client.post<{ user: User }>('/auth/login', { email, password })
      user.value = data.user
      return { ok: true }
    } catch (err: any) {
      return { ok: false, error: err.response?.data?.detail || '登录失败' }
    } finally {
      loading.value = false
    }
  }

  async function register(email: string, nickname: string, password: string) {
    loading.value = true
    try {
      const { data } = await client.post<{ user: User; message: string }>('/auth/register', {
        email,
        nickname,
        password,
      })
      return { ok: true, message: data.message }
    } catch (err: any) {
      return { ok: false, error: err.response?.data?.detail || '注册失败' }
    } finally {
      loading.value = false
    }
  }

  async function logout() {
    try {
      await client.post('/auth/logout')
    } finally {
      user.value = null
    }
  }

  return { user, loading, initialized, isLoggedIn, isAdmin, fetchMe, login, register, logout }
})

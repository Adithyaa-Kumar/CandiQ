// api/client.ts
// ───────────────
// Single Axios instance used by the whole app. Two interceptors:
//   1. Request: attach the access token if we have one.
//   2. Response: on a 401, try refreshing once via the refresh token;
//      if that also fails, clear auth state and let the caller's
//      catch block / route guard handle redirecting to login.

import axios, { AxiosError, type InternalAxiosRequestConfig } from "axios"

import type { TokenResponse } from "@/types"

const BASE_URL = import.meta.env.VITE_API_BASE_URL || "/api/v1"

const ACCESS_TOKEN_KEY = "candiq_access_token"
const REFRESH_TOKEN_KEY = "candiq_refresh_token"

export const tokenStorage = {
  getAccess: () => localStorage.getItem(ACCESS_TOKEN_KEY),
  getRefresh: () => localStorage.getItem(REFRESH_TOKEN_KEY),
  set: (tokens: TokenResponse) => {
    localStorage.setItem(ACCESS_TOKEN_KEY, tokens.access_token)
    localStorage.setItem(REFRESH_TOKEN_KEY, tokens.refresh_token)
  },
  clear: () => {
    localStorage.removeItem(ACCESS_TOKEN_KEY)
    localStorage.removeItem(REFRESH_TOKEN_KEY)
  },
}

export const apiClient = axios.create({
  baseURL: BASE_URL,
  timeout: 30_000,
})

apiClient.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = tokenStorage.getAccess()
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

let isRefreshing = false
let refreshQueue: Array<() => void> = []

apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const originalRequest = error.config as InternalAxiosRequestConfig & { _retried?: boolean }

    if (error.response?.status !== 401 || originalRequest._retried || !tokenStorage.getRefresh()) {
      return Promise.reject(error)
    }

    if (isRefreshing) {
      // Another request already triggered a refresh — wait for it.
      return new Promise((resolve) => {
        refreshQueue.push(() => resolve(apiClient(originalRequest)))
      })
    }

    originalRequest._retried = true
    isRefreshing = true

    try {
      const { data } = await axios.post<TokenResponse>(`${BASE_URL}/auth/refresh`, {
        refresh_token: tokenStorage.getRefresh(),
      })
      tokenStorage.set(data)
      refreshQueue.forEach((resolve) => resolve())
      refreshQueue = []
      return apiClient(originalRequest)
    } catch (refreshError) {
      tokenStorage.clear()
      refreshQueue = []
      window.location.href = "/login"
      return Promise.reject(refreshError)
    } finally {
      isRefreshing = false
    }
  }
)

export function extractErrorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail
    if (typeof detail === "string") return detail
    if (Array.isArray(detail)) return detail.map((d) => d.msg).join(", ")
    return error.message
  }
  return "An unexpected error occurred"
}
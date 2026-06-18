// hooks/useAuth.ts
// ──────────────────
// Zustand store for auth state. Persists tokens to localStorage via
// tokenStorage (api/client.ts); persists nothing else — user profile
// is re-fetched implicitly by virtue of every API call attaching the
// token, so there's no separate "rehydrate user" step needed for MVP.

import { create } from "zustand"

import { apiClient, extractErrorMessage, tokenStorage } from "@/api/client"
import type { User } from "@/types"

interface AuthState {
  user: User | null
  isAuthenticated: boolean
  isLoading: boolean
  error: string | null

  register: (email: string, password: string, fullName?: string) => Promise<void>
  login: (email: string, password: string) => Promise<void>
  logout: () => void
  clearError: () => void
}

export const useAuth = create<AuthState>((set) => ({
  user: null,
  isAuthenticated: !!tokenStorage.getAccess(),
  isLoading: false,
  error: null,

  register: async (email, password, fullName) => {
    set({ isLoading: true, error: null })
    try {
      await apiClient.post("/auth/register", { email, password, full_name: fullName })
      // Registration succeeded — log in immediately for a smooth flow.
      const { data } = await apiClient.post("/auth/login", { email, password })
      tokenStorage.set(data)
      set({ isAuthenticated: true, isLoading: false })
    } catch (e) {
      set({ error: extractErrorMessage(e), isLoading: false })
      throw e
    }
  },

  login: async (email, password) => {
    set({ isLoading: true, error: null })
    try {
      const { data } = await apiClient.post("/auth/login", { email, password })
      tokenStorage.set(data)
      set({ isAuthenticated: true, isLoading: false })
    } catch (e) {
      set({ error: extractErrorMessage(e), isLoading: false })
      throw e
    }
  },

  logout: () => {
    tokenStorage.clear()
    set({ user: null, isAuthenticated: false })
  },

  clearError: () => set({ error: null }),
}))
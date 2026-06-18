// App.tsx
// ───────
// Route table + the thin authenticated shell (top bar with brand + logout).
// Unauthenticated routes (login/register) render full-screen with no shell,
// matching how LoginPage/RegisterPage already center themselves on bg-bg.

import type { ReactNode } from "react"
import { Navigate, Route, Routes, useNavigate } from "react-router-dom"

import { useAuth } from "@/hooks/useAuth"
import LoginPage from "@/pages/LoginPage"
import RegisterPage from "@/pages/RegisterPage"
import UploadPage from "@/pages/UploadPage"
import ProgressPage from "@/pages/ProgressPage"
import ResultsPage from "@/pages/ResultsPage"

function ProtectedRoute({ children }: { children: ReactNode }) {
  const { isAuthenticated } = useAuth()
  if (!isAuthenticated) return <Navigate to="/login" replace />
  return <AppShell>{children}</AppShell>
}

function AppShell({ children }: { children: ReactNode }) {
  const { logout } = useAuth()
  const navigate = useNavigate()

  return (
    <div className="min-h-screen bg-bg">
      <header className="border-b border-border">
        <div className="max-w-6xl mx-auto px-8 h-14 flex items-center justify-between">
          <button
            onClick={() => navigate("/upload")}
            className="flex items-center gap-2 cursor-pointer"
          >
            <div className="w-1.5 h-1.5 rounded-full bg-accent shadow-[0_0_8px_#00d4aa]" />
            <span className="text-accent text-xs tracking-[0.2em] uppercase font-semibold">
              CandiQ
            </span>
          </button>
          <button
            onClick={() => {
              logout()
              navigate("/login")
            }}
            className="text-xs text-[#3a5a6a] hover:text-[#c0d0e0] tracking-widest uppercase transition-colors"
          >
            Sign out
          </button>
        </div>
      </header>
      <main>{children}</main>
    </div>
  )
}

export default function App() {
  const { isAuthenticated } = useAuth()

  return (
    <Routes>
      <Route path="/login" element={isAuthenticated ? <Navigate to="/upload" replace /> : <LoginPage />} />
      <Route
        path="/register"
        element={isAuthenticated ? <Navigate to="/upload" replace /> : <RegisterPage />}
      />

      <Route
        path="/upload"
        element={
          <ProtectedRoute>
            <UploadPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/jobs/:jobId"
        element={
          <ProtectedRoute>
            <ProgressPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/jobs/:jobId/results"
        element={
          <ProtectedRoute>
            <ResultsPage />
          </ProtectedRoute>
        }
      />

      <Route path="/" element={<Navigate to={isAuthenticated ? "/upload" : "/login"} replace />} />
      <Route path="*" element={<Navigate to={isAuthenticated ? "/upload" : "/login"} replace />} />
    </Routes>
  )
}

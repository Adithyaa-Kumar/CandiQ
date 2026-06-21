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
      <header className="sticky top-0 z-10 bg-bg/95 backdrop-blur border-b border-border">
        <div className="max-w-6xl mx-auto px-6 h-14 flex items-center justify-between">
          <button
            onClick={() => navigate("/upload")}
            className="flex items-center gap-2.5 cursor-pointer group"
          >
            <div className="w-7 h-7 bg-accent rounded-lg flex items-center justify-center shadow-sm">
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                <path d="M7 1L12 4V10L7 13L2 10V4L7 1Z" fill="white" fillOpacity="0.9"/>
                <path d="M7 5L9.5 6.5V9.5L7 11L4.5 9.5V6.5L7 5Z" fill="white"/>
              </svg>
            </div>
            <span className="font-semibold text-text-primary text-sm tracking-tight group-hover:text-accent transition-colors">
              CandiQ
            </span>
          </button>
          <button
            onClick={() => { logout(); navigate("/login") }}
            className="text-xs text-text-tertiary hover:text-text-secondary transition-colors font-medium"
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
      <Route path="/register" element={isAuthenticated ? <Navigate to="/upload" replace /> : <RegisterPage />} />
      <Route path="/upload" element={<ProtectedRoute><UploadPage /></ProtectedRoute>} />
      <Route path="/jobs/:jobId" element={<ProtectedRoute><ProgressPage /></ProtectedRoute>} />
      <Route path="/jobs/:jobId/results" element={<ProtectedRoute><ResultsPage /></ProtectedRoute>} />
      <Route path="/" element={<Navigate to={isAuthenticated ? "/upload" : "/login"} replace />} />
      <Route path="*" element={<Navigate to={isAuthenticated ? "/upload" : "/login"} replace />} />
    </Routes>
  )
}
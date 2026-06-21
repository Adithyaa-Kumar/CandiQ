import { useState, type FormEvent } from "react"
import { Link, useNavigate } from "react-router-dom"
import { useAuth } from "@/hooks/useAuth"

export default function LoginPage() {
  const navigate = useNavigate()
  const { login, isLoading, error, clearError } = useAuth()
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    clearError()
    try {
      await login(email, password)
      navigate("/upload")
    } catch {}
  }

  return (
    <div className="min-h-screen bg-surface flex items-center justify-center p-4">
      <div className="w-full max-w-sm fade-in">
        {/* Logo */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-12 h-12 bg-accent rounded-xl mb-4 shadow-card-md">
            <svg width="22" height="22" viewBox="0 0 14 14" fill="none">
              <path d="M7 1L12 4V10L7 13L2 10V4L7 1Z" fill="white" fillOpacity="0.9"/>
              <path d="M7 5L9.5 6.5V9.5L7 11L4.5 9.5V6.5L7 5Z" fill="white"/>
            </svg>
          </div>
          <h1 className="text-xl font-semibold text-text-primary">CandiQ</h1>
          <p className="text-text-tertiary text-sm mt-1">AI candidate ranking</p>
        </div>

        <div className="bg-bg rounded-2xl shadow-card-lg border border-border p-8">
          <h2 className="text-lg font-semibold text-text-primary mb-6">Sign in</h2>

          {error && (
            <div className="mb-4 px-4 py-3 bg-error-light border border-red-200 text-error text-sm rounded-xl">
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-text-secondary mb-1.5">
                Email
              </label>
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full border border-border rounded-xl px-4 py-2.5 text-sm text-text-primary
                           placeholder-text-tertiary outline-none focus:border-accent focus:ring-2
                           focus:ring-accent/10 transition-all bg-bg"
                placeholder="you@company.com"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-text-secondary mb-1.5">
                Password
              </label>
              <input
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full border border-border rounded-xl px-4 py-2.5 text-sm text-text-primary
                           placeholder-text-tertiary outline-none focus:border-accent focus:ring-2
                           focus:ring-accent/10 transition-all bg-bg"
                placeholder="••••••••"
              />
            </div>

            <button
              type="submit"
              disabled={isLoading}
              className="w-full py-2.5 bg-accent text-white font-semibold text-sm rounded-xl
                         hover:bg-accent-hover transition-colors disabled:opacity-50 shadow-card mt-2"
            >
              {isLoading ? "Signing in…" : "Sign in"}
            </button>
          </form>

          <p className="text-center text-sm text-text-tertiary mt-6">
            No account?{" "}
            <Link to="/register" className="text-accent font-medium hover:underline">
              Register
            </Link>
          </p>
        </div>
      </div>
    </div>
  )
}
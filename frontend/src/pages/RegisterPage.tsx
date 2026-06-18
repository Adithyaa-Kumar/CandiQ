// pages/RegisterPage.tsx
import { useState, type FormEvent } from "react"
import { Link, useNavigate } from "react-router-dom"

import { useAuth } from "@/hooks/useAuth"

export default function RegisterPage() {
  const navigate = useNavigate()
  const { register, isLoading, error, clearError } = useAuth()
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [fullName, setFullName] = useState("")

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    clearError()
    try {
      await register(email, password, fullName || undefined)
      navigate("/upload")
    } catch {
      // error already in store state
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-bg">
      <div className="w-full max-w-sm">
        <div className="mb-8 text-center">
          <div className="flex items-center justify-center gap-2 mb-2">
            <div className="w-2 h-2 rounded-full bg-accent shadow-[0_0_8px_#00d4aa]" />
            <span className="text-accent text-sm tracking-[0.2em] uppercase font-semibold">
              CandiQ
            </span>
          </div>
          <p className="text-[#3a5a6a] text-xs">AI Candidate Ranking</p>
        </div>

        <form onSubmit={handleSubmit} className="bg-panel border border-border rounded-lg p-6 space-y-4">
          <h1 className="text-[#e2e8f0] text-lg font-light mb-4">Create account</h1>

          {error && (
            <div className="px-3 py-2 border border-red-900/50 bg-red-950/30 text-red-400 text-xs rounded">
              {error}
            </div>
          )}

          <div>
            <label className="block text-xs text-[#4a8aa0] tracking-widest uppercase mb-1.5">
              Full name
            </label>
            <input
              type="text"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              className="w-full bg-bg border border-border focus:border-accent/50 rounded px-3 py-2
                         text-sm text-[#c0d0e0] outline-none transition-colors"
              placeholder="Jane Recruiter"
            />
          </div>

          <div>
            <label className="block text-xs text-[#4a8aa0] tracking-widest uppercase mb-1.5">
              Email
            </label>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full bg-bg border border-border focus:border-accent/50 rounded px-3 py-2
                         text-sm text-[#c0d0e0] outline-none transition-colors"
              placeholder="you@company.com"
            />
          </div>

          <div>
            <label className="block text-xs text-[#4a8aa0] tracking-widest uppercase mb-1.5">
              Password
            </label>
            <input
              type="password"
              required
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full bg-bg border border-border focus:border-accent/50 rounded px-3 py-2
                         text-sm text-[#c0d0e0] outline-none transition-colors"
              placeholder="At least 8 characters"
            />
          </div>

          <button
            type="submit"
            disabled={isLoading}
            className="w-full py-2.5 bg-accent text-bg font-semibold text-sm tracking-widest uppercase
                       rounded hover:bg-[#00eabb] transition-colors disabled:opacity-50"
          >
            {isLoading ? "Creating account..." : "Create account"}
          </button>

          <p className="text-center text-xs text-[#3a5a6a] pt-2">
            Already have an account?{" "}
            <Link to="/login" className="text-accent hover:underline">
              Sign in
            </Link>
          </p>
        </form>
      </div>
    </div>
  )
}
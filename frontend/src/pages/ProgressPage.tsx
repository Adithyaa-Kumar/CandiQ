import { useEffect } from "react"
import { useNavigate, useParams } from "react-router-dom"
import { ProgressTracker } from "@/components/ProgressTracker"
import { useJobPolling } from "@/hooks/useJobPolling"

const REDIRECT_DELAY_MS = 800

export default function ProgressPage() {
  const { jobId } = useParams<{ jobId: string }>()
  const navigate = useNavigate()
  const { job, error, isPolling } = useJobPolling(jobId ?? null)

  useEffect(() => {
    if (job?.status === "completed" && jobId) {
      const t = setTimeout(() => navigate(`/jobs/${jobId}/results`), REDIRECT_DELAY_MS)
      return () => clearTimeout(t)
    }
  }, [job?.status, jobId, navigate])

  if (!jobId) {
    return (
      <div className="max-w-3xl mx-auto px-6 py-24 text-center text-text-tertiary text-sm">
        No job ID in URL.
      </div>
    )
  }

  const isFailed = job?.status === "failed"
  const isComplete = job?.status === "completed"

  return (
    <div className="max-w-3xl mx-auto px-6 py-12">
      {/* Header */}
      <div className="mb-10">
        {job?.jd_signals?.role_title && (
          <div className="text-xs font-semibold text-accent uppercase tracking-widest mb-2">
            {job.jd_signals.role_title}
          </div>
        )}
        <h1 className="text-2xl font-bold text-text-primary">
          {isComplete ? "Evaluation complete" :
           isFailed   ? "Evaluation failed" :
                        "Running the panel…"}
        </h1>
        {job?.status_message && !isFailed && (
          <p className="text-text-secondary text-sm mt-2">{job.status_message}</p>
        )}
      </div>

      {/* Error */}
      {(error || (isFailed && job?.error_message)) && (
        <div className="mb-6 flex gap-3 px-4 py-4 bg-error-light border border-red-200 text-error text-sm rounded-xl">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="shrink-0 mt-0.5">
            <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
          </svg>
          <div>
            {error || job?.error_message}
            {(error || job?.error_message)?.includes("schema") && (
              <div className="mt-1 text-xs opacity-80">
                The database schema may need a migration. Run <code className="font-mono bg-red-100 px-1 rounded">alembic upgrade head</code> and restart.
              </div>
            )}
          </div>
        </div>
      )}

      {/* Progress tracker */}
      <div className="bg-bg rounded-2xl shadow-card border border-border p-6 mb-6">
        <ProgressTracker
          currentStage={job?.current_stage ?? "queued"}
          status={job?.status ?? "pending"}
          progressPct={job?.progress_pct ?? 0}
        />
      </div>

      {/* Live stats */}
      {((job?.shortlisted_count ?? 0) > 0 || (job?.disqualified_count ?? 0) > 0 || (job?.total_candidates ?? 0) > 0) && (
        <div className="grid grid-cols-3 gap-3 mb-6">
          {[
            { label: "Total pool", value: job?.total_candidates ?? "—", color: "text-text-primary" },
            { label: "Filtered out", value: job?.disqualified_count ?? "—", color: "text-text-secondary" },
            { label: "Shortlisted", value: job?.shortlisted_count ?? "—", color: "text-accent" },
          ].map(({ label, value, color }) => (
            <div key={label} className="bg-bg rounded-2xl shadow-card border border-border p-4 text-center">
              <div className={`text-2xl font-bold tabular-nums ${color}`}>{value}</div>
              <div className="text-xs text-text-tertiary font-medium mt-1">{label}</div>
            </div>
          ))}
        </div>
      )}

      {/* Role signals */}
      {job?.jd_signals && (
        <div className="bg-bg rounded-2xl shadow-card border border-border p-6 mb-6">
          <div className="text-xs font-semibold text-text-tertiary uppercase tracking-widest mb-4">
            Role signals detected
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-5">
            {[
              { label: "Domain",     value: job.jd_signals.domain },
              { label: "Seniority",  value: job.jd_signals.seniority },
              { label: "Experience", value: `${job.jd_signals.exp_min}–${job.jd_signals.exp_max} yrs` },
              { label: "Candidates", value: job.total_candidates },
            ].map(({ label, value }) => (
              <div key={label}>
                <div className="text-xs text-text-tertiary mb-1">{label}</div>
                <div className="text-sm font-semibold text-text-primary capitalize">{String(value)}</div>
              </div>
            ))}
          </div>
          {job.jd_signals.top_skills.length > 0 && (
            <div className="flex flex-wrap gap-2">
              {job.jd_signals.top_skills.map(([skill, weight]) => (
                <span key={skill} className="inline-flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-lg
                                              border border-border bg-surface text-text-secondary font-medium">
                  {skill}
                  <span className={`text-[10px] font-bold ${
                    weight >= 9 ? "text-error" : weight >= 7 ? "text-warning" : "text-text-tertiary"
                  }`}>
                    {weight >= 9 ? "required" : weight >= 7 ? "preferred" : ""}
                  </span>
                </span>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Agent panel - show when running specialists */}
      {(job?.current_stage === "specialist_panel" || job?.current_stage === "arbitration") && (
        <div className="bg-bg rounded-2xl shadow-card border border-border p-6 mb-6">
          <div className="text-xs font-semibold text-text-tertiary uppercase tracking-widest mb-4">
            Expert panel
          </div>
          <div className="grid grid-cols-3 gap-3">
            {[
              { name: "Technical", desc: "Stack depth & architecture", icon: "⚙️" },
              { name: "Trajectory", desc: "Career progression", icon: "📈" },
              { name: "Behavioral", desc: "Ownership & initiative", icon: "🎯" },
            ].map(({ name, desc, icon }) => (
              <div key={name} className="p-4 bg-accent-light rounded-xl border border-blue-100">
                <div className="text-base mb-2">{icon}</div>
                <div className="text-xs font-semibold text-accent">{name}</div>
                <div className="text-xs text-text-tertiary mt-0.5">{desc}</div>
                <div className="flex items-center gap-1 mt-2">
                  <div className="w-1.5 h-1.5 bg-accent rounded-full progress-pulse"/>
                  <span className="text-[10px] text-accent">Running</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {isFailed && (
        <div className="text-center mt-4">
          <button
            onClick={() => navigate("/upload")}
            className="px-6 py-2.5 bg-accent text-white font-semibold text-sm rounded-xl
                       hover:bg-accent-hover transition-colors shadow-card"
          >
            Start a new evaluation
          </button>
        </div>
      )}
    </div>
  )
}
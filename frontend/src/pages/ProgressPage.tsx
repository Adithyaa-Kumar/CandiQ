// pages/ProgressPage.tsx
// ───────────────────────
// Polls the job via useJobPolling and shows live stage progress. On
// completion, auto-navigates to the results page after a short beat so
// the user actually sees the "done" tick land instead of being yanked
// away mid-animation.

import { useEffect } from "react"
import { useNavigate, useParams } from "react-router-dom"

import { ProgressTracker } from "@/components/ProgressTracker"
import { useJobPolling } from "@/hooks/useJobPolling"

const REDIRECT_DELAY_MS = 700

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

  if (!jobId) return <MissingJobId />

  return (
    <div className="max-w-3xl mx-auto px-8 py-16">
      <div className="text-center mb-10">
        <span className="text-xs text-[#4a8aa0] tracking-[0.2em] uppercase">
          {job?.jd_signals?.role_title ?? "Evaluating candidates"}
        </span>
        <h1 className="text-2xl font-light text-[#e2e8f0] mt-2">
          {job?.status === "completed"
            ? "Evaluation complete"
            : job?.status === "failed"
            ? "Evaluation failed"
            : "Running the panel..."}
        </h1>
      </div>

      {error && (
        <div className="mb-6 px-4 py-3 border border-red-900/50 bg-red-950/30 text-red-400 text-sm rounded">
          {error}
        </div>
      )}

      {job?.status === "failed" && job.error_message && (
        <div className="mb-6 px-4 py-3 border border-red-900/50 bg-red-950/30 text-red-400 text-sm rounded">
          {job.error_message}
        </div>
      )}

      <div className="bg-panel border border-border rounded-lg p-6 mb-6">
        <ProgressTracker
          currentStage={job?.current_stage ?? "queued"}
          status={job?.status ?? "pending"}
          progressPct={job?.progress_pct ?? 0}
        />
      </div>

      {job?.status_message && (
        <div className="bg-bg border border-border rounded px-4 py-3 mb-6">
          <span className="text-accent text-xs">$</span>{" "}
          <span className="text-[#7a9ab0] text-xs font-mono">{job.status_message}</span>
        </div>
      )}

      {job?.jd_signals && (
        <div className="bg-panel border border-border rounded-lg p-5 mb-6">
          <div className="text-xs text-[#4a8aa0] tracking-widest uppercase mb-3">Role signals</div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-sm mb-4">
            <div>
              <div className="text-[#3a5a6a] text-xs mb-1">Domain</div>
              <div className="text-[#c0d0e0]">{job.jd_signals.domain}</div>
            </div>
            <div>
              <div className="text-[#3a5a6a] text-xs mb-1">Seniority</div>
              <div className="text-[#c0d0e0]">{job.jd_signals.seniority}</div>
            </div>
            <div>
              <div className="text-[#3a5a6a] text-xs mb-1">Experience</div>
              <div className="text-[#c0d0e0]">
                {job.jd_signals.exp_min}–{job.jd_signals.exp_max} yrs
              </div>
            </div>
            <div>
              <div className="text-[#3a5a6a] text-xs mb-1">Candidates</div>
              <div className="text-[#c0d0e0]">{job.total_candidates}</div>
            </div>
          </div>
          {job.jd_signals.top_skills.length > 0 && (
            <div className="flex flex-wrap gap-2">
              {job.jd_signals.top_skills.map(([skill, weight]) => (
                <span
                  key={skill}
                  className="text-xs px-2.5 py-1 rounded border border-border bg-bg text-[#7a9ab0]"
                >
                  {skill} <span className="text-[#2a4a5a]">·{weight.toFixed(1)}</span>
                </span>
              ))}
            </div>
          )}
        </div>
      )}

      {((job?.shortlisted_count ?? 0) > 0 || (job?.disqualified_count ?? 0) > 0) && (
        <div className="grid grid-cols-3 gap-3 text-center">
          <div className="bg-panel border border-border rounded-lg py-3">
            <div className="text-lg text-[#c0d0e0]">{job?.total_candidates ?? "—"}</div>
            <div className="text-[10px] text-[#3a5a6a] tracking-widest uppercase mt-1">Pool</div>
          </div>
          <div className="bg-panel border border-border rounded-lg py-3">
            <div className="text-lg text-[#c0d0e0]">{job?.disqualified_count ?? "—"}</div>
            <div className="text-[10px] text-[#3a5a6a] tracking-widest uppercase mt-1">
              Disqualified
            </div>
          </div>
          <div className="bg-panel border border-border rounded-lg py-3">
            <div className="text-lg text-accent">{job?.shortlisted_count ?? "—"}</div>
            <div className="text-[10px] text-[#3a5a6a] tracking-widest uppercase mt-1">
              Shortlisted
            </div>
          </div>
        </div>
      )}

      {!isPolling && job?.status === "failed" && (
        <div className="text-center mt-8">
          <button
            onClick={() => navigate("/upload")}
            className="px-6 py-2 text-xs tracking-widest uppercase bg-accent text-bg font-semibold rounded hover:bg-[#00eabb] transition-colors"
          >
            Start a new evaluation
          </button>
        </div>
      )}
    </div>
  )
}

function MissingJobId() {
  // jobId missing from the URL — shouldn't happen via normal navigation,
  // but guards against a malformed deep link.
  return (
    <div className="max-w-3xl mx-auto px-8 py-16 text-center text-[#3a5a6a] text-sm">
      No job ID in URL.
    </div>
  )
}

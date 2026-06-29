import { useEffect, useState } from "react"
import { Link, useParams } from "react-router-dom"
import { apiClient, extractErrorMessage } from "@/api/client"
import { AgentReviewDrawer } from "@/components/AgentReviewDrawer"
import { ConsensusTable } from "@/components/ConsensusTable"
import type { JobResultItem, JobResultsResponse, JobStatusResponse } from "@/types"

function JobMatchHeatmap({ topSkills, results }: {
  topSkills: [string, number][]
  results: JobResultItem[]
}) {
  if (!topSkills.length) return null
  const topFive = topSkills.slice(0, 8)

  const getSkillCoverage = (skill: string) => {
    const skillLc = skill.toLowerCase()
    // Scan all text signals: agent pros/cons/rationale, strengths, risks, title
    // This fixes the undercounting bug where skills in career text but not
    // explicitly named in agent pros were scoring 0%
    const matched = results.filter(r => {
      if (r.is_disqualified) return false
      const allText = [
        r.current_title ?? "",
        ...(r.strengths ?? []),
        ...(r.risks ?? []),
        ...r.agent_reviews.flatMap(a => [
          ...a.pros,
          ...a.cons,
          a.rationale ?? "",
        ]),
      ].join(" ").toLowerCase()
      return allText.includes(skillLc)
    })
    return Math.round((matched.length / Math.max(results.filter(r => !r.is_disqualified).length, 1)) * 100)
  }

  return (
    <div className="bg-bg rounded-2xl shadow-card border border-border p-6 mb-6">
      <div className="text-xs font-semibold text-text-tertiary uppercase tracking-wider mb-4">
        Job match heatmap — skill coverage across shortlist
      </div>
      <div className="space-y-3">
        {topFive.map(([skill, weight]) => {
          const pct = getSkillCoverage(skill)
          const barColor = pct >= 60 ? "bg-success" : pct >= 30 ? "bg-warning" : "bg-error"
          return (
            <div key={skill} className="flex items-center gap-3">
              <div className="w-40 shrink-0 flex items-center justify-between">
                <span className="text-xs text-text-secondary font-medium truncate">{skill}</span>
                <span className={`text-[10px] font-bold ml-1 ${
                  weight >= 9 ? "text-error" : weight >= 7 ? "text-warning" : "text-text-tertiary"
                }`}>
                  {weight >= 9 ? "req" : weight >= 7 ? "pref" : ""}
                </span>
              </div>
              <div className="flex-1 h-2 bg-surface-2 rounded-full overflow-hidden">
                <div className={`h-full rounded-full transition-all ${barColor}`} style={{ width: `${pct}%` }} />
              </div>
              <span className="w-10 text-xs font-semibold text-right tabular-nums text-text-secondary">{pct}%</span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function PoolAnalytics({ results, total, disqualified }: {
  results: JobResultItem[]
  total: number
  disqualified: number
}) {
  const qualified = results.filter(r => !r.is_disqualified)
  const avgScore = qualified.length
    ? qualified.reduce((s, r) => s + (r.consensus_score ?? 0), 0) / qualified.length
    : 0

  const topCandidate = qualified.find(r => r.final_rank === 1)

  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
      {[
        { label: "Total pool",      value: total,                 color: "text-text-primary", sub: "candidates uploaded" },
        { label: "Filtered out",    value: disqualified,          color: "text-text-secondary", sub: "didn't pass gate" },
        { label: "Shortlisted",     value: qualified.length,      color: "text-accent",  sub: "passed expert panel" },
        { label: "Avg consensus",   value: avgScore.toFixed(1),   color: avgScore >= 70 ? "text-success" : "text-warning", sub: "mean score" },
      ].map(({ label, value, color, sub }) => (
        <div key={label} className="bg-bg rounded-2xl shadow-card border border-border p-4">
          <div className="text-xs text-text-tertiary font-medium mb-1">{label}</div>
          <div className={`text-2xl font-bold tabular-nums ${color}`}>{value}</div>
          <div className="text-xs text-text-tertiary mt-1">{sub}</div>
        </div>
      ))}
    </div>
  )
}

function CostTracker({ job }: { job: JobStatusResponse | null }) {
  if (!job || (!job.llm_calls && !job.eval_time_seconds)) return null
  return (
    <div className="flex items-center gap-4 text-xs text-text-tertiary bg-surface rounded-xl px-4 py-2.5 border border-border">
      <span className="font-semibold text-text-secondary">Evaluation stats</span>
      <span>🤖 {job.llm_calls} LLM calls</span>
      {job.eval_time_seconds && <span>⏱ {job.eval_time_seconds.toFixed(0)}s total</span>}
      {job.shortlisted_count > 0 && (
        <span>
          {job.total_candidates} → {job.disqualified_count} filtered → {job.shortlisted_count} shortlisted
        </span>
      )}
    </div>
  )
}

export default function ResultsPage() {
  const { jobId } = useParams<{ jobId: string }>()
  const [data, setData] = useState<JobResultsResponse | null>(null)
  const [job, setJob] = useState<JobStatusResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [selected, setSelected] = useState<JobResultItem | null>(null)
  const [showDisqualified, setShowDisqualified] = useState(false)

  useEffect(() => {
    if (!jobId) return
    let cancelled = false
    setIsLoading(true)

    Promise.all([
      apiClient.get<JobResultsResponse>(`/jobs/${jobId}/results`, { params: { include_disqualified: true } }),
      apiClient.get<JobStatusResponse>(`/jobs/${jobId}`),
    ]).then(([resultsRes, statusRes]) => {
      if (!cancelled) {
        setData(resultsRes.data)
        setJob(statusRes.data)
      }
    }).catch(e => {
      if (!cancelled) setError(extractErrorMessage(e))
    }).finally(() => {
      if (!cancelled) setIsLoading(false)
    })

    return () => { cancelled = true }
  }, [jobId])

  if (isLoading) {
    return (
      <div className="max-w-6xl mx-auto px-6 py-24 text-center">
        <div className="inline-flex items-center gap-3 text-text-secondary">
          <div className="w-4 h-4 border-2 border-accent border-t-transparent rounded-full animate-spin"/>
          Loading results…
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="max-w-6xl mx-auto px-6 py-24 text-center">
        <div className="text-error text-sm mb-4">{error}</div>
        <Link to="/upload" className="text-accent text-sm font-medium hover:underline">
          Start a new evaluation
        </Link>
      </div>
    )
  }

  if (!data || data.status !== "completed") {
    return (
      <div className="max-w-6xl mx-auto px-6 py-24 text-center">
        <p className="text-text-secondary text-sm mb-4">This evaluation hasn't finished yet.</p>
        <Link to={`/jobs/${jobId}`} className="text-accent text-sm font-medium hover:underline">
          View progress
        </Link>
      </div>
    )
  }

  const qualified = data.results.filter(r => !r.is_disqualified)
  const disqualified = data.results.filter(r => r.is_disqualified)
  const topSkills = job?.jd_signals?.top_skills ?? []

  return (
    <div className="max-w-6xl mx-auto px-6 py-10">
      {/* Header */}
      <div className="flex items-start justify-between flex-wrap gap-4 mb-8">
        <div>
          {data.role_title && (
            <div className="text-xs font-semibold text-accent uppercase tracking-widest mb-1.5">
              {data.role_title}
            </div>
          )}
          <h1 className="text-2xl font-bold text-text-primary">Consensus Ranking</h1>
          <p className="text-text-secondary text-sm mt-1">
            {qualified.length} candidate{qualified.length !== 1 ? "s" : ""} reviewed by expert AI panel
          </p>
        </div>

        <div className="flex items-center gap-3 flex-wrap">
          <CostTracker job={job} />
          {disqualified.length > 0 && (
            <button
              onClick={() => setShowDisqualified(v => !v)}
              className="text-xs text-text-tertiary hover:text-text-secondary font-medium transition-colors
                         px-3 py-2 border border-border rounded-lg hover:bg-surface"
            >
              {showDisqualified ? "Hide" : `Show ${disqualified.length} filtered`}
            </button>
          )}
          <Link
            to="/upload"
            className="text-xs font-semibold text-white bg-accent hover:bg-accent-hover transition-colors
                       px-4 py-2 rounded-lg shadow-card"
          >
            New evaluation
          </Link>
        </div>
      </div>

      {/* Analytics */}
      <PoolAnalytics
        results={data.results}
        total={data.total_candidates}
        disqualified={data.disqualified_count}
      />

      {/* Skill heatmap */}
      {topSkills.length > 0 && (
        <JobMatchHeatmap topSkills={topSkills} results={data.results} />
      )}

      {/* Results table */}
      <ConsensusTable
        results={showDisqualified ? data.results : qualified}
        selectedCandidateId={selected?.candidate_id ?? null}
        onSelect={setSelected}
      />

      {/* Top candidate highlight */}
      {qualified.length > 0 && (() => {
        const top = qualified.find(r => r.final_rank === 1)
        if (!top) return null
        return (
          <div className="mt-6 p-5 bg-accent-light border border-blue-200 rounded-2xl">
            <div className="flex items-start justify-between flex-wrap gap-3">
              <div>
                <div className="text-xs font-semibold text-accent uppercase tracking-wider mb-1">
                  🏆 Top Recommendation
                </div>
                <div className="text-lg font-bold text-text-primary">{top.candidate_name}</div>
                {top.current_title && (
                  <div className="text-sm text-text-secondary capitalize mt-0.5">{top.current_title}</div>
                )}
              </div>
              <div className="text-right">
                <div className="text-3xl font-bold text-accent tabular-nums">
                  {top.consensus_score?.toFixed(1)}
                </div>
                <div className="text-xs text-text-tertiary">consensus score</div>
              </div>
            </div>
            {top.strengths.length > 0 && (
              <div className="mt-4 pt-4 border-t border-blue-200">
                <div className="text-xs font-semibold text-accent mb-2">Why this candidate</div>
                <div className="flex flex-wrap gap-2">
                  {top.strengths.map((s, i) => (
                    <span key={i} className="text-xs bg-white text-text-secondary px-3 py-1.5 rounded-lg border border-blue-200">
                      {s}
                    </span>
                  ))}
                </div>
              </div>
            )}
            {top.risks.length > 0 && (
              <div className="mt-3">
                <div className="text-xs font-semibold text-warning mb-1.5">Risks to probe</div>
                <div className="flex flex-wrap gap-2">
                  {top.risks.map((r, i) => (
                    <span key={i} className="text-xs bg-warning-light text-warning px-3 py-1.5 rounded-lg border border-amber-200">
                      {r}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        )
      })()}

      <AgentReviewDrawer candidate={selected} onClose={() => setSelected(null)} />
    </div>
  )
}
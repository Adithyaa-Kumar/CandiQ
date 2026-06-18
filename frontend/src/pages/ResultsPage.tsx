// pages/ResultsPage.tsx
// ───────────────────────
// Fetches the final ranked results once (no polling needed — by the time
// the user lands here via ProgressPage, the job is complete). Holds the
// selected candidate for the AgentReviewDrawer; the table itself is
// presentation-only.

import { useEffect, useState } from "react"
import { Link, useParams } from "react-router-dom"

import { apiClient, extractErrorMessage } from "@/api/client"
import { AgentReviewDrawer } from "@/components/AgentReviewDrawer"
import { ConsensusTable } from "@/components/ConsensusTable"
import type { JobResultItem, JobResultsResponse } from "@/types"

export default function ResultsPage() {
  const { jobId } = useParams<{ jobId: string }>()

  const [data, setData] = useState<JobResultsResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [selected, setSelected] = useState<JobResultItem | null>(null)

  useEffect(() => {
    if (!jobId) return
    let cancelled = false

    setIsLoading(true)
    apiClient
      .get<JobResultsResponse>(`/jobs/${jobId}/results`)
      .then(({ data }) => {
        if (!cancelled) setData(data)
      })
      .catch((e) => {
        if (!cancelled) setError(extractErrorMessage(e))
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [jobId])

  if (isLoading) {
    return (
      <div className="max-w-3xl mx-auto px-8 py-24 text-center">
        <p className="text-[#3a5a6a] text-sm">Loading results...</p>
      </div>
    )
  }

  if (error) {
    return (
      <div className="max-w-3xl mx-auto px-8 py-24 text-center">
        <p className="text-red-400 text-sm mb-4">{error}</p>
        <Link to="/upload" className="text-accent text-xs tracking-widest uppercase hover:underline">
          Start a new evaluation
        </Link>
      </div>
    )
  }

  if (data && data.status !== "completed") {
    return (
      <div className="max-w-3xl mx-auto px-8 py-24 text-center">
        <p className="text-[#3a5a6a] text-sm mb-4">This evaluation hasn't finished yet.</p>
        <Link
          to={`/jobs/${jobId}`}
          className="text-accent text-xs tracking-widest uppercase hover:underline"
        >
          View progress
        </Link>
      </div>
    )
  }

  return (
    <div className="max-w-6xl mx-auto px-8 py-10">
      <div className="flex items-end justify-between mb-8 flex-wrap gap-4">
        <div>
          <span className="text-xs text-[#4a8aa0] tracking-[0.2em] uppercase">
            {data?.role_title ?? "Results"}
          </span>
          <h1 className="text-2xl font-light text-[#e2e8f0] mt-1">Consensus ranking</h1>
        </div>
        <div className="flex gap-3 text-center">
          <div className="px-4 py-2 bg-panel border border-border rounded-lg">
            <div className="text-sm text-[#c0d0e0]">{data?.total_candidates ?? 0}</div>
            <div className="text-[10px] text-[#3a5a6a] tracking-widest uppercase">Pool</div>
          </div>
          <div className="px-4 py-2 bg-panel border border-border rounded-lg">
            <div className="text-sm text-[#c0d0e0]">{data?.disqualified_count ?? 0}</div>
            <div className="text-[10px] text-[#3a5a6a] tracking-widest uppercase">Disqualified</div>
          </div>
          <div className="px-4 py-2 bg-panel border border-border rounded-lg">
            <div className="text-sm text-accent">{data?.shortlisted_count ?? 0}</div>
            <div className="text-[10px] text-[#3a5a6a] tracking-widest uppercase">Shortlisted</div>
          </div>
        </div>
      </div>

      <ConsensusTable
        results={data?.results ?? []}
        selectedCandidateId={selected?.candidate_id ?? null}
        onSelect={setSelected}
      />

      <div className="text-center mt-8">
        <Link
          to="/upload"
          className="text-xs text-[#3a5a6a] hover:text-accent tracking-widest uppercase transition-colors"
        >
          Run another evaluation
        </Link>
      </div>

      <AgentReviewDrawer candidate={selected} onClose={() => setSelected(null)} />
    </div>
  )
}

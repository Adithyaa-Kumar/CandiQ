import type { AgentType, JobResultItem } from "@/types"

const AGENT_COLS: { type: AgentType; label: string }[] = [
  { type: "tech_specialist",       label: "Tech"       },
  { type: "trajectory_specialist", label: "Trajectory" },
  { type: "behavioral_specialist", label: "Behavioral" },
]

function getAgentScore(item: JobResultItem, type: AgentType): number | null {
  return item.agent_reviews.find(r => r.agent_type === type)?.score ?? null
}

function ScoreBadge({ score }: { score: number | null }) {
  if (score === null) return <span className="text-text-tertiary text-sm">—</span>
  const color =
    score >= 80 ? "text-success bg-success-light" :
    score >= 60 ? "text-warning bg-warning-light" :
                  "text-error bg-error-light"
  return (
    <span className={`inline-block tabular-nums text-xs font-semibold px-2 py-0.5 rounded-md ${color}`}>
      {score.toFixed(0)}
    </span>
  )
}

function ConfidencePip({ confidence }: { confidence: number | null }) {
  if (confidence === null) return null
  const label = confidence >= 80 ? "High" : confidence >= 55 ? "Med" : "Low"
  const color = confidence >= 80 ? "text-success" : confidence >= 55 ? "text-warning" : "text-error"
  return (
    <span
      title={`Confidence: ${confidence.toFixed(0)}% — based on specialist agreement`}
      className={`text-[10px] font-semibold uppercase tracking-wide ${color}`}
    >
      {label}
    </span>
  )
}

interface Props {
  results: JobResultItem[]
  selectedCandidateId: string | null
  onSelect: (item: JobResultItem) => void
}

export function ConsensusTable({ results, selectedCandidateId, onSelect }: Props) {
  const nameById = Object.fromEntries(results.map(r => [r.candidate_id, r.candidate_name]))

  const sorted = [...results].sort((a, b) => {
    if (a.is_disqualified && !b.is_disqualified) return 1
    if (!a.is_disqualified && b.is_disqualified) return -1
    if (a.final_rank === null) return 1
    if (b.final_rank === null) return -1
    return a.final_rank - b.final_rank
  })

  if (sorted.length === 0) {
    return (
      <div className="bg-bg rounded-2xl shadow-card border border-border p-12 text-center">
        <div className="text-4xl mb-3">🔍</div>
        <p className="text-text-secondary font-medium">No candidates cleared the retrieval filter.</p>
        <p className="text-text-tertiary text-sm mt-1">
          Try relaxing the job description requirements or uploading more candidates.
        </p>
      </div>
    )
  }

  return (
    <div className="bg-bg rounded-2xl shadow-card border border-border overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr className="bg-surface border-b border-border">
              <th className="text-left px-5 py-3.5 text-xs font-semibold text-text-tertiary uppercase tracking-wider w-12">#</th>
              <th className="text-left px-5 py-3.5 text-xs font-semibold text-text-tertiary uppercase tracking-wider">Candidate</th>
              <th className="text-right px-5 py-3.5 text-xs font-semibold text-text-tertiary uppercase tracking-wider">Consensus</th>
              <th className="text-right px-5 py-3.5 text-xs font-semibold text-text-tertiary uppercase tracking-wider">Confidence</th>
              {AGENT_COLS.map(c => (
                <th key={c.type} className="text-right px-5 py-3.5 text-xs font-semibold text-text-tertiary uppercase tracking-wider hidden md:table-cell">
                  {c.label}
                </th>
              ))}
              <th className="px-5 py-3.5 w-8" />
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {sorted.map((item) => {
              const isSelected = item.candidate_id === selectedCandidateId
              const isDisq     = item.is_disqualified
              const displayScore = item.consensus_score

              return (
                <tr
                  key={item.candidate_id}
                  onClick={() => onSelect(item)}
                  className={`cursor-pointer transition-colors ${
                    isDisq     ? "opacity-40 hover:opacity-60 bg-bg" :
                    isSelected ? "bg-accent-light" :
                                 "hover:bg-surface"
                  }`}
                >
                  <td className="px-5 py-4">
                    {isDisq ? (
                      <span className="text-xs text-text-tertiary font-mono">—</span>
                    ) : (
                      <span className="text-sm font-semibold text-text-tertiary tabular-nums">
                        {item.final_rank ?? "—"}
                      </span>
                    )}
                  </td>
                  <td className="px-5 py-4">
                    <div className="font-semibold text-text-primary text-sm truncate max-w-[180px]">
                      {item.candidate_name}
                    </div>
                    <div className="text-xs text-text-tertiary truncate max-w-[180px]">
                      {item.current_title || "—"}
                    </div>
                    {isDisq && item.disqualify_reason && (
                      <div className="text-[10px] text-error mt-0.5 truncate max-w-[180px]">
                        {item.disqualify_reason}
                      </div>
                    )}
                    {/* Alternatives resolved to names */}
                    {!isDisq && item.alternatives.length > 0 && (
                      <div className="text-[10px] text-text-tertiary mt-0.5">
                        Alt: {item.alternatives.slice(0, 2).map(id => nameById[id] || id).join(", ")}
                      </div>
                    )}
                  </td>
                  <td className="px-5 py-4 text-right">
                    {isDisq ? (
                      <span className="text-text-tertiary text-sm">—</span>
                    ) : (
                      <span className={`font-bold text-base tabular-nums ${
                        (displayScore ?? 0) >= 80 ? "text-success" :
                        (displayScore ?? 0) >= 60 ? "text-warning" : "text-error"
                      }`}>
                        {displayScore?.toFixed(1) ?? "—"}
                      </span>
                    )}
                  </td>
                  <td className="px-5 py-4 text-right">
                    {isDisq ? null : <ConfidencePip confidence={item.confidence ?? null} />}
                  </td>
                  {AGENT_COLS.map(c => (
                    <td key={c.type} className="px-5 py-4 text-right hidden md:table-cell">
                      <ScoreBadge score={getAgentScore(item, c.type)} />
                    </td>
                  ))}
                  <td className="px-5 py-4 text-right">
                    <svg
                      width="14" height="14" viewBox="0 0 24 24" fill="none"
                      stroke="currentColor" strokeWidth="2"
                      className={`ml-auto transition-transform ${isSelected ? "rotate-90 text-accent" : "text-text-tertiary"}`}
                    >
                      <polyline points="9 18 15 12 9 6" />
                    </svg>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
import type { AgentType, JobResultItem } from "@/types"

const AGENT_COLS: { type: AgentType; label: string }[] = [
  { type: "tech_specialist",       label: "Tech"       },
  { type: "trajectory_specialist", label: "Trajectory" },
  { type: "behavioral_specialist", label: "Behavioral" },
]

function getScore(item: JobResultItem, type: AgentType) {
  return item.agent_reviews.find(r => r.agent_type === type)?.score ?? null
}

function ScoreBadge({ score }: { score: number | null }) {
  if (score === null) return <span className="text-text-tertiary text-sm">—</span>
  const color = score >= 80 ? "text-success bg-success-light" :
                score >= 60 ? "text-warning bg-warning-light" :
                              "text-error bg-error-light"
  return (
    <span className={`inline-block tabular-nums text-xs font-semibold px-2 py-0.5 rounded-md ${color}`}>
      {score.toFixed(0)}
    </span>
  )
}

function ConsensusScore({ score }: { score: number | null }) {
  if (score === null) return <span className="text-text-tertiary font-medium">—</span>
  const color = score >= 80 ? "text-success" : score >= 60 ? "text-warning" : "text-error"
  return <span className={`font-bold text-base tabular-nums ${color}`}>{score.toFixed(1)}</span>
}

interface Props {
  results: JobResultItem[]
  selectedCandidateId: string | null
  onSelect: (item: JobResultItem) => void
}

export function ConsensusTable({ results, selectedCandidateId, onSelect }: Props) {
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
        <p className="text-text-tertiary text-sm mt-1">Try relaxing the job description requirements or uploading more candidates.</p>
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
              <th className="text-right px-5 py-3.5 text-xs font-semibold text-text-tertiary uppercase tracking-wider">Score</th>
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
              const isDisq = item.is_disqualified

              return (
                <tr
                  key={item.candidate_id}
                  onClick={() => onSelect(item)}
                  className={`cursor-pointer transition-colors ${
                    isSelected ? "bg-accent-light" :
                    isDisq    ? "bg-surface/50 hover:bg-surface" :
                                "hover:bg-surface"
                  }`}
                >
                  <td className="px-5 py-4">
                    {isDisq ? (
                      <span className="text-xs text-error font-medium">✗</span>
                    ) : (
                      <span className="text-sm font-semibold text-text-tertiary tabular-nums">
                        {item.final_rank ?? "—"}
                      </span>
                    )}
                  </td>
                  <td className="px-5 py-4">
                    <div className={`font-semibold text-sm ${isDisq ? "text-text-tertiary" : "text-text-primary"}`}>
                      {item.candidate_name}
                    </div>
                    {item.current_title && (
                      <div className="text-xs text-text-tertiary mt-0.5 capitalize">{item.current_title}</div>
                    )}
                    {isDisq && item.disqualify_reason && (
                      <div className="text-xs text-error mt-1 bg-error-light px-2 py-0.5 rounded-md inline-block">
                        {item.disqualify_reason}
                      </div>
                    )}
                    {/* Strengths preview */}
                    {!isDisq && item.strengths.length > 0 && (
                      <div className="text-xs text-text-tertiary mt-1 line-clamp-1">
                        {item.strengths[0]}
                      </div>
                    )}
                  </td>
                  <td className="px-5 py-4 text-right">
                    <ConsensusScore score={item.consensus_score} />
                  </td>
                  {AGENT_COLS.map(c => (
                    <td key={c.type} className="px-5 py-4 text-right hidden md:table-cell">
                      <ScoreBadge score={getScore(item, c.type)} />
                    </td>
                  ))}
                  <td className="px-5 py-4">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none"
                         stroke={isSelected ? "#2563eb" : "#94a3b8"} strokeWidth="2">
                      <polyline points="9 18 15 12 9 6"/>
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
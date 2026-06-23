import type { AgentReview, AgentType, JobResultItem } from "@/types"

const AGENT_META: Record<AgentType, { label: string; icon: string; focus: string }> = {
  tech_specialist:       { label: "Technical",  icon: "⚙️", focus: "Stack depth, architecture, evidence of shipping" },
  trajectory_specialist: { label: "Trajectory", icon: "📈", focus: "Career velocity, pedigree, growth pattern" },
  behavioral_specialist: { label: "Behavioral", icon: "🎯", focus: "Ownership language, initiative, platform signals" },
}

function scoreColor(score: number): string {
  return score >= 80 ? "text-success" : score >= 60 ? "text-warning" : "text-error"
}
function scoreBarColor(score: number): string {
  return score >= 80 ? "bg-success" : score >= 60 ? "bg-warning" : "bg-error"
}

function ConfidenceMeter({ confidence }: { confidence: number | null }) {
  if (confidence === null) return null
  const label  = confidence >= 80 ? "High" : confidence >= 55 ? "Medium" : "Low"
  const color  = confidence >= 80 ? "text-success" : confidence >= 55 ? "text-warning" : "text-error"
  const barCol = confidence >= 80 ? "bg-success" : confidence >= 55 ? "bg-warning" : "bg-error"
  return (
    <div className="flex items-center gap-3 p-3 bg-surface rounded-xl border border-border mb-4">
      <div className="flex-1">
        <div className="flex items-center justify-between mb-1">
          <span className="text-xs font-semibold text-text-secondary uppercase tracking-wider">
            Panel Confidence
          </span>
          <span className={`text-sm font-bold tabular-nums ${color}`}>
            {confidence.toFixed(0)}% · {label}
          </span>
        </div>
        <div className="h-1.5 bg-surface-2 rounded-full overflow-hidden">
          <div className={`h-full rounded-full ${barCol}`} style={{ width: `${confidence}%` }} />
        </div>
        <div className="text-[10px] text-text-tertiary mt-1">
          {confidence >= 80
            ? "Specialists are in strong agreement — score is reliable"
            : confidence >= 55
            ? "Moderate agreement — one or more specialists diverged"
            : "Low agreement — specialists disagree significantly; interpret score with caution"}
        </div>
      </div>
    </div>
  )
}

function AgentCard({ review }: { review: AgentReview }) {
  const meta = AGENT_META[review.agent_type]
  return (
    <div className="border border-border rounded-xl p-5">
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className="text-xl">{meta.icon}</span>
          <div>
            <div className="font-semibold text-text-primary text-sm">{meta.label}</div>
            <div className="text-xs text-text-tertiary">{meta.focus}</div>
          </div>
        </div>
        <div className="text-right">
          <div className={`text-xl font-bold tabular-nums ${scoreColor(review.score)}`}>
            {review.score.toFixed(0)}
          </div>
          <div className="text-xs text-text-tertiary">/100</div>
        </div>
      </div>

      <div className="h-1.5 bg-surface-2 rounded-full overflow-hidden mb-4">
        <div
          className={`h-full rounded-full transition-all ${scoreBarColor(review.score)}`}
          style={{ width: `${review.score}%` }}
        />
      </div>

      {review.rationale && (
        <p className="text-xs text-text-secondary leading-relaxed mb-4 p-3 bg-surface rounded-lg border border-border">
          "{review.rationale}"
        </p>
      )}

      <div className="grid grid-cols-2 gap-4">
        <div>
          <div className="text-xs font-semibold text-success uppercase tracking-wider mb-2">Strengths</div>
          <ul className="space-y-1.5">
            {review.pros.map((p, i) => (
              <li key={i} className="text-xs text-text-secondary flex gap-1.5">
                <span className="text-success shrink-0">+</span>{p}
              </li>
            ))}
            {review.pros.length === 0 && <li className="text-xs text-text-tertiary">None noted</li>}
          </ul>
        </div>
        <div>
          <div className="text-xs font-semibold text-warning uppercase tracking-wider mb-2">Concerns</div>
          <ul className="space-y-1.5">
            {review.cons.map((c, i) => (
              <li key={i} className="text-xs text-text-secondary flex gap-1.5">
                <span className="text-warning shrink-0">−</span>{c}
              </li>
            ))}
            {review.cons.length === 0 && <li className="text-xs text-text-tertiary">None noted</li>}
          </ul>
        </div>
      </div>
    </div>
  )
}

interface Props {
  item: JobResultItem | null
  onClose: () => void
  allResults?: JobResultItem[]
}

export function AgentReviewDrawer({ item, onClose, allResults = [] }: Props) {
  if (!item) return null

  const nameById = Object.fromEntries(allResults.map(r => [r.candidate_id, r.candidate_name]))

  const orderedReviews = (["tech_specialist", "trajectory_specialist", "behavioral_specialist"] as AgentType[])
    .map(type => item.agent_reviews.find(r => r.agent_type === type))
    .filter(Boolean) as AgentReview[]

  return (
    <div className="fixed inset-0 z-50 flex justify-end" onClick={onClose}>
      <div
        className="w-full max-w-xl bg-surface shadow-modal h-full overflow-y-auto"
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="sticky top-0 bg-surface border-b border-border px-6 py-4 flex items-start justify-between z-10">
          <div>
            <div className="font-bold text-text-primary">{item.candidate_name}</div>
            <div className="text-sm text-text-tertiary">{item.current_title || "—"}</div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg hover:bg-surface-2 transition-colors text-text-tertiary"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>

        <div className="p-6 space-y-6">
          {/* Confidence meter — Tier 5 */}
          <ConfidenceMeter confidence={item.confidence ?? null} />

          {/* Score summary */}
          {!item.is_disqualified && (
            <div className="grid grid-cols-2 gap-3">
              <div className="bg-surface border border-border rounded-xl p-4 text-center">
                <div className="text-xs text-text-tertiary font-medium mb-1">Consensus Score</div>
                <div className={`text-3xl font-bold tabular-nums ${
                  (item.consensus_score ?? 0) >= 80 ? "text-success" :
                  (item.consensus_score ?? 0) >= 60 ? "text-warning" : "text-error"
                }`}>
                  {item.consensus_score?.toFixed(1) ?? "—"}
                </div>
                <div className="text-[10px] text-text-tertiary mt-1">Arbitrator-adjusted, ±15 of weighted vote</div>
              </div>
              <div className="bg-surface border border-border rounded-xl p-4 text-center">
                <div className="text-xs text-text-tertiary font-medium mb-1">Pool Percentile</div>
                <div className="text-3xl font-bold tabular-nums text-accent">
                  {item.normalized_score != null ? `${item.normalized_score.toFixed(0)}` : "—"}
                </div>
                <div className="text-[10px] text-text-tertiary mt-1">Relative to this candidate pool</div>
              </div>
            </div>
          )}

          {/* Disqualified banner */}
          {item.is_disqualified && item.disqualify_reason && (
            <div className="flex gap-3 px-4 py-4 bg-error-light border border-red-200 text-error text-sm rounded-xl">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="shrink-0 mt-0.5">
                <circle cx="12" cy="12" r="10" /><line x1="12" y1="8" x2="12" y2="12" /><line x1="12" y1="16" x2="12.01" y2="16" />
              </svg>
              <div>
                <div className="font-semibold mb-0.5">Disqualified</div>
                {item.disqualify_reason}
              </div>
            </div>
          )}

          {/* Strengths and Risks */}
          {(item.strengths.length > 0 || item.risks.length > 0) && (
            <div className="grid grid-cols-2 gap-4">
              <div>
                <div className="text-xs font-semibold text-success uppercase tracking-wider mb-3">Why they stand out</div>
                <ul className="space-y-2">
                  {item.strengths.map((s, i) => (
                    <li key={i} className="text-xs text-text-secondary flex gap-2 items-start">
                      <span className="text-success shrink-0 mt-0.5">✓</span>{s}
                    </li>
                  ))}
                  {item.strengths.length === 0 && <li className="text-xs text-text-tertiary">None detected</li>}
                </ul>
              </div>
              <div>
                <div className="text-xs font-semibold text-error uppercase tracking-wider mb-3">Risks to consider</div>
                <ul className="space-y-2">
                  {item.risks.map((r, i) => (
                    <li key={i} className="text-xs text-text-secondary flex gap-2 items-start">
                      <span className="text-warning shrink-0 mt-0.5">!</span>{r}
                    </li>
                  ))}
                  {item.risks.length === 0 && <li className="text-xs text-text-tertiary">None noted</li>}
                </ul>
              </div>
            </div>
          )}

          {/* Alternatives resolved to names */}
          {item.alternatives.length > 0 && (
            <div>
              <div className="text-xs font-semibold text-text-tertiary uppercase tracking-wider mb-2">
                Comparable candidates in this shortlist
              </div>
              <div className="flex flex-wrap gap-2">
                {item.alternatives.map((id) => {
                  const altName = nameById[id]
                  if (!altName) return null
                  return (
                    <span key={id} className="text-xs bg-surface-2 text-text-secondary px-3 py-1 rounded-full border border-border">
                      {altName}
                    </span>
                  )
                })}
              </div>
            </div>
          )}

          {/* Per-agent reviews */}
          {orderedReviews.length > 0 && (
            <div>
              <div className="text-sm font-semibold text-text-primary mb-3">
                Specialist Panel Reviews
              </div>
              <div className="space-y-4">
                {orderedReviews.map(review => (
                  <AgentCard key={review.id} review={review} />
                ))}
              </div>
            </div>
          )}

          {/* Retrieval metadata */}
          {item.retrieval_score != null && (
            <div className="text-xs text-text-tertiary pt-2 border-t border-border">
              Retrieval signal: {item.retrieval_score.toFixed(3)} via {item.retrieval_method || "—"}
              {item.rule_composite_score != null && ` · Rule score: ${item.rule_composite_score.toFixed(1)}`}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
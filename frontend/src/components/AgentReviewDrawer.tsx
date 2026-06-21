import type { AgentReview, AgentType, JobResultItem } from "@/types"

const AGENT_META: Record<AgentType, { label: string; icon: string; focus: string }> = {
  tech_specialist:       { label: "Technical",   icon: "⚙️", focus: "Stack depth, architecture, execution" },
  trajectory_specialist: { label: "Trajectory",  icon: "📈", focus: "Career velocity, pedigree, growth" },
  behavioral_specialist: { label: "Behavioral",  icon: "🎯", focus: "Ownership, initiative, platform signals" },
}

function scoreColor(score: number): string {
  return score >= 80 ? "text-success" : score >= 60 ? "text-warning" : "text-error"
}

function scoreBarColor(score: number): string {
  return score >= 80 ? "bg-success" : score >= 60 ? "bg-warning" : "bg-error"
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

      {/* Score bar */}
      <div className="h-1.5 bg-surface-2 rounded-full overflow-hidden mb-4">
        <div
          className={`h-full rounded-full transition-all ${scoreBarColor(review.score)}`}
          style={{ width: `${review.score}%` }}
        />
      </div>

      {review.rationale && (
        <p className="text-xs text-text-secondary leading-relaxed mb-4 p-3 bg-surface rounded-lg">
          "{review.rationale}"
        </p>
      )}

      <div className="grid grid-cols-2 gap-4">
        <div>
          <div className="text-xs font-semibold text-success uppercase tracking-wider mb-2">Strengths</div>
          <ul className="space-y-1.5">
            {review.pros.map((p, i) => (
              <li key={i} className="text-xs text-text-secondary flex gap-1.5">
                <span className="text-success shrink-0">+</span>
                {p}
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
                <span className="text-warning shrink-0">−</span>
                {c}
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
  candidate: JobResultItem | null
  onClose: () => void
}

export function AgentReviewDrawer({ candidate, onClose }: Props) {
  if (!candidate) return null

  const isDisq = candidate.is_disqualified
  const score = candidate.consensus_score

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-black/30 backdrop-blur-sm" onClick={onClose} />

      <div className="relative w-full max-w-lg h-full bg-bg shadow-card-lg overflow-y-auto slide-in-right">
        {/* Header */}
        <div className="sticky top-0 bg-bg/95 backdrop-blur border-b border-border px-6 py-5 flex items-start justify-between z-10">
          <div>
            <h2 className="text-lg font-bold text-text-primary">{candidate.candidate_name}</h2>
            {candidate.current_title && (
              <div className="text-sm text-text-secondary mt-0.5 capitalize">{candidate.current_title}</div>
            )}
            {isDisq && (
              <div className="mt-2 inline-flex items-center gap-1.5 text-xs text-error bg-error-light
                              border border-red-200 px-2.5 py-1 rounded-full font-medium">
                <span>✗</span> {candidate.disqualify_reason}
              </div>
            )}
          </div>
          <button
            onClick={onClose}
            className="w-8 h-8 flex items-center justify-center rounded-lg hover:bg-surface
                       text-text-tertiary hover:text-text-primary transition-colors"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
            </svg>
          </button>
        </div>

        <div className="px-6 py-5">
          {/* Score overview */}
          {!isDisq && (
            <div className="grid grid-cols-2 gap-3 mb-6">
              <div className="bg-surface rounded-xl p-4 text-center">
                <div className="text-xs text-text-tertiary font-medium mb-1">Final Rank</div>
                <div className="text-3xl font-bold text-text-primary">
                  #{candidate.final_rank ?? "—"}
                </div>
              </div>
              <div className="bg-surface rounded-xl p-4 text-center">
                <div className="text-xs text-text-tertiary font-medium mb-1">Consensus Score</div>
                <div className={`text-3xl font-bold tabular-nums ${score ? scoreColor(score) : "text-text-tertiary"}`}>
                  {score?.toFixed(1) ?? "—"}
                </div>
              </div>
            </div>
          )}

          {/* Agent score summary bar */}
          {!isDisq && candidate.agent_reviews.length > 0 && (
            <div className="mb-6 p-4 bg-surface rounded-xl border border-border">
              <div className="text-xs font-semibold text-text-tertiary uppercase tracking-wider mb-3">
                Panel scores
              </div>
              <div className="space-y-2.5">
                {candidate.agent_reviews.map(review => {
                  const meta = AGENT_META[review.agent_type]
                  return (
                    <div key={review.id} className="flex items-center gap-3">
                      <div className="w-24 text-xs text-text-secondary font-medium shrink-0">
                        {meta.icon} {meta.label}
                      </div>
                      <div className="flex-1 h-2 bg-surface-2 rounded-full overflow-hidden">
                        <div
                          className={`h-full rounded-full ${scoreBarColor(review.score)}`}
                          style={{ width: `${review.score}%` }}
                        />
                      </div>
                      <div className={`w-8 text-xs font-bold tabular-nums text-right ${scoreColor(review.score)}`}>
                        {review.score.toFixed(0)}
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          )}

          {/* Strengths */}
          {candidate.strengths.length > 0 && (
            <div className="mb-4 p-4 bg-success-light rounded-xl border border-green-200">
              <div className="text-xs font-semibold text-success uppercase tracking-wider mb-2.5">
                ✓ Why selected
              </div>
              <ul className="space-y-1.5">
                {candidate.strengths.map((s, i) => (
                  <li key={i} className="text-sm text-text-secondary flex gap-2">
                    <span className="text-success shrink-0 mt-0.5">•</span>{s}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Risks */}
          {candidate.risks.length > 0 && (
            <div className="mb-6 p-4 bg-warning-light rounded-xl border border-amber-200">
              <div className="text-xs font-semibold text-warning uppercase tracking-wider mb-2.5">
                ⚠ Probe in interview
              </div>
              <ul className="space-y-1.5">
                {candidate.risks.map((r, i) => (
                  <li key={i} className="text-sm text-text-secondary flex gap-2">
                    <span className="text-warning shrink-0 mt-0.5">•</span>{r}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Agent breakdown */}
          {candidate.agent_reviews.length > 0 && (
            <>
              <div className="text-xs font-semibold text-text-tertiary uppercase tracking-wider mb-3">
                Agent breakdown
              </div>
              <div className="space-y-3 mb-6">
                {candidate.agent_reviews.map(review => (
                  <AgentCard key={review.id} review={review} />
                ))}
              </div>
            </>
          )}

          {/* Retrieval metadata */}
          <div className="pt-4 border-t border-border">
            <div className="text-xs font-semibold text-text-tertiary uppercase tracking-wider mb-3">
              Retrieval metadata
            </div>
            <div className="grid grid-cols-3 gap-3">
              {[
                { label: "Method",     value: candidate.retrieval_method ?? "—" },
                { label: "Similarity", value: candidate.retrieval_score?.toFixed(3) ?? "—" },
                { label: "Rule score", value: candidate.rule_composite_score?.toFixed(1) ?? "—" },
              ].map(({ label, value }) => (
                <div key={label} className="bg-surface rounded-lg p-3 text-center">
                  <div className="text-xs text-text-tertiary mb-1">{label}</div>
                  <div className="text-xs font-semibold text-text-primary font-mono">{value}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
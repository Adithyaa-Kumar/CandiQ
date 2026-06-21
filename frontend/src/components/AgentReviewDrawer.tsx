// components/AgentReviewDrawer.tsx
// ───────────────────────────────────
// Slide-over panel showing the arbitrator's verdict (strengths/risks)
// plus each specialist's full pros/cons/rationale for one candidate.
//
// BUG FIX: was referencing `candidate.executive_summary` (old field),
// which no longer exists on JobResultItem since migration d4c1611d96eb
// replaced it with `strengths`, `risks`, `alternatives`. Now renders
// those three arrays instead, which is richer and more actionable.

import type { AgentReview, AgentType, JobResultItem } from "@/types"

const AGENT_META: Record<AgentType, { label: string; focus: string }> = {
  tech_specialist: {
    label: "Tech & Hard Skills",
    focus: "Stack depth, architecture exposure, execution history",
  },
  trajectory_specialist: {
    label: "Pedigree & Trajectory",
    focus: "Career velocity, company scale, tenure stability",
  },
  behavioral_specialist: {
    label: "Behavioral & Platform Signals",
    focus: "Open-source activity, communication, mentorship signals",
  },
}

function scoreColor(score: number): string {
  if (score >= 80) return "text-accent"
  if (score >= 60) return "text-accent2"
  return "text-[#c08a4a]"
}

function AgentCard({ review }: { review: AgentReview }) {
  const meta = AGENT_META[review.agent_type]
  return (
    <div className="border border-border rounded-lg p-4">
      <div className="flex items-start justify-between mb-1">
        <div>
          <div className="text-[#c0d0e0] text-sm">{meta.label}</div>
          <div className="text-[#3a5a6a] text-xs mt-0.5">{meta.focus}</div>
        </div>
        <div className={`text-lg tabular-nums font-medium ${scoreColor(review.score)}`}>
          {review.score.toFixed(0)}
        </div>
      </div>

      {review.rationale && (
        <p className="text-[#7a9ab0] text-xs leading-relaxed mt-3">{review.rationale}</p>
      )}

      <div className="grid grid-cols-2 gap-3 mt-3">
        <div>
          <div className="text-[10px] text-accent tracking-widest uppercase mb-1.5">Pros</div>
          <ul className="space-y-1">
            {review.pros.map((p, i) => (
              <li key={i} className="text-xs text-[#9ab0c0] flex gap-1.5">
                <span className="text-accent">+</span> {p}
              </li>
            ))}
          </ul>
        </div>
        <div>
          <div className="text-[10px] text-[#c08a4a] tracking-widest uppercase mb-1.5">Cons</div>
          <ul className="space-y-1">
            {review.cons.map((c, i) => (
              <li key={i} className="text-xs text-[#9ab0c0] flex gap-1.5">
                <span className="text-[#c08a4a]">−</span> {c}
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  )
}

interface AgentReviewDrawerProps {
  candidate: JobResultItem | null
  onClose: () => void
}

export function AgentReviewDrawer({ candidate, onClose }: AgentReviewDrawerProps) {
  if (!candidate) return null

  const hasVerdict =
    (candidate.strengths?.length ?? 0) > 0 || (candidate.risks?.length ?? 0) > 0

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-black/60" onClick={onClose} />

      <div className="relative w-full max-w-xl h-full bg-panel border-l border-border overflow-y-auto">
        <div className="sticky top-0 bg-panel border-b border-border px-6 py-4 flex items-start justify-between">
          <div>
            <div className="text-[#e2e8f0] text-lg">{candidate.candidate_name}</div>
            {candidate.current_title && (
              <div className="text-[#3a5a6a] text-xs mt-0.5">{candidate.current_title}</div>
            )}
            {candidate.is_disqualified && (
              <div className="mt-1 text-[10px] text-red-400 tracking-widest uppercase">
                Disqualified — {candidate.disqualify_reason}
              </div>
            )}
          </div>
          <button
            onClick={onClose}
            className="text-[#3a5a6a] hover:text-[#c0d0e0] text-xl leading-none transition-colors"
          >
            ×
          </button>
        </div>

        <div className="px-6 py-5">
          {!candidate.is_disqualified && (
            <div className="flex items-center gap-6 mb-6">
              <div>
                <div className="text-[10px] text-[#4a8aa0] tracking-widest uppercase mb-1">
                  Final rank
                </div>
                <div className="text-2xl text-[#c0d0e0] tabular-nums">
                  {candidate.final_rank ?? "—"}
                </div>
              </div>
              <div>
                <div className="text-[10px] text-[#4a8aa0] tracking-widest uppercase mb-1">
                  Consensus score
                </div>
                <div
                  className={`text-2xl tabular-nums ${
                    candidate.consensus_score ? scoreColor(candidate.consensus_score) : "text-[#3a5a6a]"
                  }`}
                >
                  {candidate.consensus_score?.toFixed(1) ?? "—"}
                </div>
              </div>
            </div>
          )}

          {/* FIX: replaced executive_summary with strengths + risks */}
          {hasVerdict && (
            <div className="mb-6 space-y-3">
              {candidate.strengths.length > 0 && (
                <div className="bg-bg border border-border rounded-lg p-4">
                  <div className="text-[10px] text-accent tracking-widest uppercase mb-2">
                    Strengths
                  </div>
                  <ul className="space-y-1">
                    {candidate.strengths.map((s, i) => (
                      <li key={i} className="text-xs text-[#9ab0c0] flex gap-1.5">
                        <span className="text-accent">✓</span> {s}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {candidate.risks.length > 0 && (
                <div className="bg-bg border border-border rounded-lg p-4">
                  <div className="text-[10px] text-[#c08a4a] tracking-widest uppercase mb-2">
                    Risks to probe
                  </div>
                  <ul className="space-y-1">
                    {candidate.risks.map((r, i) => (
                      <li key={i} className="text-xs text-[#9ab0c0] flex gap-1.5">
                        <span className="text-[#c08a4a]">⚠</span> {r}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}

          {candidate.agent_reviews.length > 0 && (
            <>
              <div className="text-[10px] text-[#4a8aa0] tracking-widest uppercase mb-3">
                Specialist panel
              </div>
              <div className="space-y-3 mb-6">
                {candidate.agent_reviews.map((review) => (
                  <AgentCard key={review.id} review={review} />
                ))}
              </div>
            </>
          )}

          <div className="border-t border-border pt-4 flex gap-6 text-xs text-[#3a5a6a]">
            {candidate.retrieval_method && (
              <span>
                Retrieval: <span className="text-[#7a9ab0]">{candidate.retrieval_method}</span>
              </span>
            )}
            {candidate.retrieval_score !== null && (
              <span>
                Similarity:{" "}
                <span className="text-[#7a9ab0]">{candidate.retrieval_score?.toFixed(2)}</span>
              </span>
            )}
            {candidate.rule_composite_score !== null && (
              <span>
                Rule score:{" "}
                <span className="text-[#7a9ab0]">{candidate.rule_composite_score?.toFixed(1)}</span>
              </span>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
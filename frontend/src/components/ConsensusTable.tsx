// components/ConsensusTable.tsx
// ───────────────────────────────
// The "trust" view: every candidate's consensus score plus the three
// specialist scores that fed into it, side by side, so a recruiter never
// has to take the ranking on faith. Clicking a row opens the full
// rationale in AgentReviewDrawer (managed by the parent).

import type { AgentType, JobResultItem } from "@/types"

const AGENT_COLUMNS: { type: AgentType; label: string }[] = [
  { type: "tech_specialist", label: "Tech" },
  { type: "trajectory_specialist", label: "Trajectory" },
  { type: "behavioral_specialist", label: "Behavioral" },
]

function getAgentScore(item: JobResultItem, type: AgentType): number | null {
  return item.agent_reviews.find((r) => r.agent_type === type)?.score ?? null
}

function scoreColor(score: number | null): string {
  if (score === null) return "text-[#3a5a6a]"
  if (score >= 80) return "text-accent"
  if (score >= 60) return "text-accent2"
  return "text-[#c08a4a]"
}

interface ConsensusTableProps {
  results: JobResultItem[]
  selectedCandidateId: string | null
  onSelect: (item: JobResultItem) => void
}

export function ConsensusTable({ results, selectedCandidateId, onSelect }: ConsensusTableProps) {
  const sorted = [...results].sort((a, b) => {
    if (a.final_rank === null) return 1
    if (b.final_rank === null) return -1
    return a.final_rank - b.final_rank
  })

  if (sorted.length === 0) {
    return (
      <div className="bg-panel border border-border rounded-lg p-10 text-center">
        <p className="text-[#3a5a6a] text-sm">No candidates cleared the retrieval filter.</p>
      </div>
    )
  }

  return (
    <div className="bg-panel border border-border rounded-lg overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left">
              <th className="px-4 py-3 text-[10px] text-[#4a8aa0] tracking-widest uppercase font-normal w-12">
                Rank
              </th>
              <th className="px-4 py-3 text-[10px] text-[#4a8aa0] tracking-widest uppercase font-normal">
                Candidate
              </th>
              <th className="px-4 py-3 text-[10px] text-[#4a8aa0] tracking-widest uppercase font-normal text-right">
                Consensus
              </th>
              {AGENT_COLUMNS.map((col) => (
                <th
                  key={col.type}
                  className="px-4 py-3 text-[10px] text-[#4a8aa0] tracking-widest uppercase font-normal text-right hidden md:table-cell"
                >
                  {col.label}
                </th>
              ))}
              <th className="px-4 py-3 w-8" />
            </tr>
          </thead>
          <tbody>
            {sorted.map((item) => {
              const isSelected = item.candidate_id === selectedCandidateId
              return (
                <tr
                  key={item.candidate_id}
                  onClick={() => onSelect(item)}
                  className={`border-b border-border/60 last:border-0 cursor-pointer transition-colors ${
                    isSelected ? "bg-accent/5" : "hover:bg-bg/60"
                  }`}
                >
                  <td className="px-4 py-3 text-[#3a5a6a] tabular-nums">
                    {item.final_rank ?? "—"}
                  </td>
                  <td className="px-4 py-3">
                    <div className="text-[#c0d0e0]">{item.candidate_name}</div>
                    {item.current_title && (
                      <div className="text-[#3a5a6a] text-xs mt-0.5">{item.current_title}</div>
                    )}
                  </td>
                  <td
                    className={`px-4 py-3 text-right tabular-nums font-medium ${scoreColor(
                      item.consensus_score
                    )}`}
                  >
                    {item.consensus_score?.toFixed(1) ?? "—"}
                  </td>
                  {AGENT_COLUMNS.map((col) => {
                    const score = getAgentScore(item, col.type)
                    return (
                      <td
                        key={col.type}
                        className={`px-4 py-3 text-right tabular-nums hidden md:table-cell ${scoreColor(
                          score
                        )}`}
                      >
                        {score?.toFixed(0) ?? "—"}
                      </td>
                    )
                  })}
                  <td className="px-4 py-3 text-[#2a4a5a]">›</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

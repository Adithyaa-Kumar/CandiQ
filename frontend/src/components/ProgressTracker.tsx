// components/ProgressTracker.tsx
// ───────────────────────────────
// Horizontal HUD-style stepper for the 5 real pipeline stages (queued is
// folded into "before stage 1 starts" rather than shown as its own lit
// step — recruiters care about what's happening now, not the enqueue).

import type { JobStage, JobStatus } from "@/types"

const STAGES: { key: JobStage; label: string; detail: string }[] = [
  { key: "analyzing_jd", label: "JD Analysis", detail: "Extracting role signals" },
  { key: "retrieval_filter", label: "Retrieval Filter", detail: "Hybrid shortlist" },
  { key: "specialist_panel", label: "Specialist Panel", detail: "3 agents in parallel" },
  { key: "arbitration", label: "Arbitration", detail: "Final consensus" },
  { key: "done", label: "Done", detail: "Results ready" },
]

function stageIndex(stage: JobStage): number {
  if (stage === "queued") return -1
  const i = STAGES.findIndex((s) => s.key === stage)
  return i === -1 ? 0 : i
}

interface ProgressTrackerProps {
  currentStage: JobStage
  status: JobStatus
  progressPct: number
}

export function ProgressTracker({ currentStage, status, progressPct }: ProgressTrackerProps) {
  const activeIndex = stageIndex(currentStage)
  const failed = status === "failed"

  return (
    <div className="w-full">
      <div className="flex items-center justify-between mb-3">
        <span className="text-xs text-[#4a8aa0] tracking-[0.15em] uppercase">Pipeline</span>
        <span className={`text-xs tabular-nums ${failed ? "text-red-400" : "text-accent"}`}>
          {failed ? "Failed" : `${Math.round(progressPct)}%`}
        </span>
      </div>

      <div className="h-1 w-full bg-border rounded-full overflow-hidden mb-6">
        <div
          className={`h-full rounded-full transition-all duration-500 ${
            failed ? "bg-red-500" : "bg-accent shadow-[0_0_8px_#00d4aa]"
          }`}
          style={{ width: `${Math.max(2, Math.min(100, progressPct))}%` }}
        />
      </div>

      <div className="grid grid-cols-5 gap-2">
        {STAGES.map((stage, i) => {
          const isDone = i < activeIndex || (i === activeIndex && status === "completed")
          const isActive = i === activeIndex && status !== "completed" && status !== "failed"
          const isError = i === activeIndex && failed

          return (
            <div key={stage.key} className="flex flex-col items-center text-center gap-2">
              <div
                className={`w-7 h-7 rounded-full border flex items-center justify-center text-xs transition-colors ${
                  isError
                    ? "border-red-500 text-red-400 bg-red-950/30"
                    : isDone
                    ? "border-accent bg-accent text-bg"
                    : isActive
                    ? "border-accent text-accent shadow-[0_0_10px_rgba(0,212,170,0.4)] animate-pulse"
                    : "border-border text-[#2a3a4a]"
                }`}
              >
                {isError ? "!" : isDone ? "✓" : i + 1}
              </div>
              <div>
                <div
                  className={`text-[11px] tracking-wide leading-tight ${
                    isDone || isActive ? "text-[#c0d0e0]" : "text-[#3a5a6a]"
                  }`}
                >
                  {stage.label}
                </div>
                <div className="text-[10px] text-[#2a3a4a] leading-tight mt-0.5 hidden sm:block">
                  {stage.detail}
                </div>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

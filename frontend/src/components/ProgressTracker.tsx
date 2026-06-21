import type { JobStage, JobStatus } from "@/types"

const STAGES: { key: JobStage; label: string; detail: string; icon: string }[] = [
  { key: "analyzing_jd",    label: "JD Analysis",        detail: "Extracting role signals",   icon: "📋" },
  { key: "retrieval_filter", label: "Smart Filter",       detail: "Hybrid shortlist",          icon: "🔍" },
  { key: "specialist_panel", label: "Expert Panel",       detail: "3 AI agents in parallel",   icon: "🧠" },
  { key: "arbitration",     label: "Arbitration",         detail: "Final consensus ranking",   icon: "⚖️" },
  { key: "done",            label: "Complete",            detail: "Results ready",             icon: "✅" },
]

function stageIndex(stage: JobStage): number {
  if (stage === "queued") return -1
  const i = STAGES.findIndex(s => s.key === stage)
  return i === -1 ? 0 : i
}

interface Props {
  currentStage: JobStage
  status: JobStatus
  progressPct: number
}

export function ProgressTracker({ currentStage, status, progressPct }: Props) {
  const activeIndex = stageIndex(currentStage)
  const failed = status === "failed"
  const completed = status === "completed"

  return (
    <div className="w-full">
      {/* Progress bar */}
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs font-medium text-text-secondary">Pipeline progress</span>
        <span className={`text-xs font-semibold tabular-nums ${failed ? "text-error" : "text-accent"}`}>
          {failed ? "Failed" : `${Math.round(progressPct)}%`}
        </span>
      </div>
      <div className="h-2 w-full bg-surface-2 rounded-full overflow-hidden mb-8">
        <div
          className={`h-full rounded-full transition-all duration-700 ${
            failed ? "bg-error" : "bg-accent"
          } ${!completed && !failed ? "progress-pulse" : ""}`}
          style={{ width: `${Math.max(2, Math.min(100, progressPct))}%` }}
        />
      </div>

      {/* Stage steps */}
      <div className="relative">
        {/* Connector line */}
        <div className="absolute top-5 left-5 right-5 h-0.5 bg-border z-0" />
        <div
          className={`absolute top-5 left-5 h-0.5 z-0 transition-all duration-700 ${failed ? "bg-error" : "bg-accent"}`}
          style={{ width: `calc(${Math.max(0, Math.min(100, (activeIndex / (STAGES.length - 1)) * 100))}% - 10px)` }}
        />

        <div className="relative z-10 grid gap-2" style={{ gridTemplateColumns: `repeat(${STAGES.length}, 1fr)` }}>
          {STAGES.map((stage, i) => {
            const isDone = i < activeIndex || (i === activeIndex && completed)
            const isActive = i === activeIndex && !completed && !failed
            const isError = i === activeIndex && failed
            const isFuture = i > activeIndex

            return (
              <div key={stage.key} className="flex flex-col items-center gap-2">
                <div className={`w-10 h-10 rounded-full border-2 flex items-center justify-center text-sm
                                 transition-all duration-300 bg-bg ${
                  isError   ? "border-error bg-error-light" :
                  isDone    ? "border-accent bg-accent" :
                  isActive  ? "border-accent bg-accent-light shadow-md shadow-accent/20" :
                              "border-border"
                }`}>
                  {isError ? (
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#dc2626" strokeWidth="2.5">
                      <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
                    </svg>
                  ) : isDone ? (
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5">
                      <polyline points="20 6 9 17 4 12"/>
                    </svg>
                  ) : isActive ? (
                    <div className="w-2.5 h-2.5 bg-accent rounded-full progress-pulse"/>
                  ) : (
                    <span className="text-xs text-text-tertiary font-medium">{i + 1}</span>
                  )}
                </div>
                <div className="text-center">
                  <div className={`text-xs font-semibold leading-tight ${
                    isDone || isActive ? "text-text-primary" : "text-text-tertiary"
                  }`}>
                    {stage.label}
                  </div>
                  <div className="text-[11px] text-text-tertiary leading-tight mt-0.5 hidden sm:block">
                    {stage.detail}
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
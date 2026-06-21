import { useEffect, useRef, useState } from "react"
import { useNavigate } from "react-router-dom"
import { apiClient, extractErrorMessage } from "@/api/client"
import { UploadZone } from "@/components/InputPanel"
import type { CandidateIngestResponse, JobCreateResponse, PoolStatusResponse } from "@/types"

type Step =
  | "idle"
  | "uploading_candidates"
  | "waiting_for_pool"
  | "ready_to_evaluate"
  | "pool_failed"
  | "submitting_job"

const POLL_INTERVAL_MS = 3_000

export default function UploadPage() {
  const navigate = useNavigate()

  const jdFileRef = useRef<File | null>(null)
  const jdTextRef = useRef("")
  const candFileRef = useRef<File | null>(null)
  const candTextRef = useRef("")
  const pollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const cancelledRef = useRef(false)

  const [step, setStep] = useState<Step>("idle")
  const [error, setError] = useState<string | null>(null)
  const [candidatesReceived, setCandidatesReceived] = useState<number | null>(null)
  const [poolCandidateCount, setPoolCandidateCount] = useState<number | null>(null)
  const [uploadProgress, setUploadProgress] = useState<number | null>(null)
  const [sampleCandidates, setSampleCandidates] = useState<string[]>([])
  const [, forceRender] = useState(0)

  const hasJd = !!(jdFileRef.current || jdTextRef.current.trim())
  const hasCandidates = !!(candFileRef.current || candTextRef.current.trim())

  useEffect(() => {
    cancelledRef.current = false
    return () => {
      cancelledRef.current = true
      if (pollTimerRef.current) clearTimeout(pollTimerRef.current)
    }
  }, [])

  const startPollingPool = () => {
    const poll = async () => {
      if (cancelledRef.current) return
      try {
        const { data } = await apiClient.get<PoolStatusResponse>("/candidates/pool-status")
        if (cancelledRef.current) return
        if (data.status === "ready") {
          setPoolCandidateCount(data.candidate_count)
          setStep("ready_to_evaluate")
        } else if (data.status === "failed") {
          setStep("pool_failed")
          setError("Candidate processing failed. Please try uploading again.")
        } else {
          pollTimerRef.current = setTimeout(poll, POLL_INTERVAL_MS)
        }
      } catch {
        if (!cancelledRef.current)
          pollTimerRef.current = setTimeout(poll, POLL_INTERVAL_MS)
      }
    }
    poll()
  }

  const handleUploadCandidates = async () => {
    setError(null)
    setStep("uploading_candidates")
    setUploadProgress(0)
    setSampleCandidates([])
    if (pollTimerRef.current) clearTimeout(pollTimerRef.current)

    try {
      const form = new FormData()
      if (candFileRef.current) {
        form.append("candidates_file", candFileRef.current)
      } else {
        form.append("candidates_text", candTextRef.current)
      }

      const { data } = await apiClient.post<CandidateIngestResponse>("/candidates/upload", form, {
        headers: { "Content-Type": "multipart/form-data" },
        onUploadProgress: (e) => {
          if (e.total) setUploadProgress(Math.round((e.loaded / e.total) * 100))
        },
      })

      setCandidatesReceived(data.candidates_received)
      setUploadProgress(null)
      setStep("waiting_for_pool")
      startPollingPool()
    } catch (e) {
      setUploadProgress(null)
      setError(extractErrorMessage(e))
      setStep("idle")
    }
  }

  const handleEvaluate = async () => {
    setError(null)
    setStep("submitting_job")
    try {
      const form = new FormData()
      if (jdFileRef.current) {
        form.append("jd_file", jdFileRef.current)
      } else {
        form.append("jd_text", jdTextRef.current)
      }
      const { data } = await apiClient.post<JobCreateResponse>("/jobs", form, {
        headers: { "Content-Type": "multipart/form-data" },
      })
      navigate(`/jobs/${data.job_id}`)
    } catch (e) {
      setError(extractErrorMessage(e))
      setStep("ready_to_evaluate")
    }
  }

  const poolCount = poolCandidateCount ?? candidatesReceived

  return (
    <div className="max-w-3xl mx-auto px-6 py-12">
      {/* Hero */}
      <div className="text-center mb-12">
        <h1 className="text-3xl font-bold text-text-primary tracking-tight">
          Find the right people,{" "}
          <span className="text-accent">not just keywords.</span>
        </h1>
        <p className="text-text-secondary text-base mt-3 max-w-xl mx-auto">
          Upload your candidate pool once, then evaluate against any job description using a
          multi-agent AI panel.
        </p>
      </div>

      {error && (
        <div className="mb-6 flex gap-3 px-4 py-3 bg-error-light border border-red-200 text-error text-sm rounded-xl">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="shrink-0 mt-0.5">
            <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
          </svg>
          {error}
        </div>
      )}

      {/* Step 1 */}
      <div className="bg-bg rounded-2xl shadow-card border border-border p-6 mb-4">
        <div className="flex items-center gap-3 mb-5">
          <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-semibold ${
            step === "ready_to_evaluate" || step === "submitting_job"
              ? "bg-success text-white"
              : "bg-accent text-white"
          }`}>
            {step === "ready_to_evaluate" || step === "submitting_job" ? (
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5">
                <polyline points="20 6 9 17 4 12"/>
              </svg>
            ) : "1"}
          </div>
          <div>
            <div className="font-semibold text-text-primary text-sm">Candidate Pool</div>
            <div className="text-xs text-text-tertiary">Upload your résumés or candidate data</div>
          </div>
          {/* Status badge */}
          {step === "waiting_for_pool" && (
            <div className="ml-auto flex items-center gap-2 text-xs text-warning bg-warning-light px-3 py-1.5 rounded-full">
              <div className="w-1.5 h-1.5 bg-warning rounded-full progress-pulse"/>
              Indexing {poolCount ? `${poolCount} candidates` : "…"}
            </div>
          )}
          {(step === "ready_to_evaluate" || step === "submitting_job") && poolCount !== null && (
            <div className="ml-auto flex items-center gap-2 text-xs text-success bg-success-light px-3 py-1.5 rounded-full font-medium">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                <polyline points="20 6 9 17 4 12"/>
              </svg>
              {poolCount} candidates indexed
            </div>
          )}
        </div>

        <UploadZone
          label="Candidates"
          sublabel="JSON, JSONL, CSV, PDF, DOCX, or plain text"
          accept=".json,.jsonl,.csv,.pdf,.docx,.txt"
          textPlaceholder="Paste JSON, JSONL, CSV, or plain résumé text. Separate multiple résumés with -----"
          onFile={(f) => { candFileRef.current = f; candTextRef.current = ""; forceRender(n => n+1) }}
          onText={(t) => { candTextRef.current = t; candFileRef.current = null; forceRender(n => n+1) }}
          uploadProgress={step === "uploading_candidates" ? uploadProgress : null}
        />

        {step === "waiting_for_pool" && (
          <div className="mt-4 h-1 bg-surface-2 rounded-full overflow-hidden">
            <div className="h-full bg-warning rounded-full progress-pulse w-full"/>
          </div>
        )}

        {/* Sample preview */}
        {sampleCandidates.length > 0 && (
          <div className="mt-4 p-4 bg-surface rounded-xl border border-border">
            <div className="text-xs font-medium text-text-secondary mb-2">Preview</div>
            <div className="space-y-1">
              {sampleCandidates.map((name, i) => (
                <div key={i} className="text-sm text-text-primary">{name}</div>
              ))}
            </div>
          </div>
        )}

        <button
          onClick={handleUploadCandidates}
          disabled={!hasCandidates || step === "uploading_candidates" || step === "waiting_for_pool"}
          className={`mt-5 px-5 py-2.5 text-sm font-semibold rounded-xl transition-all ${
            hasCandidates && step !== "uploading_candidates" && step !== "waiting_for_pool"
              ? "bg-accent text-white hover:bg-accent-hover shadow-card cursor-pointer"
              : "bg-surface-2 text-text-tertiary cursor-not-allowed"
          }`}
        >
          {step === "uploading_candidates" ? "Uploading…" :
           step === "waiting_for_pool" ? "Indexing…" : "Upload Candidates"}
        </button>
      </div>

      {/* Step 2 */}
      <div className={`bg-bg rounded-2xl shadow-card border border-border p-6 mb-6 transition-opacity ${
        step === "ready_to_evaluate" || step === "submitting_job" ? "" : "opacity-50 pointer-events-none"
      }`}>
        <div className="flex items-center gap-3 mb-5">
          <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-semibold ${
            step === "ready_to_evaluate" || step === "submitting_job"
              ? "bg-accent text-white"
              : "bg-surface-2 text-text-tertiary border border-border"
          }`}>2</div>
          <div>
            <div className="font-semibold text-text-primary text-sm">Job Description</div>
            <div className="text-xs text-text-tertiary">The role you're hiring for</div>
          </div>
        </div>

        <UploadZone
          label="Job Description"
          sublabel="TXT, PDF, or DOCX"
          accept=".txt,.pdf,.docx"
          textPlaceholder="Paste the full job description — title, responsibilities, requirements, anything…"
          onFile={(f) => { jdFileRef.current = f; jdTextRef.current = ""; forceRender(n => n+1) }}
          onText={(t) => { jdTextRef.current = t; jdFileRef.current = null; forceRender(n => n+1) }}
        />
      </div>

      {/* CTA */}
      <div className="text-center">
        <button
          onClick={handleEvaluate}
          disabled={!hasJd || step !== "ready_to_evaluate"}
          className={`px-10 py-3 text-sm font-semibold rounded-xl transition-all shadow-card-md ${
            hasJd && step === "ready_to_evaluate"
              ? "bg-accent text-white hover:bg-accent-hover cursor-pointer"
              : "bg-surface-2 text-text-tertiary cursor-not-allowed"
          }`}
        >
          {step === "submitting_job" ? "Starting evaluation…" : "Evaluate Candidates"}
        </button>
        {step === "waiting_for_pool" && (
          <p className="text-text-tertiary text-xs mt-3">
            Embedding and indexing candidates — usually 10–60s. The button unlocks automatically.
          </p>
        )}
        {step === "pool_failed" && (
          <p className="text-error text-xs mt-3">
            Indexing failed. Check your file format and try again.
          </p>
        )}
      </div>
    </div>
  )
}
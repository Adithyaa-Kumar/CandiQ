// pages/UploadPage.tsx
//
// Two-step flow:
//   1. POST /candidates/upload — ingest candidate pool (async)
//   2. Poll GET /candidates/pool-status until status === "ready"
//   3. POST /jobs — submit JD for evaluation
//
// BUG FIX: original used a hardcoded setTimeout(25000) to "wait" for
// ingestion to finish before unlocking the Evaluate button. This broke
// in two ways:
//   a) 25s is arbitrary — small pools finish in 3s, large ones take 90s+
//   b) The button unlocked regardless of whether ingestion actually succeeded
//
// Now polls GET /candidates/pool-status on a 3s interval until
// status === "ready" or "failed", then enables/disables the button
// accordingly. Accurate and no magic numbers.

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
  const [, forceRender] = useState(0)

  const hasJd = !!(jdFileRef.current || jdTextRef.current.trim())
  const hasCandidates = !!(candFileRef.current || candTextRef.current.trim())

  // Clean up poll timer on unmount
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
          // still processing — poll again
          pollTimerRef.current = setTimeout(poll, POLL_INTERVAL_MS)
        }
      } catch (e) {
        if (cancelledRef.current) return
        // Don't abort on transient network errors — keep polling
        pollTimerRef.current = setTimeout(poll, POLL_INTERVAL_MS)
      }
    }
    poll()
  }

  const handleUploadCandidates = async () => {
    setError(null)
    setStep("uploading_candidates")
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
      })

      setCandidatesReceived(data.candidates_received)
      setStep("waiting_for_pool")
      startPollingPool()
    } catch (e) {
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

  const statusLabel = () => {
    if (step === "uploading_candidates") return "Uploading…"
    if (step === "waiting_for_pool") return "Indexing candidates…"
    if (step === "ready_to_evaluate" && poolCandidateCount !== null)
      return `✓ ${poolCandidateCount} candidates indexed`
    if (step === "ready_to_evaluate" && candidatesReceived !== null)
      return `✓ ${candidatesReceived} candidates queued`
    return null
  }

  const uploadButtonLabel = () => {
    if (step === "uploading_candidates") return "Uploading…"
    if (step === "waiting_for_pool") return "Indexing…"
    return "Upload Candidates"
  }

  const uploadBusy = step === "uploading_candidates" || step === "waiting_for_pool"

  return (
    <div className="max-w-4xl mx-auto px-8 py-12">
      <div className="mb-12 text-center">
        <h1 className="text-3xl font-light text-[#e2e8f0] tracking-tight mb-2">
          Find the right people,
          <br />
          <span className="text-accent">not just the right keywords.</span>
        </h1>
        <p className="text-[#3a5a6a] text-sm mt-4">
          Upload your candidate pool once, then evaluate it against any job description.
        </p>
      </div>

      {error && (
        <div className="mb-6 px-4 py-3 border border-red-900/50 bg-red-950/30 text-red-400 text-sm rounded">
          {error}
        </div>
      )}

      {/* Step 1: candidate pool */}
      <div className="bg-panel border border-border rounded-lg p-5 mb-6">
        <div className="flex items-center justify-between mb-1">
          <span className="text-xs text-accent tracking-widest uppercase">Step 1</span>
          {statusLabel() && (
            <span className="text-xs text-accent">{statusLabel()}</span>
          )}
        </div>
        <UploadZone
          label="Candidate Pool"
          accept=".json,.jsonl,.csv,.pdf,.docx,.txt"
          textPlaceholder="Paste JSON, JSONL, CSV, or plain résumé text. Multiple résumés? Separate with -----"
          onFile={(f) => {
            candFileRef.current = f
            candTextRef.current = ""
            forceRender((n) => n + 1)
          }}
          onText={(t) => {
            candTextRef.current = t
            candFileRef.current = null
            forceRender((n) => n + 1)
          }}
        />

        {/* Inline indexing progress bar */}
        {step === "waiting_for_pool" && (
          <div className="mt-3 h-1 bg-border rounded overflow-hidden">
            <div className="h-full bg-accent animate-pulse w-full" />
          </div>
        )}

        <button
          onClick={handleUploadCandidates}
          disabled={!hasCandidates || uploadBusy}
          className={`mt-4 px-6 py-2 text-xs tracking-widest uppercase transition-all rounded ${
            hasCandidates && !uploadBusy
              ? "bg-accent text-bg font-semibold hover:bg-[#00eabb] cursor-pointer"
              : "bg-bg text-[#2a3a4a] border border-border cursor-not-allowed"
          }`}
        >
          {uploadButtonLabel()}
        </button>
      </div>

      {/* Step 2: job description */}
      <div
        className={`bg-panel border border-border rounded-lg p-5 mb-6 transition-opacity ${
          step === "ready_to_evaluate" || step === "submitting_job" ? "" : "opacity-40"
        }`}
      >
        <div className="text-xs text-accent tracking-widest uppercase mb-1">Step 2</div>
        <UploadZone
          label="Job Description"
          accept=".txt,.pdf,.docx"
          textPlaceholder="Paste the full job description here — title, responsibilities, requirements, anything…"
          onFile={(f) => {
            jdFileRef.current = f
            jdTextRef.current = ""
            forceRender((n) => n + 1)
          }}
          onText={(t) => {
            jdTextRef.current = t
            jdFileRef.current = null
            forceRender((n) => n + 1)
          }}
        />
      </div>

      <div className="text-center">
        <button
          onClick={handleEvaluate}
          disabled={!hasJd || step !== "ready_to_evaluate"}
          className={`px-12 py-3 text-sm tracking-[0.2em] uppercase transition-all rounded ${
            hasJd && step === "ready_to_evaluate"
              ? "bg-accent text-bg font-semibold hover:bg-[#00eabb] cursor-pointer"
              : "bg-bg text-[#2a3a4a] border border-border cursor-not-allowed"
          }`}
        >
          {step === "submitting_job" ? "Submitting…" : "Evaluate Candidates"}
        </button>
        {step === "waiting_for_pool" && (
          <p className="text-[#2a3a4a] text-xs mt-3">
            Embedding and indexing candidates — this usually takes 10–60 seconds.
            Evaluate will unlock automatically when ready.
          </p>
        )}
        {step === "pool_failed" && (
          <p className="text-red-400 text-xs mt-3">
            Indexing failed. Try uploading again or check the backend logs.
          </p>
        )}
      </div>
    </div>
  )
}
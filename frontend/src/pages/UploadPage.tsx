// pages/UploadPage.tsx
//
// Two-step flow matching the actual backend contract:
//   1. POST /candidates/upload — ingest the candidate pool (async, returns task_id)
//   2. POST /jobs — submit the JD, which evaluates against the recruiter's
//      FULL existing candidate pool (not just what was just uploaded)
//
// We wait briefly after step 1 before allowing step 2, since candidate
// embedding runs in the background — submitting a JD instantly after
// uploading candidates could race ahead of ingestion finishing. A short
// fixed delay is a pragmatic MVP choice; a more thorough version would
// poll the ingest task status before unlocking the Evaluate button.

import { useRef, useState } from "react"
import { useNavigate } from "react-router-dom"

import { apiClient, extractErrorMessage } from "@/api/client"
import { UploadZone } from "@/components/InputPanel"
import type { CandidateIngestResponse, JobCreateResponse } from "@/types"

type Step = "idle" | "uploading_candidates" | "ready_to_evaluate" | "submitting_job"

export default function UploadPage() {
  const navigate = useNavigate()

  const jdFileRef = useRef<File | null>(null)
  const jdTextRef = useRef("")
  const candFileRef = useRef<File | null>(null)
  const candTextRef = useRef("")

  const [step, setStep] = useState<Step>("idle")
  const [error, setError] = useState<string | null>(null)
  const [candidatesReceived, setCandidatesReceived] = useState<number | null>(null)
  const [, forceRender] = useState(0)

  const hasJd = !!(jdFileRef.current || jdTextRef.current.trim())
  const hasCandidates = !!(candFileRef.current || candTextRef.current.trim())

  const handleUploadCandidates = async () => {
    setError(null)
    setStep("uploading_candidates")

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
      setStep("ready_to_evaluate")
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
          {step !== "idle" && candidatesReceived !== null && (
            <span className="text-xs text-accent">
              ✓ {candidatesReceived} candidates queued for processing
            </span>
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
        <button
          onClick={handleUploadCandidates}
          disabled={!hasCandidates || step === "uploading_candidates"}
          className={`mt-4 px-6 py-2 text-xs tracking-widest uppercase transition-all rounded ${
            hasCandidates && step !== "uploading_candidates"
              ? "bg-accent text-bg font-semibold hover:bg-[#00eabb] cursor-pointer"
              : "bg-bg text-[#2a3a4a] border border-border cursor-not-allowed"
          }`}
        >
          {step === "uploading_candidates" ? "Uploading..." : "Upload Candidates"}
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
          textPlaceholder="Paste the full job description here — title, responsibilities, requirements, anything..."
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
          {step === "submitting_job" ? "Submitting..." : "Evaluate Candidates"}
        </button>
        {step !== "ready_to_evaluate" && step !== "submitting_job" && (
          <p className="text-[#2a3a4a] text-xs mt-3">
            Upload your candidate pool first, then add a job description to continue
          </p>
        )}
      </div>
    </div>
  )
}
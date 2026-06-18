// types.ts
// ─────────
// Mirrors app/schemas/*.py exactly. Keep these in sync with the backend —
// any drift here is a silent bug (a field renamed on one side and not
// the other won't show up until the response actually arrives wrong).

// ── Auth ──────────────────────────────────────────────────────────────────

export interface User {
  id: string
  email: string
  full_name: string | null
  is_active: boolean
  created_at: string
}

export interface TokenResponse {
  access_token: string
  refresh_token: string
  token_type: "bearer"
}

// ── Candidates ────────────────────────────────────────────────────────────

export interface Candidate {
  id: string
  external_id: string | null
  name: string
  current_title: string | null
  years_of_experience: number | null
  created_at: string
}

export interface CandidateIngestResponse {
  task_id: string
  candidates_received: number
  message: string
}

// ── Jobs ──────────────────────────────────────────────────────────────────

export type JobStatus = "pending" | "running" | "completed" | "failed"

export type JobStage =
  | "queued"
  | "analyzing_jd"
  | "retrieval_filter"
  | "specialist_panel"
  | "arbitration"
  | "done"

export interface JDSignals {
  role_title: string
  domain: string
  seniority: string
  exp_min: number
  exp_max: number
  top_skills: [string, number][]
}

export interface JobCreateResponse {
  job_id: string
  status: JobStatus
  message: string
}

export interface JobStatusResponse {
  job_id: string
  status: JobStatus
  current_stage: JobStage
  progress_pct: number
  status_message: string | null
  error_message: string | null
  jd_signals: JDSignals | null
  total_candidates: number
  disqualified_count: number
  shortlisted_count: number
  created_at: string
  started_at: string | null
  completed_at: string | null
}

export type AgentType = "tech_specialist" | "trajectory_specialist" | "behavioral_specialist"

export interface AgentReview {
  id: string
  agent_type: AgentType
  score: number
  pros: string[]
  cons: string[]
  rationale: string | null
  created_at: string
}

export interface JobResultItem {
  candidate_id: string
  candidate_name: string
  current_title: string | null
  retrieval_score: number | null
  retrieval_method: string | null
  rule_composite_score: number | null
  consensus_score: number | null
  final_rank: number | null
  executive_summary: string | null
  agent_reviews: AgentReview[]
}

export interface JobResultsResponse {
  job_id: string
  status: JobStatus
  role_title: string | null
  total_candidates: number
  disqualified_count: number
  shortlisted_count: number
  results: JobResultItem[]
}

// ── API error shape ──────────────────────────────────────────────────────

export interface ApiError {
  detail: string | { msg: string; loc: string[] }[]
}
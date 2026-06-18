// hooks/useJobPolling.ts
// ─────────────────────────
// Polls GET /jobs/{id} on an interval until the job reaches a terminal
// state (completed | failed). Backs off slightly as the job runs longer
// so a long-running evaluation doesn't hammer the API every second for
// twenty minutes straight.

import { useCallback, useEffect, useRef, useState } from "react"

import { apiClient, extractErrorMessage } from "@/api/client"
import type { JobStatusResponse } from "@/types"

const POLL_INTERVAL_MS = 2_000
const MAX_POLL_INTERVAL_MS = 8_000
const BACKOFF_AFTER_POLLS = 10

interface UseJobPollingResult {
  job: JobStatusResponse | null
  error: string | null
  isPolling: boolean
}

export function useJobPolling(jobId: string | null): UseJobPollingResult {
  const [job, setJob] = useState<JobStatusResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [isPolling, setIsPolling] = useState(false)

  const pollCountRef = useRef(0)
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const cancelledRef = useRef(false)

  const poll = useCallback(async (id: string) => {
    if (cancelledRef.current) return

    try {
      const { data } = await apiClient.get<JobStatusResponse>(`/jobs/${id}`)
      if (cancelledRef.current) return

      setJob(data)
      setError(null)
      pollCountRef.current += 1

      if (data.status === "completed" || data.status === "failed") {
        setIsPolling(false)
        return
      }

      const interval = Math.min(
        POLL_INTERVAL_MS + Math.max(0, pollCountRef.current - BACKOFF_AFTER_POLLS) * 500,
        MAX_POLL_INTERVAL_MS
      )
      timeoutRef.current = setTimeout(() => poll(id), interval)
    } catch (e) {
      if (cancelledRef.current) return
      setError(extractErrorMessage(e))
      setIsPolling(false)
    }
  }, [])

  useEffect(() => {
    cancelledRef.current = false
    pollCountRef.current = 0

    if (!jobId) {
      setJob(null)
      setError(null)
      setIsPolling(false)
      return
    }

    setIsPolling(true)
    poll(jobId)

    return () => {
      cancelledRef.current = true
      if (timeoutRef.current) clearTimeout(timeoutRef.current)
    }
  }, [jobId, poll])

  return { job, error, isPolling }
}
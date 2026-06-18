"""
pipeline/agents/panel.py
────────────────────────────
Orchestrates Stage 2 (specialist panel) and Stage 3 (arbitration).

Stage 2: the shortlist is split into batches. For each batch, the three
specialist agents run CONCURRENTLY (asyncio.gather) — not sequentially —
since they're independent lenses on the same data. Bounded concurrency
across batches keeps total in-flight API calls reasonable.

Stage 3: once every candidate has all three specialist reviews, the
arbitrator runs in its own batches (see arbitrator.py) to produce the
final consensus score and executive summary.
"""

import asyncio

from app.pipeline.agents.arbitrator import ArbitratorVerdict, run_arbitrator
from app.pipeline.agents.base import AgentReviewResult
from app.pipeline.agents.behavioral_specialist import run_behavioral_specialist
from app.pipeline.agents.tech_specialist import run_tech_specialist
from app.pipeline.agents.trajectory_specialist import run_trajectory_specialist
from app.pipeline.jd_analyzer import JDSignals
from app.logging_conf import get_logger

logger = get_logger(__name__)

SPECIALIST_BATCH_SIZE = 10   # candidates per specialist call
MAX_CONCURRENT_BATCHES = 4   # bounded concurrency across specialist batches


class PanelResult:
    def __init__(self):
        # candidate_id -> {agent_key: AgentReviewResult}
        self.specialist_reviews: dict[str, dict[str, AgentReviewResult]] = {}
        # candidate_id -> ArbitratorVerdict
        self.verdicts: dict[str, ArbitratorVerdict] = {}


async def _run_specialist_batch(
    jd_signals: JDSignals, batch: list[dict]
) -> dict[str, dict[str, AgentReviewResult]]:
    """Run all 3 specialists concurrently for one batch of candidates."""
    tech_task = asyncio.to_thread(run_tech_specialist, jd_signals, batch)
    trajectory_task = asyncio.to_thread(run_trajectory_specialist, jd_signals, batch)
    behavioral_task = asyncio.to_thread(run_behavioral_specialist, jd_signals, batch)

    tech_results, trajectory_results, behavioral_results = await asyncio.gather(
        tech_task, trajectory_task, behavioral_task
    )

    merged: dict[str, dict[str, AgentReviewResult]] = {}
    for c in batch:
        cid = str(c.get("candidate_id", ""))
        merged[cid] = {
            "tech_specialist": tech_results.get(cid),
            "trajectory_specialist": trajectory_results.get(cid),
            "behavioral_specialist": behavioral_results.get(cid),
        }
    return merged


async def run_specialist_panel(
    jd_signals: JDSignals,
    shortlisted_candidates: list[dict],
    progress_callback=None,
) -> dict[str, dict[str, AgentReviewResult]]:
    """
    Runs the full specialist panel (Stage 2) across the shortlist.
    progress_callback(completed, total), if provided, is called after
    each batch finishes — used to update Job.progress_pct.
    """
    batches = [
        shortlisted_candidates[i : i + SPECIALIST_BATCH_SIZE]
        for i in range(0, len(shortlisted_candidates), SPECIALIST_BATCH_SIZE)
    ]

    semaphore = asyncio.Semaphore(MAX_CONCURRENT_BATCHES)
    all_reviews: dict[str, dict[str, AgentReviewResult]] = {}
    completed = 0

    async def _bounded_batch(batch: list[dict]):
        nonlocal completed
        async with semaphore:
            result = await _run_specialist_batch(jd_signals, batch)
            completed_local = len(batch)
            return result, completed_local

    tasks = [_bounded_batch(b) for b in batches]
    for coro in asyncio.as_completed(tasks):
        result, n = await coro
        all_reviews.update(result)
        completed += n
        if progress_callback:
            progress_callback(completed, len(shortlisted_candidates))

    logger.info("specialist_panel.complete", candidates=len(all_reviews))
    return all_reviews


def run_panel_pipeline(
    jd_signals: JDSignals,
    shortlisted_candidates: list[dict],
    progress_callback=None,
) -> PanelResult:
    """
    Synchronous entrypoint (called from the Celery task, which is sync).
    Runs Stage 2 (concurrent specialist panel) then Stage 3 (arbitration).
    """
    result = PanelResult()

    result.specialist_reviews = asyncio.run(
        run_specialist_panel(jd_signals, shortlisted_candidates, progress_callback)
    )

    candidate_reviews_for_arbitrator = [
        (
            str(c.get("candidate_id", "")),
            c.get("profile", {}).get("anonymized_name", "Unknown"),
            {k: v for k, v in result.specialist_reviews.get(str(c.get("candidate_id", "")), {}).items() if v},
        )
        for c in shortlisted_candidates
    ]

    result.verdicts = run_arbitrator(jd_signals, candidate_reviews_for_arbitrator)

    return result

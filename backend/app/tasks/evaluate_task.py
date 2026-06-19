"""
tasks/evaluate_task.py
─────────────────────────
The core background task. Given a Job (JD + scope of candidates to
consider), runs:

  Stage 1: JD analysis -> retrieval filter (hybrid dense+sparse, adaptive shortlist)
  Stage 2: 3 specialist agents in parallel across the shortlist
  Stage 3: Arbitrator reconciles into final consensus score + summary

Progress is written to the Job row after each stage so the API's
GET /jobs/{id} can report live status to a polling frontend.
"""

import uuid
from datetime import datetime, timezone

from app.celery_app import celery_app
from app.db.models.agent_review import AgentReview, AgentType
from app.db.models.candidate import Candidate
from app.db.models.job import Job, JobStage, JobStatus
from app.db.models.job_result import JobResult
from app.db.session import SessionLocal
from app.logging_conf import get_logger
from app.pipeline.agents.panel import run_panel_pipeline
from app.pipeline.jd_analyzer import analyze_jd
from app.pipeline.retrieval import run_retrieval_filter

logger = get_logger(__name__)

_AGENT_TYPE_MAP = {
    "tech_specialist": AgentType.TECH_SPECIALIST,
    "trajectory_specialist": AgentType.TRAJECTORY_SPECIALIST,
    "behavioral_specialist": AgentType.BEHAVIORAL_SPECIALIST,
}


def _update_job(db, job: Job, **fields) -> None:
    for k, v in fields.items():
        setattr(job, k, v)
    db.commit()


@celery_app.task(name="evaluate_job", bind=True)
def evaluate_job_task(self, job_id: str) -> dict:
    db = SessionLocal()

    try:
        job = db.get(Job, uuid.UUID(job_id))
        if not job:
            logger.error("evaluate_job.not_found", job_id=job_id)
            return {"error": "job not found"}

        _update_job(
            db, job,
            status=JobStatus.RUNNING,
            started_at=datetime.now(timezone.utc),
            current_stage=JobStage.ANALYZING_JD,
            progress_pct=5,
            status_message="Analyzing job description...",
        )

        # ── Stage 1a: JD analysis ────────────────────────────────────────
        try:
            jd_signals = analyze_jd(job.jd_text)
        except Exception as e:
            _update_job(
                db, job,
                status=JobStatus.FAILED,
                error_message=str(e),
                status_message="Job description analysis failed",
            )
            return {"error": str(e)}

        _update_job(
            db, job,
            jd_signals=jd_signals.model_dump(),
            progress_pct=15,
            status_message=f"Role understood: {jd_signals.role_title}",
        )

        # ── Load candidate pool for this job ────────────────────────────
        candidate_rows = (
            db.query(Candidate)
            .filter(Candidate.pool_id == job.candidate_pool_id)
            .all()
        )
        total_candidates = len(candidate_rows)

        if total_candidates == 0:
            _update_job(
                db, job,
                status=JobStatus.FAILED,
                error_message="No candidates found. Upload candidates before running an evaluation.",
            )
            return {"error": "no candidates"}

        candidate_dicts = [row.profile_data for row in candidate_rows]
        # Map external candidate_id (used throughout the pipeline) -> DB row
        candidate_by_ext_id = {
            row.profile_data.get("candidate_id"): row for row in candidate_rows
        }

        _update_job(
            db, job,
            current_stage=JobStage.RETRIEVAL_FILTER,
            total_candidates=total_candidates,
            progress_pct=20,
            status_message=f"Running strict retrieval filter on {total_candidates:,} candidates...",
        )

        # ── Stage 1b/c/d: hybrid retrieval ───────────────────────────────
        retrieval_result = run_retrieval_filter(job.jd_text, jd_signals, candidate_dicts, job.owner_id)

        shortlist = retrieval_result["shortlist"]
        disqualified = retrieval_result["disqualified"]

        _update_job(
            db, job,
            disqualified_count=len(disqualified),
            shortlisted_count=len(shortlist),
            current_stage=JobStage.SPECIALIST_PANEL,
            progress_pct=35,
            status_message=f"Shortlisted {len(shortlist)} of {total_candidates:,} for specialist review",
        )

        if not shortlist:
            _update_job(
                db, job,
                status=JobStatus.COMPLETED,
                current_stage=JobStage.DONE,
                progress_pct=100,
                completed_at=datetime.now(timezone.utc),
                status_message="No candidates passed the qualification filters.",
            )
            return {"shortlisted": 0, "disqualified": len(disqualified)}

        shortlisted_candidate_dicts = [c for c, _, _, _, _ in shortlist]

        # ── Stage 2 + 3: specialist panel + arbitration ──────────────────
        def _progress_cb(completed: int, total: int) -> None:
            pct = 35 + int((completed / max(total, 1)) * 45)  # 35 -> 80
            _update_job(
                db, job,
                progress_pct=pct,
                status_message=f"Specialist panel reviewing candidates ({completed}/{total})...",
            )

        panel_result = run_panel_pipeline(jd_signals, shortlisted_candidate_dicts, _progress_cb)

        _update_job(
            db, job,
            current_stage=JobStage.ARBITRATION,
            progress_pct=85,
            status_message="Arbitrator finalising consensus rankings...",
        )

        # ── Persist results ───────────────────────────────────────────────
        final_results = []
        for c, flags, rule_score, retrieval_score, retrieval_method in shortlist:
            ext_id = c.get("candidate_id")
            candidate_row = candidate_by_ext_id.get(ext_id)
            if not candidate_row:
                continue

            verdict = panel_result.verdicts.get(ext_id)
            reviews = panel_result.specialist_reviews.get(ext_id, {})

            job_result = JobResult(
                id=uuid.uuid4(),
                job_id=job.id,
                candidate_id=candidate_row.id,
                candidate_name=flags["name"],
                current_title=flags["current_title"],
                retrieval_score=retrieval_score,
                retrieval_method=retrieval_method,
                rule_composite_score=rule_score["composite_score"],
                consensus_score=verdict.consensus_score if verdict else None,
                strengths=verdict.strengths if verdict else [],
                risks=verdict.risks if verdict else [],
                alternatives=verdict.alternatives if verdict else [],
                is_disqualified=False,
            )
            db.add(job_result)
            db.flush()  # get job_result.id before adding child agent_reviews

            for agent_key, review in reviews.items():
                if not review:
                    continue
                db.add(AgentReview(
                    id=uuid.uuid4(),
                    job_result_id=job_result.id,
                    agent_type=_AGENT_TYPE_MAP[agent_key],
                    score=review.score,
                    pros=review.pros,
                    cons=review.cons,
                    rationale=review.rationale,
                ))

            final_results.append((job_result, verdict.consensus_score if verdict else 0))

        # Rank by consensus score
        final_results.sort(key=lambda x: x[1], reverse=True)
        for rank, (job_result, _) in enumerate(final_results, start=1):
            job_result.final_rank = rank

        # Persist disqualified candidates too, for transparency
        for c, flags, rule_score in disqualified:
            ext_id = c.get("candidate_id")
            candidate_row = candidate_by_ext_id.get(ext_id)
            if not candidate_row:
                continue
            db.add(JobResult(
                id=uuid.uuid4(),
                job_id=job.id,
                candidate_id=candidate_row.id,
                candidate_name=flags["name"],
                current_title=flags["current_title"],
                is_disqualified=True,
                disqualify_reason=rule_score["disqualify_reason"],
            ))

        _update_job(
            db, job,
            status=JobStatus.COMPLETED,
            current_stage=JobStage.DONE,
            progress_pct=100,
            completed_at=datetime.now(timezone.utc),
            status_message="Evaluation complete.",
        )

        logger.info(
            "evaluate_job.complete",
            job_id=job_id,
            shortlisted=len(shortlist),
            disqualified=len(disqualified),
        )

        return {
            "shortlisted": len(shortlist),
            "disqualified": len(disqualified),
            "total": total_candidates,
        }

    except Exception as e:
        db.rollback()
        logger.error("evaluate_job.failed", job_id=job_id, error=str(e))
        try:
            job = db.get(Job, uuid.UUID(job_id))
            if job:
                _update_job(db, job, status=JobStatus.FAILED, error_message=str(e))
        except Exception:
            pass
        raise
    finally:
        db.close()
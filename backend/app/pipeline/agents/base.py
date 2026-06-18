"""
pipeline/agents/base.py
──────────────────────────
Shared infrastructure for all specialist agents and the arbitrator.
Every agent call goes through `call_agent()` so retry behaviour,
response parsing, and error handling are consistent and only
implemented once.
"""

import json
import re

import google.generativeai as genai
from pydantic import BaseModel
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import get_settings
from app.core.exceptions import PipelineError
from app.logging_conf import get_logger

settings = get_settings()
logger = get_logger(__name__)

genai.configure(api_key=settings.gemini_api_key)

AGENT_MODEL = genai.GenerativeModel("gemini-2.5-flash")


class AgentReviewResult(BaseModel):
    candidate_id: str
    agent_name: str
    score: float
    pros: list[str]
    cons: list[str]
    rationale: str


def _strip_fences(raw: str) -> str:
    raw = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.MULTILINE)
    raw = re.sub(r"\s*```$", "", raw, flags=re.MULTILINE)
    return raw.strip()


def _call_llm(prompt: str, max_tokens: int = 2048) -> str:
    response = AGENT_MODEL.generate_content(
        prompt,
        generation_config={
            "temperature": 0.2,
            "response_mime_type": "application/json",
        },
    )

    return response.text


def call_agent_batch(
    prompt: str,
    agent_name: str,
    expected_ids: list[str],
    max_tokens: int = 4096,
) -> dict[str, AgentReviewResult]:
    """
    Calls Claude with a prompt covering multiple candidates and parses
    a JSON array of per-candidate reviews. On any failure, returns
    neutral fallback reviews for all expected_ids rather than raising —
    one batch failing should never crash the whole evaluation job.
    """
    try:
        raw = _call_llm(prompt, max_tokens=max_tokens)
        cleaned = _strip_fences(raw)
        data = json.loads(cleaned)
        reviews = data.get("reviews", data if isinstance(data, list) else [])

        result: dict[str, AgentReviewResult] = {}
        for item in reviews:
            cid = str(item.get("candidate_id", ""))
            if cid not in expected_ids:
                continue
            result[cid] = AgentReviewResult(
                candidate_id=cid,
                agent_name=agent_name,
                score=float(item.get("score", 50.0)),
                pros=list(item.get("pros", []))[:5],
                cons=list(item.get("cons", []))[:5],
                rationale=str(item.get("rationale", ""))[:500],
            )

        # Fill in fallback for anything Claude skipped
        for cid in expected_ids:
            if cid not in result:
                result[cid] = _fallback_review(cid, agent_name)

        return result

    except Exception as e:
        logger.error("agent_batch_failed", agent=agent_name, error=str(e))
        return {cid: _fallback_review(cid, agent_name) for cid in expected_ids}


def _fallback_review(candidate_id: str, agent_name: str) -> AgentReviewResult:
    return AgentReviewResult(
        candidate_id=candidate_id,
        agent_name=agent_name,
        score=50.0,
        pros=[],
        cons=["Agent evaluation unavailable — neutral score assigned"],
        rationale="This candidate could not be evaluated by this agent due to a processing error.",
    )

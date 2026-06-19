"""
pipeline/jd_analyzer.py
─────────────────────────
Calls Claude once on any JD text and returns a fully structured
JDSignals object that drives ALL downstream scoring and agent prompts.

Nothing about skills, experience range, disqualifiers, or dimension
weights is hardcoded — every evaluation run derives them fresh from
whatever JD was submitted.

BUG FIX (critical): the original implementation used str.format() on a
prompt template that contained literal JSON braces in its instructions.
.format() tries to interpret every {...} as a field reference, which
raised `KeyError: '\\n  "role_title"'` on every call. Fixed by using
.replace() on a single placeholder token instead of .format().
"""

import json
import re

import google.generativeai as genai
from pydantic import BaseModel, Field
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import get_settings
from app.core.exceptions import PipelineError
from app.logging_conf import get_logger

settings = get_settings()
logger = get_logger(__name__)

genai.configure(api_key=settings.gemini_api_key)

MODEL = genai.GenerativeModel(settings.gemini_panel_model)


class JDSignals(BaseModel):
    role_title: str = ""
    domain: str = "other"
    seniority: str = "mid"

    exp_min: int = 2
    exp_max: int = 15

    skill_weights: dict[str, int] = Field(default_factory=dict)
    bad_title_keywords: list[str] = Field(default_factory=list)
    requires_product_co: bool = False

    dim_weights: dict[str, float] = Field(
        default_factory=lambda: {
            "skills": 0.40,
            "career": 0.25,
            "activity": 0.20,
            "experience": 0.10,
            "platform": 0.05,
        }
    )

    ideal_candidate_summary: str = ""

    # Recruiter-intent qualitative signals — used by trajectory + behavioral agents
    company_stage: str = "unknown"          # seed | early | growth | scale | enterprise | unknown
    ownership_weight: float = 0.5           # 0.0–1.0: how much independent ownership matters
    leadership_weight: float = 0.5          # 0.0–1.0: IC-only vs expected to lead/mentor
    red_flags: list[str] = Field(default_factory=list)  # resume signals that should raise concern


# NOTE: This template contains literal JSON braces. It is rendered with
# str.replace("__JD_TEXT__", jd_text) — NEVER with str.format() or an
# f-string, both of which would choke on the literal braces below.
_EXTRACTION_PROMPT = """You are a senior technical recruiter with deep domain expertise across engineering,
design, product, finance, legal, and operations roles.

Analyze the job description below and return a JSON object with EXACTLY these fields.
No markdown, no explanation — raw JSON only.

{
  "role_title": "exact title from JD",
  "domain": "one of: software_engineering | machine_learning | data_engineering | data_science | frontend | mobile | devops | design | product | finance | legal | operations | sales | marketing | hr | other",
  "seniority": "one of: intern | junior | mid | senior | lead | principal | executive",
  "exp_min": <integer years, 0 if not stated>,
  "exp_max": <integer years, 99 if no upper bound>,
  "skill_weights": {
    "<exact skill name as it would appear on a resume>": <integer 1-10>
  },
  "bad_title_keywords": [
    "<job title word that would indicate a completely irrelevant candidate>"
  ],
  "requires_product_co": <true | false>,
  "dim_weights": {
    "skills": <float>,
    "career": <float>,
    "activity": <float>,
    "experience": <float>,
    "platform": <float>
  },
  "ideal_candidate_summary": "<3-5 sentences describing the ideal hire: background, depth, what they've shipped, what makes them stand out>",
  "company_stage": "one of: seed | early | growth | scale | enterprise | unknown",
  "ownership_weight": <float 0.0-1.0 — how critical is independent ownership vs guided execution>,
  "leadership_weight": <float 0.0-1.0 — 0.0 means pure IC, 1.0 means must lead teams or mentor>,
  "red_flags": [
    "<resume signal that should raise recruiter concern for THIS specific role>"
  ]
}

Rules for skill_weights:
- Include 15-40 skills depending on role breadth.
- Weight 9-10: must-have, candidate is a non-starter without this.
- Weight 7-8: strongly preferred, differentiates strong vs weak candidates.
- Weight 4-6: nice-to-have, adds score but absence doesn't disqualify.
- Weight 1-3: tangential, minor positive signal.
- Use the exact canonical name (e.g. "PyTorch" not "pytorch", "React" not "ReactJS").

Rules for dim_weights:
- Must sum to exactly 1.0.
- skills weight should be higher for technical IC roles.
- career weight should be higher when company pedigree/education matters.
- activity weight should be higher when urgency to hire is mentioned.
- experience weight should be higher when a specific band is critical.
- platform weight stays low (0.03-0.08) unless the JD is from a platform that tracks engagement.

Rules for bad_title_keywords:
- Only include titles that are genuinely irrelevant to this role.
- Do NOT include titles that could be a career transition (e.g. "data analyst" for an ML role).
- Keep list tight - false disqualifications are worse than false inclusions.

JOB DESCRIPTION:
\"\"\"
__JD_TEXT__
\"\"\"
"""


def _build_prompt(jd_text: str) -> str:
    # .replace(), not .format()/f-string — the template above has literal
    # JSON braces that would break str.format()'s field-reference parsing.
    return _EXTRACTION_PROMPT.replace("__JD_TEXT__", jd_text.strip())


def _strip_markdown_fences(raw: str) -> str:
    raw = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.MULTILINE)
    raw = re.sub(r"\s*```$", "", raw, flags=re.MULTILINE)
    return raw.strip()


def _normalise_dim_weights(dw: dict) -> dict:
    if not dw:
        return JDSignals().dim_weights
    total = sum(dw.values()) or 1.0
    return {k: round(v / total, 4) for k, v in dw.items()}


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def _call_llm(prompt: str) -> str:
    response = MODEL.generate_content(
        prompt,
        generation_config={
            "temperature": 0.1,
            "response_mime_type": "application/json",
        },
    )

    return response.text


def analyze_jd(jd_text: str) -> JDSignals:
    """
    Parse any job description into structured scoring signals.
    Raises PipelineError if Claude's response can't be parsed after retries.
    """
    if not jd_text or len(jd_text.strip()) < 30:
        raise PipelineError("Job description is too short to analyze")

    prompt = _build_prompt(jd_text)

    try:
        raw = _call_llm(prompt)
    except Exception as e:
        import traceback
        logger.error(
            "jd_analyzer.llm_call_failed",
            error=repr(e),
            traceback=traceback.format_exc(),
        )
        raise

    cleaned = _strip_markdown_fences(raw)

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        logger.error("jd_analyzer.json_parse_failed", error=str(e), raw=cleaned[:500])
        raise PipelineError(f"JD analysis failed: malformed response from model ({e})")

    skill_weights = {k.lower(): int(v) for k, v in data.get("skill_weights", {}).items()}
    bad_titles = [t.lower() for t in data.get("bad_title_keywords", [])]
    dim_weights = _normalise_dim_weights(data.get("dim_weights", {}))

    signals = JDSignals(
        role_title=data.get("role_title", "Untitled Role"),
        domain=data.get("domain", "other"),
        seniority=data.get("seniority", "mid"),
        exp_min=int(data.get("exp_min", 2)),
        exp_max=int(data.get("exp_max", 15)),
        skill_weights=skill_weights,
        bad_title_keywords=bad_titles,
        requires_product_co=bool(data.get("requires_product_co", False)),
        dim_weights=dim_weights,
        ideal_candidate_summary=data.get("ideal_candidate_summary", ""),
        company_stage=data.get("company_stage", "unknown"),
        ownership_weight=float(data.get("ownership_weight", 0.5)),
        leadership_weight=float(data.get("leadership_weight", 0.5)),
        red_flags=[str(r).lower() for r in data.get("red_flags", [])],
    )

    logger.info(
        "jd_analyzer.success",
        role_title=signals.role_title,
        domain=signals.domain,
        skill_count=len(signals.skill_weights),
    )
    return signals
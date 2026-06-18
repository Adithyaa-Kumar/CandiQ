"""
pipeline/ingest.py
────────────────────
Accepts candidate data in any format and normalises it to the
internal candidate dict schema used by parse_candidates.get_career_flags().

Supported inputs
────────────────
  • .json / .jsonl  — structured candidate objects (any reasonable shape)
  • .csv            — tabular: one row per candidate, flexible column names
  • .pdf / .docx     — résumé files: each file = one candidate
  • plain text       — pasted résumé text or raw JSON/JSONL
"""

import csv
import io
import json
import re
import uuid
from pathlib import Path

from app.core.exceptions import InvalidInputError


# ─────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────

def load_candidates(raw_bytes: bytes, filename: str) -> list[dict]:
    """Entry point for file uploads."""
    ext = Path(filename).suffix.lower()

    try:
        if ext in (".json", ".jsonl") or _looks_like_json(raw_bytes):
            return _from_json(raw_bytes)
        if ext == ".csv":
            return _from_csv(raw_bytes)
        if ext == ".pdf":
            return _from_pdf_bytes(raw_bytes)
        if ext in (".docx", ".doc"):
            return _from_docx_bytes(raw_bytes)
        return _from_plaintext(raw_bytes.decode("utf-8", errors="replace"))
    except InvalidInputError:
        raise
    except Exception as e:
        raise InvalidInputError(f"Could not parse '{filename}': {e}")


def load_candidates_from_text(text: str) -> list[dict]:
    """Entry point for pasted textarea input."""
    stripped = text.strip()
    if not stripped:
        raise InvalidInputError("Candidate text is empty")

    if stripped.startswith("[") or stripped.startswith("{"):
        try:
            return _from_json(stripped.encode())
        except Exception:
            pass
    return _from_plaintext(stripped)


# ─────────────────────────────────────────────────────────────
# Format parsers
# ─────────────────────────────────────────────────────────────

def _from_json(raw: bytes) -> list[dict]:
    text = raw.decode("utf-8", errors="replace").strip()
    if text.startswith("["):
        candidates = json.loads(text)
    else:
        candidates = []
        for line in text.splitlines():
            line = line.strip()
            if line:
                candidates.append(json.loads(line))

    if not isinstance(candidates, list):
        candidates = [candidates]

    return [_normalise(c) for c in candidates if isinstance(c, dict)]


def _from_csv(raw: bytes) -> list[dict]:
    text = raw.decode("utf-8", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    return [_csv_row_to_candidate({k.strip().lower(): (v or "").strip() for k, v in row.items() if k})
            for row in reader]


def _from_pdf_bytes(raw: bytes) -> list[dict]:
    try:
        import pypdf
        reader = pypdf.PdfReader(io.BytesIO(raw))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception:
        text = raw.decode("utf-8", errors="replace")
    return [_resume_text_to_candidate(text)]


def _from_docx_bytes(raw: bytes) -> list[dict]:
    try:
        import docx
        doc = docx.Document(io.BytesIO(raw))
        text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    except Exception:
        text = raw.decode("utf-8", errors="replace")
    return [_resume_text_to_candidate(text)]


def _from_plaintext(text: str) -> list[dict]:
    """Multiple résumés separated by a line of ---- or ====."""
    blocks = re.split(r"\n[-=]{5,}\n", text)
    candidates = [
        _resume_text_to_candidate(b.strip())
        for b in blocks if len(b.strip()) > 100
    ]
    return candidates if candidates else [_resume_text_to_candidate(text)]


# ─────────────────────────────────────────────────────────────
# Schema normalisation
# ─────────────────────────────────────────────────────────────

def _normalise(c: dict) -> dict:
    profile = c.get("profile", {})
    signals = c.get("redrob_signals", {})

    if not profile and any(k in c for k in ("name", "title", "years_of_experience")):
        profile = {
            "anonymized_name": c.get("name", c.get("full_name", "Unknown")),
            "headline": c.get("headline", c.get("title", "")),
            "summary": c.get("summary", c.get("bio", c.get("about", ""))),
            "location": c.get("location", ""),
            "country": c.get("country", ""),
            "years_of_experience": _safe_float(
                c.get("years_of_experience", c.get("yoe", c.get("experience_years", 0)))
            ),
            "current_title": c.get("current_title", c.get("title", "")),
            "current_company": c.get("current_company", c.get("company", "")),
            "current_company_size": c.get("company_size", ""),
            "current_industry": c.get("industry", ""),
        }
        # Flat schema has no career_history array — synthesize a single
        # current-role entry from the top-level company/title so company-type
        # checks (has_product_co, is_consulting_only) actually have data to work with.
        if not c.get("career_history") and (profile["current_company"] or profile["current_title"]):
            c["career_history"] = [{
                "company": profile["current_company"],
                "title": profile["current_title"],
                "start_date": "", "end_date": None,
                "duration_months": int(profile["years_of_experience"] * 12),
                "is_current": True,
                "industry": profile["current_industry"],
                "company_size": profile["current_company_size"],
                "description": profile["summary"],
            }]

    c.setdefault("candidate_id", f"CAND_{uuid.uuid4().hex[:8].upper()}")
    c["profile"] = {
        "anonymized_name": profile.get("anonymized_name", profile.get("name", "Unknown")),
        "headline": profile.get("headline", ""),
        "summary": profile.get("summary", ""),
        "location": profile.get("location", ""),
        "country": profile.get("country", ""),
        "years_of_experience": _safe_float(profile.get("years_of_experience", 0)),
        "current_title": profile.get("current_title", ""),
        "current_company": profile.get("current_company", ""),
        "current_company_size": profile.get("current_company_size", ""),
        "current_industry": profile.get("current_industry", ""),
    }

    c.setdefault("career_history", [])
    c.setdefault("education", [])
    c["skills"] = _normalise_skills(c.get("skills", []))

    c["redrob_signals"] = {
        "last_active_date": signals.get("last_active_date", ""),
        "notice_period_days": _safe_int(signals.get("notice_period_days", 90)),
        "open_to_work_flag": bool(signals.get("open_to_work_flag", False)),
        "recruiter_response_rate": _safe_float(signals.get("recruiter_response_rate", 0)),
        "github_activity_score": _safe_float(signals.get("github_activity_score", 0)),
        "profile_completeness_score": _safe_float(signals.get("profile_completeness_score", 50)),
        "interview_completion_rate": _safe_float(signals.get("interview_completion_rate", 0)),
        "skill_assessment_scores": signals.get("skill_assessment_scores", {}),
        "saved_by_recruiters_30d": _safe_int(signals.get("saved_by_recruiters_30d", 0)),
        "profile_views_received_30d": _safe_int(signals.get("profile_views_received_30d", 0)),
    }
    return c


def _normalise_skills(skills: list) -> list[dict]:
    normalised = []
    for s in skills:
        if isinstance(s, str):
            normalised.append({"name": s, "proficiency": "unknown", "endorsements": 0, "duration_months": 0})
        elif isinstance(s, dict):
            normalised.append({
                "name": s.get("name", ""),
                "proficiency": s.get("proficiency", "unknown"),
                "endorsements": _safe_int(s.get("endorsements", 0)),
                "duration_months": _safe_int(s.get("duration_months", 0)),
            })
    return [s for s in normalised if s["name"]]


def _csv_row_to_candidate(row: dict) -> dict:
    def get(*keys):
        for k in keys:
            if k in row and row[k]:
                return row[k]
        return ""

    skills_raw = get("skills", "skill_list", "technologies", "tech_stack")
    skills = [s.strip() for s in re.split(r"[,;|]", skills_raw) if s.strip()]

    career_history = []
    company = get("current_company", "company", "employer", "organization")
    title = get("current_title", "title", "role", "position", "job_title")
    if company or title:
        career_history.append({
            "company": company, "title": title,
            "start_date": get("start_date", "from"), "end_date": None,
            "duration_months": _safe_int(get("tenure_months", "duration_months", "months")),
            "is_current": True,
            "industry": get("industry", "sector", ""),
            "company_size": get("company_size", "org_size", ""),
            "description": get("description", "role_description", "responsibilities", ""),
        })

    edu = []
    institution = get("institution", "university", "college", "school", "alma_mater")
    if institution:
        edu.append({
            "institution": institution,
            "degree": get("degree", "qualification", ""),
            "field_of_study": get("field_of_study", "major", "specialization", ""),
            "start_year": _safe_int(get("edu_start", "0")),
            "end_year": _safe_int(get("edu_end", "grad_year", "graduation_year", "0")),
            "grade": get("gpa", "grade", "cgpa", ""),
            "tier": get("edu_tier", "institution_tier", "tier_4"),
        })

    return _normalise({
        "candidate_id": get("candidate_id", "id", "cand_id") or f"CAND_{uuid.uuid4().hex[:8].upper()}",
        "profile": {
            "anonymized_name": get("name", "full_name", "candidate_name", "anonymized_name") or "Unknown",
            "headline": get("headline", "tagline") or title,
            "summary": get("summary", "bio", "about", "profile_summary", "overview"),
            "location": get("location", "city", "region"),
            "country": get("country"),
            "years_of_experience": _safe_float(get("years_of_experience", "yoe", "experience_years", "experience")),
            "current_title": title,
            "current_company": company,
            "current_company_size": get("company_size", ""),
            "current_industry": get("industry", ""),
        },
        "career_history": career_history,
        "education": edu,
        "skills": [{"name": s, "proficiency": "unknown", "endorsements": 0, "duration_months": 0} for s in skills],
        "redrob_signals": {
            "last_active_date": get("last_active_date", "last_active", ""),
            "notice_period_days": _safe_int(get("notice_period_days", "notice_period", "notice") or "90"),
            "open_to_work_flag": get("open_to_work", "available", "actively_looking", "").lower() in ("true", "yes", "1"),
            "recruiter_response_rate": _safe_float(get("recruiter_response_rate", "response_rate") or "0"),
            "github_activity_score": _safe_float(get("github_activity_score", "github_score") or "0"),
            "profile_completeness_score": _safe_float(get("profile_completeness_score", "profile_score") or "50"),
            "interview_completion_rate": _safe_float(get("interview_completion_rate", "interview_rate") or "0"),
            "skill_assessment_scores": {},
            "saved_by_recruiters_30d": _safe_int(get("saved_by_recruiters_30d", "saved_count") or "0"),
            "profile_views_received_30d": _safe_int(get("profile_views_received_30d", "profile_views") or "0"),
        },
    })


def _resume_text_to_candidate(text: str) -> dict:
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    name = lines[0] if lines else "Unknown"
    if name.lower() in ("resume", "curriculum vitae", "cv", "résumé"):
        name = lines[1] if len(lines) > 1 else "Unknown"

    yoe = 0.0
    yoe_match = re.search(r"(\d+(?:\.\d+)?)\s*\+?\s*years?(?:\s+of)?\s+experience", text, re.I)
    if yoe_match:
        yoe = float(yoe_match.group(1))

    skills = []
    skill_section = re.search(
        r"(?:skills?|technologies|technical\s+skills?|tech\s+stack)[:\s]*\n(.*?)(?:\n\n|\Z)",
        text, re.I | re.S,
    )
    if skill_section:
        raw_skills = re.split(r"[,•|·\n\t]+", skill_section.group(1))
        skills = [s.strip() for s in raw_skills if 2 < len(s.strip()) < 50]

    title = ""
    title_match = re.search(r"(?:title|position|role)[:\s]+([^\n]+)", text, re.I)
    if title_match:
        title = title_match.group(1).strip()

    location = ""
    loc_match = re.search(r"(?:location|city|based in)[:\s]+([^\n]+)", text, re.I)
    if loc_match:
        location = loc_match.group(1).strip()

    return _normalise({
        "candidate_id": f"CAND_{uuid.uuid4().hex[:8].upper()}",
        "profile": {
            "anonymized_name": name, "headline": title, "summary": text[:2000],
            "location": location, "country": "", "years_of_experience": yoe,
            "current_title": title, "current_company": "",
            "current_company_size": "", "current_industry": "",
        },
        "career_history": [{
            "company": "See résumé", "title": title, "start_date": "", "end_date": None,
            "duration_months": int(yoe * 12), "is_current": True,
            "industry": "", "company_size": "", "description": text[:3000],
        }],
        "education": [],
        "skills": [{"name": s, "proficiency": "unknown", "endorsements": 0, "duration_months": 0} for s in skills[:30]],
        "redrob_signals": {},
    })


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

def _looks_like_json(raw: bytes) -> bool:
    try:
        snippet = raw[:200].decode("utf-8", errors="replace").strip()
        return snippet.startswith("[") or snippet.startswith("{")
    except Exception:
        return False


def _safe_float(v) -> float:
    try:
        return float(str(v).replace(",", "").strip())
    except Exception:
        return 0.0


def _safe_int(v) -> int:
    try:
        return int(float(str(v).replace(",", "").strip()))
    except Exception:
        return 0

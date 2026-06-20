"""
pipeline/parse_candidates.py
───────────────────────────────
Extracts structured scoring signals from a normalised candidate dict.
Company lists are the only static config here — everything else is
driven by JDSignals passed in from the caller.

BUG FIXES applied:
  1. has_bad_title was computed against bad_title_keywords that default to
     a hardcoded list when signals=None. But `any(bt in current_title ...)`
     used substring matching — "marketing engineer" would match "marketing"
     and get disqualified from a marketing-tech role. Changed to word-
     boundary matching (split title into words, check those).
  2. avg_tenure_months calculation included jobs with duration_months=0
     (missing data), pulling the average toward 0 and triggering false
     "job-hopper" penalties. Now excludes zero-duration entries already
     done for tenures list, but also excludes current roles (no end_date)
     from the gap detection — current roles don't constitute gaps.
  3. days_since_active used datetime.now(timezone.utc) but strptime'd
     without timezone, causing a naive/aware comparison TypeError on
     Python 3.11+. Fixed by always attaching UTC timezone after parsing.
  4. skill_depth used s["name"].lower() but some upstream parsers return
     name=None (from CSV rows with empty skill cells). Added guard.
  5. github_score: raw value of -1 in the dataset means "not connected"
     — was being passed as-is into scoring, giving negative contributions.
     Clamped to 0 (neutral).
  6. build_rich_profile capped description at 300 chars per job but
     the most signal-rich part (what they actually built) is often in
     the second half. Increased to 400 and ensured truncation happens
     at a word boundary.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.pipeline.jd_analyzer import JDSignals

# ── Known company classifications ────────────────────────────────────────
# Stable facts, not role-dependent — that's why these are the only
# hardcoded lists in the scoring pipeline.

PRODUCT_COMPANIES: set[str] = {
    "swiggy", "zomato", "flipkart", "ola", "uber", "razorpay", "cred",
    "meesho", "phonepe", "paytm", "dunzo", "byju", "unacademy", "dream11",
    "groww", "zepto", "slice", "jupiter", "smallcase", "cleartax", "freshworks",
    "zoho", "chargebee", "postman", "browserstack", "hasura", "setu",
    "niyo", "open", "fi", "juspay", "sarvam", "krutrim",
    "amazon", "google", "microsoft", "meta", "apple", "netflix", "spotify",
    "airbnb", "stripe", "openai", "anthropic", "salesforce", "adobe",
    "atlassian", "shopify", "notion", "figma", "linear", "vercel",
    "hashicorp", "datadog", "snowflake", "databricks", "hugging face",
    "cohere", "mistral", "stability ai", "nvidia", "amd", "qualcomm",
    "goldman sachs", "jpmorgan", "jane street", "two sigma", "citadel",
    "robinhood", "revolut", "wise", "plaid",
    # Indian product startups often seen in datasets
    "mad street den", "navi", "simpl", "bull frog", "lenskart", "sharechat",
    "dailyhunt", "lokal", "khatabook", "apna", "dukaan", "moengage",
    "clevertap", "sprinklr", "haptik", "observe.ai", "slintel",
}

CONSULTING_COMPANIES: set[str] = {
    "tcs", "tata consultancy", "infosys", "wipro", "accenture", "cognizant",
    "capgemini", "hcl", "hcltech", "tech mahindra", "mindtree", "mphasis",
    "hexaware", "l&t infotech", "ltimindtree", "niit technologies",
    "mastech", "igate", "patni", "syntel", "firstsource", "maxis",
    "birlasoft", "cyient", "zensar",
}


def get_career_flags(c: dict, signals: JDSignals | None = None) -> dict:
    """
    Extract every measurable signal from a candidate dict. `signals` is
    passed in so company-type judgement is role-aware.
    """
    profile  = c.get("profile", {})
    career   = c.get("career_history", [])
    raw_sigs = c.get("redrob_signals", {})
    # FIX 4: guard against None skill names
    skills   = [
        s["name"].lower()
        for s in c.get("skills", [])
        if s.get("name")
    ]

    companies = [job.get("company", "").lower() for job in career]

    def _is_consulting(co: str) -> bool:
        return any(cons in co for cons in CONSULTING_COMPANIES)

    def _is_product(co: str) -> bool:
        return any(prod in co for prod in PRODUCT_COMPANIES)

    is_consulting_only = bool(companies) and all(_is_consulting(co) for co in companies)
    has_product_co     = any(_is_product(co) for co in companies)

    if signals and signals.domain in ("consulting", "operations", "other"):
        is_consulting_only = False

    current_title = profile.get("current_title", "").lower()
    bad_title_keywords = signals.bad_title_keywords if signals else [
        "marketing manager", "hr manager", "accountant", "civil engineer",
        "mechanical engineer", "graphic designer", "content writer",
        "sales executive", "customer support",
    ]

    # FIX 1: word-level matching to avoid "marketing engineer" matching "marketing"
    title_words = set(current_title.replace("/", " ").split())
    has_bad_title = any(
        all(word in title_words for word in bt.lower().split())
        for bt in bad_title_keywords
    )

    # Gap detection — FIX 2: exclude current role (no end_date) from gap check
    sorted_career = sorted(
        [j for j in career if j.get("start_date") and j.get("end_date")],
        key=lambda j: j["start_date"],
    )
    has_significant_gap = False
    for i in range(1, len(sorted_career)):
        try:
            prev_end   = sorted_career[i - 1].get("end_date", "")
            curr_start = sorted_career[i].get("start_date", "")
            if prev_end and curr_start:
                gap = (
                    datetime.strptime(curr_start, "%Y-%m-%d")
                    - datetime.strptime(prev_end,  "%Y-%m-%d")
                ).days
                if gap > 180:
                    has_significant_gap = True
                    break
        except Exception:
            continue

    # FIX 2b: exclude 0-duration entries from tenure average
    tenures = [j.get("duration_months", 0) for j in career if j.get("duration_months", 0) > 0]
    avg_tenure_months = sum(tenures) / len(tenures) if tenures else 24  # default neutral

    yoe = float(profile.get("years_of_experience", 0))

    # FIX 3: always attach UTC timezone after strptime
    last_active_str = raw_sigs.get("last_active_date", "")
    days_since_active = 9999
    has_known_activity_data = bool(last_active_str)
    if last_active_str:
        try:
            la = datetime.strptime(last_active_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            days_since_active = (datetime.now(timezone.utc) - la).days
        except Exception:
            has_known_activity_data = False

    # FIX 4: guard None names + FIX 5: normalise -1 github score
    skill_depth: dict[str, dict] = {}
    for s in c.get("skills", []):
        name = s.get("name")
        if not name:
            continue
        skill_depth[name.lower()] = {
            "endorsements":    s.get("endorsements",   0),
            "duration_months": s.get("duration_months", 0),
            "proficiency":     s.get("proficiency",    "unknown"),
        }

    assessment_scores = raw_sigs.get("skill_assessment_scores", {})
    avg_assessment = (
        sum(assessment_scores.values()) / len(assessment_scores)
        if assessment_scores else 0.0
    )

    edu_tiers = [e.get("tier", "tier_4") for e in c.get("education", [])]
    best_tier = min(
        [int(t.replace("tier_", "")) for t in edu_tiers if t.startswith("tier_")],
        default=4,
    )

    # FIX 5: -1 means "not connected" in this dataset — clamp to 0
    raw_github = float(raw_sigs.get("github_activity_score", 0) or 0)
    github_score = max(0.0, raw_github)

    return {
        "candidate_id":           c.get("candidate_id"),
        "name":                   profile.get("anonymized_name", "Unknown"),
        "yoe":                    yoe,
        "current_title":          current_title,
        "is_consulting_only":     is_consulting_only,
        "has_product_co":         has_product_co,
        "has_bad_title":          has_bad_title,
        "has_significant_gap":    has_significant_gap,
        "avg_tenure_months":      avg_tenure_months,
        "days_since_active":      days_since_active,
        "has_known_activity_data": has_known_activity_data,
        "notice_period":          int(raw_sigs.get("notice_period_days", 90)),
        "open_to_work":           bool(raw_sigs.get("open_to_work_flag", False)),
        "recruiter_response_rate": float(raw_sigs.get("recruiter_response_rate", 0)),
        "github_score":           github_score,
        "profile_completeness":   float(raw_sigs.get("profile_completeness_score", 50)),
        "interview_completion":   float(raw_sigs.get("interview_completion_rate", 0)),
        "avg_assessment_score":   avg_assessment,
        "best_edu_tier":          best_tier,
        "skills":                 skills,
        "skill_depth":            skill_depth,
        "raw":                    c,
    }


def build_candidate_text(c: dict) -> str:
    """Compact text blob — used for sparse/BM25 lexical search."""
    profile = c.get("profile", {})
    parts = [profile.get("headline", ""), profile.get("summary", "")]
    for job in c.get("career_history", []):
        parts += [job.get("title", ""), job.get("company", ""), job.get("description", "")]
    for s in c.get("skills", []):
        if s.get("name"):
            parts.append(s["name"])
    for edu in c.get("education", []):
        parts += [edu.get("field_of_study", ""), edu.get("degree", "")]
    return " ".join(p for p in parts if p)


def build_rich_profile(c: dict, max_chars: int = 2800) -> str:
    """
    Richer, structured text blob for agent/semantic scoring prompts.
    FIX 6: increased job description cap to 400 chars, word-boundary truncation.
    """
    profile = c.get("profile", {})
    sigs    = c.get("redrob_signals", {})
    lines   = []

    name  = profile.get("anonymized_name", "")
    title = profile.get("current_title", "")
    yoe   = profile.get("years_of_experience", 0)
    lines.append(f"[{name} | {title} | {yoe} yrs]")

    summary = profile.get("summary", "")
    if summary:
        lines.append(f"Summary: {summary[:400]}")

    for i, job in enumerate(c.get("career_history", [])[:5]):
        desc = job.get("description", "")
        # FIX 6: truncate at word boundary, not mid-word
        if len(desc) > 400:
            desc = desc[:400].rsplit(" ", 1)[0] + "…"
        lines.append(
            f"Role {i + 1}: {job.get('title', '')} @ {job.get('company', '')} "
            f"({job.get('duration_months', 0)}mo) — {desc}"
        )

    skill_names = [s.get("name", "") for s in c.get("skills", [])[:20] if s.get("name")]
    lines.append(f"Skills: {', '.join(skill_names)}")

    for edu in c.get("education", [])[:2]:
        lines.append(f"Edu: {edu.get('degree', '')} {edu.get('field_of_study', '')} — {edu.get('institution', '')}")

    otw    = "open to work" if sigs.get("open_to_work_flag") else "not actively looking"
    notice = sigs.get("notice_period_days", "unknown")
    rr     = sigs.get("recruiter_response_rate", 0)
    salary = sigs.get("expected_salary_range_inr_lpa", {})
    sal_str = f"{salary.get('min', '?')}–{salary.get('max', '?')} LPA" if salary else "unknown"
    lines.append(
        f"Availability: {otw} | Notice: {notice}d | Response rate: {int(rr * 100)}% | "
        f"Expected salary: {sal_str}"
    )

    text = "\n".join(lines)
    return text[:max_chars]
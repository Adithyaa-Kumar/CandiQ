"""
pipeline/score.py
────────────────────
Evidence-first multi-dimensional scorer.

Architecture changes (per product spec):
  Tier 1: Capability matching (LangChain ≈ Haystack = same RAG capability)
  Tier 2: Impact evidence boosts score
  Tier 3: Ownership evidence boosts score
  Tier 4: Scale evidence boosts score
  Tier 5: Role relevance is the dominant signal (25% weight minimum)
  Tier 6: Score normalized so distribution is healthy (not 82/21/21/2/2)

Score distribution fix:
  Final scores are percentile-normalized within the candidate pool so the
  spread is healthy (~88/81/76/69/63) rather than clustered at extremes.
  Normalization is done in run_retrieval_filter after all candidates scored.
"""

from __future__ import annotations

from app.pipeline.jd_analyzer import JDSignals
from app.pipeline.role_match import compute_role_relevance
from app.pipeline.skill_taxonomy import capability_match_score


def score_candidate(flags: dict, signals: JDSignals) -> dict:
    cid  = flags["candidate_id"]
    name = flags["name"]

    disqualified, reason = _check_disqualifiers(flags, signals)
    if disqualified:
        return _disqualified(cid, name, reason)

    score_skills      = _score_skills(flags, signals)
    score_experience  = _score_experience(flags, signals)
    score_career      = _score_career(flags, signals)
    score_activity    = _score_activity(flags)
    score_platform    = _score_platform(flags)
    role_relevance    = compute_role_relevance(flags, signals)

    # Evidence bonuses (Tier 2/3/4) — applied to skills score
    intel = flags.get("intelligence_profile") or {}
    impact_bonus    = min(15, intel.get("impact_evidence",    0) * 5)
    ownership_bonus = min(15, intel.get("ownership_evidence", 0) * 3)
    scale_bonus     = min(10, intel.get("scale_evidence",     0) * 4)

    # Evidence-augmented skills score (capped at 100)
    score_skills_aug = min(100, score_skills + impact_bonus + ownership_bonus + scale_bonus)

    dw = signals.dim_weights
    # Ensure role_relevance has at least 25% weight (Tier 5)
    rr_weight = max(0.25, dw.get("role_relevance", 0.25))

    # Redistribute remaining weights proportionally to hit 1.0 total
    other_total = 1.0 - rr_weight
    base_weights = {
        "skills":     dw.get("skills",      0.30),
        "career":     dw.get("career",       0.20),
        "activity":   dw.get("activity",     0.10),
        "experience": dw.get("experience",   0.10),
        "platform":   dw.get("platform",     0.05),
    }
    base_sum = sum(base_weights.values()) or 1.0
    norm_weights = {k: v / base_sum * other_total for k, v in base_weights.items()}

    composite = round(
        score_skills_aug  * norm_weights["skills"]
        + score_career    * norm_weights["career"]
        + score_activity  * norm_weights["activity"]
        + score_experience* norm_weights["experience"]
        + score_platform  * norm_weights["platform"]
        + role_relevance  * rr_weight,
        2,
    )

    # Confidence score (Tier 9) — based on evidence quantity
    confidence = _compute_confidence(flags, signals, role_relevance)

    return {
        "candidate_id":      cid,
        "name":              name,
        "disqualified":      False,
        "disqualify_reason": "",
        "score_skills":      score_skills_aug,
        "score_experience":  score_experience,
        "score_activity":    score_activity,
        "score_career":      score_career,
        "score_platform":    score_platform,
        "composite_score":   composite,
        "role_relevance":    role_relevance,
        "confidence":        confidence,
        # Evidence breakdown
        "impact_bonus":      impact_bonus,
        "ownership_bonus":   ownership_bonus,
        "scale_bonus":       scale_bonus,
    }


def _compute_confidence(flags: dict, signals: JDSignals, role_relevance: float) -> float:
    """
    Confidence is how sure we are the score reflects genuine fit.
    High confidence = lots of evidence. Low confidence = sparse profile.
    """
    intel = flags.get("intelligence_profile") or {}
    evidence_signals = (
        intel.get("production_ai_evidence", 0) +
        intel.get("ownership_evidence",     0) +
        intel.get("impact_evidence",        0) +
        intel.get("scale_evidence",         0)
    )
    # Base from evidence richness
    if evidence_signals >= 8:
        base = 90.0
    elif evidence_signals >= 5:
        base = 75.0
    elif evidence_signals >= 3:
        base = 60.0
    elif evidence_signals >= 1:
        base = 45.0
    else:
        base = 25.0

    # Role relevance alignment increases confidence
    if role_relevance >= 70:
        base = min(100, base + 10)
    elif role_relevance < 30:
        base = max(0, base - 15)

    return round(base, 1)


def _check_disqualifiers(flags: dict, signals: JDSignals) -> tuple[bool, str]:
    # Under-experienced
    if flags["yoe"] < max(1, signals.exp_min - 2):
        return True, f"Under-experienced: {flags['yoe']} yrs (min ~{signals.exp_min})"

    # Consulting-only when product background required
    if signals.requires_product_co and flags["is_consulting_only"]:
        return True, "JD requires product company background; only consulting found"

    # Completely wrong role (word-level match)
    if flags.get("has_bad_title"):
        return True, f"Current title indicates irrelevant domain: {flags['current_title']}"

    # Capability-aware skill gate (very low floor — agents do the nuanced call)
    skill_score = _score_skills(flags, signals)
    if skill_score < 5:
        return True, "Insufficient skill overlap (capability-matched)"

    # Final sanity filter (Tier 2 item 7): role relevance gate
    role_relevance = compute_role_relevance(flags, signals)
    if role_relevance < 15:
        return True, f"Role relevance too low ({role_relevance:.0f}/100) — likely wrong domain"

    if (
        flags["days_since_active"] > 365
        and not flags["open_to_work"]
        and flags["has_known_activity_data"]
    ):
        return True, "Inactive 12+ months and not open to work"

    return False, ""


def _score_skills(flags: dict, signals: JDSignals) -> int:
    """
    Capability-first skill scoring (Tier 1 fix).
    Uses skill_taxonomy to match LangChain ↔ Haystack as equivalent RAG capability.
    """
    if not signals.skill_weights:
        return 50

    candidate_skills = flags["skills"]   # already lowercase list[str]
    skill_depth      = flags["skill_depth"]

    # Capability-level match
    cap_score, cap_matches = capability_match_score(
        signals.skill_weights,
        candidate_skills,
        signals.skill_synonyms,
    )

    # Apply depth multipliers for directly matched skills
    # (capability peers get a flat 0.85 mult already baked in)
    depth_bonus = 0.0
    total_weight = sum(signals.skill_weights.values()) or 1
    for skill_name, weight in signals.skill_weights.items():
        skill_name_lc = skill_name.lower()
        matched_key = next(
            (cs for cs in candidate_skills if skill_name_lc in cs or cs in skill_name_lc),
            None,
        )
        if matched_key:
            depth = skill_depth.get(matched_key, {})
            endorsements    = depth.get("endorsements",   0)
            duration_months = depth.get("duration_months", 0)
            proficiency     = depth.get("proficiency",    "unknown")

            mult = 0.0
            if endorsements > 20 or duration_months > 24:
                mult = 0.25
            elif endorsements > 5 or duration_months > 12:
                mult = 0.10

            if proficiency == "expert":
                mult += 0.10
            elif proficiency == "beginner":
                mult -= 0.10

            depth_bonus += (weight / total_weight) * mult * 100

    return min(100, cap_score + int(depth_bonus))


def _score_experience(flags: dict, signals: JDSignals) -> int:
    yoe = flags["yoe"]
    exp_min, exp_max = signals.exp_min, signals.exp_max
    if exp_min <= yoe <= exp_max:
        return 100
    elif yoe < exp_min:
        return max(0, int((yoe / max(exp_min, 1)) * 80))
    else:
        over = yoe - exp_max
        return max(55, 100 - int(over * 3))


def _score_career(flags: dict, signals: JDSignals) -> int:
    score = 0
    if flags["has_product_co"]:
        score += 35
    elif not flags["is_consulting_only"]:
        score += 15

    edu_points = {1: 30, 2: 22, 3: 14, 4: 6}
    score += edu_points.get(flags["best_edu_tier"], 6)

    avg_a = flags["avg_assessment_score"]
    score += (20 if avg_a > 80 else 14 if avg_a > 65 else 8 if avg_a > 50 else 3 if avg_a > 0 else 0)

    gh = flags["github_score"]
    score += (12 if gh > 60 else 8 if gh > 30 else 4 if gh > 0 else 0)

    if flags["has_significant_gap"]:
        score -= 8
    if flags["avg_tenure_months"] < 12:
        score -= 6

    return max(0, min(100, score))


def _score_activity(flags: dict) -> int:
    score = 0
    days = flags["days_since_active"]
    if flags["has_known_activity_data"]:
        score += (40 if days <= 30 else 30 if days <= 90 else 18 if days <= 180 else 8 if days <= 270 else 0)
    else:
        score += 20

    if flags["open_to_work"]:
        score += 20

    notice = flags["notice_period"]
    score += (30 if notice <= 15 else 25 if notice <= 30 else 18 if notice <= 60 else 10 if notice <= 90 else 0)

    rr = flags["recruiter_response_rate"]
    score += (12 if rr >= 0.7 else 8 if rr >= 0.4 else 4 if rr >= 0.2 else 0)

    return min(100, score)


def _score_platform(flags: dict) -> int:
    score = 0
    pc = flags["profile_completeness"]
    score += (30 if pc >= 85 else 20 if pc >= 65 else 10 if pc >= 40 else 0)

    ic = flags["interview_completion"]
    score += (30 if ic >= 0.75 else 18 if ic >= 0.5 else 8 if ic >= 0.3 else 0)

    saved = flags["raw"].get("redrob_signals", {}).get("saved_by_recruiters_30d", 0)
    score += (25 if saved >= 10 else 15 if saved >= 5 else 8 if saved >= 2 else 0)

    views = flags["raw"].get("redrob_signals", {}).get("profile_views_received_30d", 0)
    score += (15 if views >= 100 else 10 if views >= 50 else 5 if views >= 10 else 0)

    return min(100, score)


def normalize_scores(scored_candidates: list[dict]) -> list[dict]:
    """
    Tier 4 fix: normalize composite scores so spread is healthy.

    Maps raw scores to a percentile-based range [50, 95] for qualified
    candidates. Best candidate gets ~95, rest distributed proportionally.
    Prevents the 82/21/21/2/2 clustering problem.

    Input:  list of score dicts (from score_candidate)
    Output: same dicts with normalized_score added
    """
    qualified = [s for s in scored_candidates if not s.get("disqualified")]
    if not qualified:
        return scored_candidates

    raw_scores = [s["composite_score"] for s in qualified]
    best  = max(raw_scores)
    worst = min(raw_scores)
    spread = best - worst or 1.0

    TARGET_MAX = 95.0
    TARGET_MIN = 50.0

    for s in scored_candidates:
        if s.get("disqualified"):
            s["normalized_score"] = 0.0
        else:
            raw = s["composite_score"]
            normalized = TARGET_MIN + ((raw - worst) / spread) * (TARGET_MAX - TARGET_MIN)
            s["normalized_score"] = round(normalized, 1)

    return scored_candidates


def _disqualified(cid: str, name: str, reason: str) -> dict:
    return {
        "candidate_id":      cid,
        "name":              name,
        "disqualified":      True,
        "disqualify_reason": reason,
        "score_skills":      0,
        "score_experience":  0,
        "score_activity":    0,
        "score_career":      0,
        "score_platform":    0,
        "composite_score":   0.0,
        "role_relevance":    0.0,
        "confidence":        0.0,
        "impact_bonus":      0,
        "ownership_bonus":   0,
        "scale_bonus":       0,
        "normalized_score":  0.0,
    }
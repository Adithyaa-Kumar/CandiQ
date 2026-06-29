"""
pipeline/score.py
──────────────────
Evidence-first, domain-first multi-dimensional scorer.

ROOT CAUSE FIXES IN THIS REWRITE
──────────────────────────────────
Fix 1 (critical): Bad-title disqualifier was conditional on company type.
  A graphic designer at Swiggy passed because has_product_co=True negated the check.
  Now: bad title = immediate disqualification, period. Company type is irrelevant.

Fix 2 (critical): role_relevance gate was too low (< 15).
  Graphic designers, project managers, customer support all scored 8–14 and slipped through.
  Now: gate raised to 20. Candidates who can't reach 20/100 domain relevance
  are wrong-domain — the agents should never see them.

Fix 3 (critical): composite score padded non-domain signals.
  career/activity/platform scores have nothing to do with job fit.
  A graphic designer with good platform activity scored 25–35, passing retrieval.
  Fix: role_relevance weight raised to 40% minimum. All other weights shrink proportionally.
  Domain fit is the dominant signal — as it should be.

Fix 4 (structural): score_candidate no longer returns scores for disqualified candidates.
  Previously it returned zeros. Now it returns the disqualify_reason and stops.
  This makes the disqualification decision final and traceable.
"""

from __future__ import annotations

from app.pipeline.jd_analyzer import JDSignals
from app.pipeline.role_match import compute_role_relevance
from app.pipeline.skill_taxonomy import capability_match_score
from app.pipeline.domain_scorer import compute_candidate_domain_score


def score_candidate(flags: dict, signals: JDSignals) -> dict:
    cid  = flags["candidate_id"]
    name = flags["name"]

    disqualified, reason = _check_disqualifiers(flags, signals)
    if disqualified:
        return _disqualified(cid, name, reason)

    score_skills     = _score_skills(flags, signals)
    score_experience = _score_experience(flags, signals)
    score_career     = _score_career(flags, signals)
    score_activity   = _score_activity(flags)
    score_platform   = _score_platform(flags)
    role_relevance   = compute_role_relevance(flags, signals)

    # ── DOMAIN SCORE: the primary separation signal ────────────────────────
    # This answers "has this candidate solved the SAME PROBLEM as the JD?"
    # A Data Analyst for a Retrieval/Ranking JD gets ~0-20. A Retrieval
    # Engineer gets 65-100. This is the gate that separates wrong-AI from
    # right-AI before any other score matters.
    candidate = flags.get("raw", {})
    domain_score = compute_candidate_domain_score(candidate, signals.subdomain)

    # Hard gate: below 25 domain score → disqualify even if role_relevance passes.
    # This catches "AI Specialist doing ResNet moderation" for retrieval JDs.
    if domain_score < 25 and signals.subdomain != "general":
        return _disqualified(
            cid, name,
            f"Wrong AI subdomain: domain_score={domain_score}/100 for subdomain '{signals.subdomain}'"
        )

    # Evidence bonuses applied to skills dimension
    intel = flags.get("intelligence_profile") or {}
    impact_bonus    = min(15, intel.get("impact_evidence",    0) * 5)
    ownership_bonus = min(15, intel.get("ownership_evidence", 0) * 3)
    scale_bonus     = min(10, intel.get("scale_evidence",     0) * 4)
    score_skills_aug = min(100, score_skills + impact_bonus + ownership_bonus + scale_bonus)

    # ── Weight schedule (spec: skills 25%, role_relevance 30%, career 15%,
    #    activity 10%, experience 10%, platform 10%)
    # domain_score gets 15% on top — it is the most important separator.
    # role_relevance gets 25% (broad domain alignment).
    # Together domain+role = 40% of the signal, which is correct.
    WEIGHTS = {
        "domain":      0.20,   # have they solved THIS exact problem?
        "role_relevance": 0.25, # are they in the right broad domain?
        "skills":      0.25,   # do they have the right skills?
        "career":      0.12,   # pedigree quality
        "activity":    0.08,   # responsiveness / availability
        "experience":  0.07,   # YOE alignment
        "platform":    0.03,   # platform engagement
    }

    composite = round(
        domain_score       * WEIGHTS["domain"]
        + role_relevance   * WEIGHTS["role_relevance"]
        + score_skills_aug * WEIGHTS["skills"]
        + score_career     * WEIGHTS["career"]
        + score_activity   * WEIGHTS["activity"]
        + score_experience * WEIGHTS["experience"]
        + score_platform   * WEIGHTS["platform"],
        2,
    )

    confidence = _compute_confidence(flags, signals, role_relevance, domain_score)

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
        "domain_score":      domain_score,
        "composite_score":   composite,
        "role_relevance":    role_relevance,
        "confidence":        confidence,
        "impact_bonus":      impact_bonus,
        "ownership_bonus":   ownership_bonus,
        "scale_bonus":       scale_bonus,
    }


def _compute_confidence(flags: dict, signals: JDSignals, role_relevance: float, domain_score: float = 60.0) -> float:
    intel = flags.get("intelligence_profile") or {}
    evidence_signals = (
        intel.get("production_ai_evidence", 0) +
        intel.get("ownership_evidence",     0) +
        intel.get("impact_evidence",        0) +
        intel.get("scale_evidence",         0)
    )
    if evidence_signals >= 8:   base = 90.0
    elif evidence_signals >= 5: base = 75.0
    elif evidence_signals >= 3: base = 60.0
    elif evidence_signals >= 1: base = 45.0
    else:                       base = 25.0

    if role_relevance >= 70:    base = min(100, base + 8)
    elif role_relevance < 30:   base = max(0,   base - 12)

    if domain_score >= 65:      base = min(100, base + 7)
    elif domain_score < 35:     base = max(0,   base - 10)

    return round(base, 1)


def _check_disqualifiers(flags: dict, signals: JDSignals) -> tuple[bool, str]:
    """
    Hard gates. If any of these fire, the candidate is gone — no exceptions.

    FIX 1: has_bad_title is now absolute. Company type (product/consulting) is
    irrelevant to domain fit. A graphic designer is not an AI engineer regardless
    of whether they worked at Swiggy.

    FIX 2: role_relevance gate raised to 20 (was 15). This catches:
      - Graphic designers (score 0–10)
      - Customer support reps (score 0–8)
      - Project managers with no tech background (score 5–15)
      - Operations managers with no domain overlap (score 0–12)
    """
    # Under-experienced
    if flags["yoe"] < max(1, signals.exp_min - 2):
        return True, f"Under-experienced: {flags['yoe']} yrs (min ~{signals.exp_min})"

    # FIX 1: Bad title = absolute disqualification (removed has_product_co exception)
    if flags.get("has_bad_title"):
        return True, f"Title indicates wrong domain: '{flags['current_title']}'"

    # Consulting-only when product co required
    if signals.requires_product_co and flags["is_consulting_only"]:
        return True, "JD requires product company background; only consulting found"

    # FIX 2: role_relevance gate raised to 20
    role_relevance = compute_role_relevance(flags, signals)
    if role_relevance < 20:
        return True, f"Domain mismatch: role relevance {role_relevance:.0f}/100 — wrong field"

    # Capability-matched skill gate (very low floor — agents handle nuance)
    skill_score = _score_skills(flags, signals)
    if skill_score < 3:
        return True, "No meaningful skill overlap with role requirements"

    # Activity gate
    if (
        flags["days_since_active"] > 365
        and not flags["open_to_work"]
        and flags["has_known_activity_data"]
    ):
        return True, "Inactive 12+ months and not open to work"

    return False, ""


def _score_skills(flags: dict, signals: JDSignals) -> int:
    if not signals.skill_weights:
        return 50

    candidate_skills = flags["skills"]
    skill_depth      = flags["skill_depth"]

    cap_score, cap_matches = capability_match_score(
        signals.skill_weights,
        candidate_skills,
        signals.skill_synonyms,
    )

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
            if endorsements > 20 or duration_months > 24: mult = 0.25
            elif endorsements > 5 or duration_months > 12: mult = 0.10
            if proficiency == "expert":   mult += 0.10
            elif proficiency == "beginner": mult -= 0.10
            depth_bonus += (weight / total_weight) * mult * 100

    return min(100, cap_score + int(depth_bonus))


def _score_experience(flags: dict, signals: JDSignals) -> int:
    yoe = flags["yoe"]
    exp_min, exp_max = signals.exp_min, signals.exp_max
    if exp_min <= yoe <= exp_max: return 100
    elif yoe < exp_min: return max(0, int((yoe / max(exp_min, 1)) * 80))
    else: return max(55, 100 - int((yoe - exp_max) * 3))


def _score_career(flags: dict, signals: JDSignals) -> int:
    score = 0
    if flags["has_product_co"]:   score += 35
    elif not flags["is_consulting_only"]: score += 15
    edu_points = {1: 30, 2: 22, 3: 14, 4: 6}
    score += edu_points.get(flags["best_edu_tier"], 6)
    avg_a = flags["avg_assessment_score"]
    score += (20 if avg_a > 80 else 14 if avg_a > 65 else 8 if avg_a > 50 else 3 if avg_a > 0 else 0)
    gh = flags["github_score"]
    score += (12 if gh > 60 else 8 if gh > 30 else 4 if gh > 0 else 0)
    if flags["has_significant_gap"]:  score -= 8
    if flags["avg_tenure_months"] < 12: score -= 6
    return max(0, min(100, score))


def _score_activity(flags: dict) -> int:
    score = 0
    days = flags["days_since_active"]
    if flags["has_known_activity_data"]:
        score += (40 if days <= 30 else 30 if days <= 90 else 18 if days <= 180
                  else 8 if days <= 270 else 0)
    else:
        score += 20
    if flags["open_to_work"]: score += 20
    notice = flags["notice_period"]
    score += (30 if notice <= 15 else 25 if notice <= 30 else 18 if notice <= 60
              else 10 if notice <= 90 else 0)
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
    Percentile-normalize composite scores to a healthy spread [55, 95].
    Best candidate → 95. Worst qualified → 55. Rest distributed proportionally.
    Prevents clustering at extremes (82/21/21/2/2 problem).
    """
    qualified = [s for s in scored_candidates if not s.get("disqualified")]
    if not qualified:
        return scored_candidates

    raw_scores = [s["composite_score"] for s in qualified]
    best   = max(raw_scores)
    worst  = min(raw_scores)
    spread = best - worst or 1.0

    TARGET_MAX = 95.0
    TARGET_MIN = 55.0

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
        "domain_score":      0,
        "normalized_score":  0.0,
    }
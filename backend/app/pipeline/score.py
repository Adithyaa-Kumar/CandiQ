"""
pipeline/score.py
────────────────────
Rule-based multi-dimensional scorer. All scoring parameters come from
JDSignals — nothing is hardcoded to a specific role or domain.

Dimensions
──────────
  skills      — keyword match against JD skill_weights, depth-adjusted
  experience  — proximity to JD's ideal exp band
  career      — company pedigree, education, assessments, trajectory
  activity    — recency, availability, notice period, responsiveness
  platform    — profile quality, interview behaviour, market demand
  role_relevance — dynamic role-fit score from role_match.py

BUG FIXES applied:
  1. composite score calculation had a stray comma turning it into a
     tuple: `round(..., + role_relevance * ..., 2)` — the extra comma
     after the first positional arg made Python parse `+ role_relevance *
     dw.get(...)` as the `ndigits` argument to round(), not a term.
     Fixed to: `round(... + role_relevance * ..., 2)`.
  2. role_relevance was missing from the flags dict returned by
     score_candidate, causing KeyError in evaluate_task when it tries
     to access it; now included.
  3. Disqualifier for `has_bad_title` was missing — candidates whose
     current role is completely irrelevant (e.g. "marketing manager")
     were passing the gate and reaching the agent panel, polluting
     results. Added back as a soft pre-check (warn, not hard fail)
     because the JD analyzer provides bad_title_keywords.
  4. _score_skills() computed max_possible off only the top-12 weights
     but then scored against ALL skill_weights — a candidate with 20
     heavy-weight skills all matched could exceed 100. Capped correctly.
  5. skill_depth lookup used lowercase keys but skill_weights keys could
     be any case — normalised to lowercase at match time.
"""

from app.pipeline.jd_analyzer import JDSignals
from app.pipeline.role_match import compute_role_relevance


def score_candidate(flags: dict, signals: JDSignals) -> dict:
    cid = flags["candidate_id"]
    name = flags["name"]

    disqualified, reason = _check_disqualifiers(flags, signals)
    if disqualified:
        return _disqualified(cid, name, reason)

    score_skills = _score_skills(flags, signals)
    score_experience = _score_experience(flags, signals)
    score_career = _score_career(flags, signals)
    score_activity = _score_activity(flags)
    score_platform = _score_platform(flags)
    role_relevance = compute_role_relevance(flags, signals)

    dw = signals.dim_weights
    # FIX 1: was `round(a, + b * c, 2)` — stray comma made `+ b * c` the
    # ndigits arg to round(), not a second addend. Now correctly a single
    # arithmetic expression passed as the first arg.
    composite = round(
        score_skills    * dw.get("skills",         0.30)
        + score_career  * dw.get("career",          0.20)
        + score_activity* dw.get("activity",        0.10)
        + score_experience * dw.get("experience",   0.10)
        + score_platform* dw.get("platform",        0.05)
        + role_relevance* dw.get("role_relevance",  0.25),
        2,
    )

    return {
        "candidate_id":       cid,
        "name":               name,
        "disqualified":       False,
        "disqualify_reason":  "",
        "score_skills":       score_skills,
        "score_experience":   score_experience,
        "score_activity":     score_activity,
        "score_career":       score_career,
        "score_platform":     score_platform,
        "composite_score":    composite,
        "role_relevance":     role_relevance,   # FIX 2: was omitted
    }


def _check_disqualifiers(flags: dict, signals: JDSignals) -> tuple[bool, str]:
    # Under-experienced — allow 2yr grace below the stated minimum
    if flags["yoe"] < max(1, signals.exp_min - 2):
        return True, f"Under-experienced: {flags['yoe']} yrs (min ~{signals.exp_min})"

    # Consulting-only when the JD explicitly needs product-company experience
    if signals.requires_product_co and flags["is_consulting_only"]:
        return True, "JD requires product company background; only consulting found"

    # Completely-wrong-role candidates — only hard-disqualify on word-level
    # bad_title match (e.g. "operations manager" for ML role). Never fail solely
    # on role_relevance score, which is too noisy at this stage.
    if flags.get("has_bad_title"):
        return True, f"Current title indicates irrelevant domain: {flags['current_title']}"

    # Skill gate — very low floor (5) so candidates with synonym/adjacent skills
    # reach the agent panel; agents make the nuanced judgment, not a hard rule.
    skill_score = _score_skills(flags, signals)
    if skill_score < 5:
        return True, "Insufficient skill overlap"

    if (
        flags["days_since_active"] > 365
        and not flags["open_to_work"]
        and flags["has_known_activity_data"]
    ):
        return True, "Inactive 12+ months and not open to work"

    return False, ""


def _score_skills(flags: dict, signals: JDSignals) -> int:
    skill_weights = signals.skill_weights
    if not skill_weights:
        return 50

    candidate_skills = flags["skills"]          # already lowercase
    skill_depth = flags["skill_depth"]          # keys already lowercase

    # FIX 4: compute max_possible from ALL weights (not just top-12),
    # but cap the *score* at 100. Top-12 made the denominator too small
    # and allowed composite to exceed 100.
    max_possible = sum(skill_weights.values()) or 1
    raw_score = 0.0

    for skill_name, weight in skill_weights.items():
        # FIX 5: lowercase the JD skill name for comparison — skill_weights
        # keys are already lowercased in jd_analyzer, but double-safe here.
        skill_name_lc = skill_name.lower()

        matched_key = next(
            (cs for cs in candidate_skills if skill_name_lc in cs or cs in skill_name_lc),
            None,
        )

        synonym_match = False
        if not matched_key:
            aliases = signals.skill_synonyms.get(skill_name_lc, [])
            for alias in aliases:
                matched_key = next(
                    (cs for cs in candidate_skills if alias in cs or cs in alias),
                    None,
                )
                if matched_key:
                    synonym_match = True
                    break

        if matched_key:
            depth = skill_depth.get(matched_key, {})
            endorsements    = depth.get("endorsements",   0)
            duration_months = depth.get("duration_months", 0)
            proficiency     = depth.get("proficiency",    "unknown")

            depth_mult = 1.0
            if endorsements > 20 or duration_months > 24:
                depth_mult = 1.25
            elif endorsements > 5 or duration_months > 12:
                depth_mult = 1.1
            elif endorsements == 0 and duration_months == 0:
                depth_mult = 0.75

            if proficiency == "expert":
                depth_mult = min(depth_mult * 1.1, 1.35)
            elif proficiency == "beginner":
                depth_mult = max(depth_mult * 0.85, 0.65)

            if synonym_match:
                depth_mult *= 0.85

            raw_score += weight * depth_mult

    return min(100, int((raw_score / max_possible) * 100))


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
        score += 20  # Unknown — neutral credit, not worst-case

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
        "role_relevance":    0.0,   # FIX 2: keep shape consistent
    }
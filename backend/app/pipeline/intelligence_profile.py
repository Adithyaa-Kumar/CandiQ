"""
pipeline/intelligence_profile.py
──────────────────────────────────
Evidence-first candidate intelligence extraction.

Architecture shift (per product spec Tier 6):
  OLD:  Resume → Score
  NEW:  Resume → Evidence Extraction → Intelligence Profile → Ranking

The profile is the canonical representation every downstream component
(agents, scoring, retrieval) works from. It surfaces:

  1. Impact evidence    — quantified outcomes ("improved CTR by 18%")
  2. Ownership evidence — builder signals ("built", "designed", "led")
  3. Scale evidence     — magnitude signals ("50M users", "10TB")
  4. Capability evidence — production AI/ML signals
  5. Leadership evidence — mentoring / team-leading signals
  6. Why selected / why rejected hints — pre-computed for trust layer
"""

from __future__ import annotations
import re


# ── Signal term lists ────────────────────────────────────────────────────

_IMPACT_PATTERNS = [
    # Percentage improvements
    r"\b(\d+[\.,]?\d*)\s*%\b",
    # Revenue / scale numbers with units
    r"\$\s*\d+[\.,]?\d*\s*(k|m|b|million|billion|thousand)?\b",
    r"\b\d+[\.,]?\d*\s*(million|billion|thousand|m\b|b\b|k\b)",
    # Explicit improvement verbs near numbers
    r"(increased|improved|reduced|optimized|saved|generated|scaled|boosted|grew|doubled|tripled)\s.*?\d",
]
_IMPACT_VERBS = [
    "increased", "improved", "reduced", "optimized", "saved",
    "generated", "scaled", "boosted", "grew", "doubled", "tripled",
    "decreased", "accelerated", "cut", "lifted", "raised",
]

_OWNERSHIP_TERMS = [
    "built", "designed", "led", "owned", "architected", "launched",
    "shipped", "implemented", "created", "developed", "responsible for",
    "drove", "spearheaded", "founded", "initiated", "established",
    "authored", "engineered", "constructed",
]

_SCALE_PATTERNS = [
    r"\b\d+\s*m(illion)?\s*users?\b",
    r"\b\d+\s*b(illion)?\s*users?\b",
    r"\b\d+[mk]\s*(users?|customers?|requests?|transactions?|events?|records?)\b",
    r"\b(100k|500k|1m|10m|100m|1b)\b",
    r"\b\d+\s*tb\b",
    r"\bhigh\s*(scale|traffic|availability|throughput)\b",
    r"\b(at scale|large scale|production scale|planet.?scale)\b",
    r"\b(million|billions?)\s+(of)?\s*(users?|events?|records?|transactions?)\b",
    r"\bqps\b|\btps\b",
    r"\b\d+\s*qps\b",
    r"\b(petabyte|terabyte|tb|pb)\b",
]

_AI_TERMS = [
    "llm", "transformer", "rag", "retrieval", "ranking",
    "recommendation", "embedding", "vector", "faiss", "pinecone",
    "qdrant", "milvus", "bm25", "xgboost", "fine tuning", "fine-tuning",
    "inference", "semantic search", "neural", "sentence transformer",
    "hugging face", "language model", "information retrieval",
    "elasticsearch", "opensearch", "haystack", "weaviate", "chromadb",
    "pytorch", "tensorflow", "deep learning", "machine learning",
    "generative ai", "diffusion", "stable diffusion", "gpt",
    "chatgpt", "openai", "anthropic", "gemini", "mistral",
]

_LEADERSHIP_TERMS = [
    "mentor", "mentored", "mentoring", "team lead", "lead engineer",
    "staff engineer", "principal engineer", "managed a team",
    "lead a team", "senior manager", "engineering manager", "tech lead",
    "director", "vp of engineering", "head of", "grew the team",
    "hired", "built the team", "managed engineers",
]

_BUILD_VERBS   = ["built", "created", "architected", "designed", "implemented", "developed", "engineered"]
_SHIP_VERBS    = ["shipped", "launched", "deployed", "released", "delivered", "productionized", "rolled out"]
_SCALE_VERBS   = ["scaled", "optimized", "improved performance", "reduced latency", "handled", "serving"]
_LEAD_VERBS    = ["led", "managed", "mentored", "grew", "hired", "organized", "coordinated"]


def _has_impact(desc: str) -> tuple[bool, list[str]]:
    """Detect quantified impact in a job description. Returns (found, snippets)."""
    desc_lower = desc.lower()
    snippets: list[str] = []
    for verb in _IMPACT_VERBS:
        if verb in desc_lower:
            # Grab the sentence containing the verb
            for sentence in re.split(r"[.!?\n]", desc):
                if verb in sentence.lower() and re.search(r"\d", sentence):
                    snippets.append(sentence.strip()[:200])
                    break
    # Also catch bare % patterns
    for m in re.finditer(r"\b\d+[\.,]?\d*\s*%", desc):
        start = max(0, m.start() - 60)
        snippets.append(desc[start:m.end() + 60].strip()[:200])
    return bool(snippets), list(dict.fromkeys(snippets))[:5]   # dedup, cap 5


def _has_scale(desc: str) -> tuple[bool, list[str]]:
    """Detect scale signals. Returns (found, snippets)."""
    desc_lower = desc.lower()
    snippets: list[str] = []
    for pattern in _SCALE_PATTERNS:
        for m in re.finditer(pattern, desc_lower):
            start = max(0, m.start() - 50)
            snippets.append(desc[start:m.end() + 80].strip()[:200])
    return bool(snippets), list(dict.fromkeys(snippets))[:5]


def build_candidate_intelligence_profile(candidate: dict) -> dict:
    """
    Evidence-first candidate profile. Every downstream component
    (agents, scoring, retrieval) works from this structure — not from
    raw resume text.

    Schema
    ──────
    production_ai_evidence  int   jobs with AI/ML signals
    ownership_evidence      int   jobs with builder signals
    scale_evidence          int   jobs with scale/magnitude signals
    impact_evidence         int   jobs with quantified outcomes
    leadership_evidence     int   jobs with leadership signals
    impact_score            int   weighted score from impact signals (0-100)
    ownership_score         int   weighted score from ownership signals (0-100)
    evidence_score          int   composite evidence score
    ir_ml_evidence          list  career snippets showing AI/ML work
    ownership_signals       list  career snippets showing builder language
    scale_signals           list  career snippets showing scale
    impact_signals          list  career snippets with numbers/outcomes
    key_skills              list  candidate's declared skills
    career_trajectory       str   oldest→newest title progression
    built_count             int   jobs with build verbs
    shipped_count           int   jobs with ship verbs
    scaled_count            int   jobs with scale verbs
    led_count               int   jobs with lead verbs
    why_selected            list  pre-computed recruiter trust signals
    why_rejected            list  pre-computed gaps
    """
    # career_history is stored most-recent-first → reverse for oldest→newest
    career: list[dict] = list(reversed(candidate.get("career_history", [])))
    skills: list[str]  = [s.get("name", "") for s in candidate.get("skills", []) if s.get("name")]

    # -- evidence containers --
    ir_ml_evidence:   list[str] = []
    ownership_signals: list[str] = []
    scale_signals:    list[str] = []
    impact_signals:   list[str] = []

    seen_ir:    set[int] = set()
    seen_own:   set[int] = set()

    production_ai_evidence = 0
    ownership_evidence     = 0
    scale_evidence         = 0
    impact_evidence        = 0
    leadership_evidence    = 0

    built_count   = 0
    shipped_count = 0
    scaled_count  = 0
    led_count     = 0

    # -- evidence scoring accumulators --
    impact_score_raw    = 0
    ownership_score_raw = 0

    for idx, job in enumerate(career):
        raw_desc = job.get("description", "")
        desc     = raw_desc.lower()

        # ── AI/ML evidence ────────────────────────────────────────────
        if idx not in seen_ir:
            for term in _AI_TERMS:
                if term in desc:
                    production_ai_evidence += 1
                    seen_ir.add(idx)
                    snippet = raw_desc[:300]
                    if snippet and snippet not in ir_ml_evidence:
                        ir_ml_evidence.append(snippet)
                    break

        # ── Ownership evidence ────────────────────────────────────────
        if idx not in seen_own:
            for term in _OWNERSHIP_TERMS:
                if term in desc:
                    ownership_evidence += 1
                    seen_own.add(idx)
                    snippet = raw_desc[:300]
                    if snippet and snippet not in ownership_signals:
                        ownership_signals.append(snippet)
                    ownership_score_raw += 15     # Tier 3: +15 per ownership job
                    break

        # ── Scale evidence ────────────────────────────────────────────
        has_s, s_snippets = _has_scale(raw_desc)
        if has_s:
            scale_evidence += 1
            scale_signals.extend(sn for sn in s_snippets if sn not in scale_signals)

        # ── Impact evidence ───────────────────────────────────────────
        has_i, i_snippets = _has_impact(raw_desc)
        if has_i:
            impact_evidence += 1
            impact_signals.extend(sn for sn in i_snippets if sn not in impact_signals)
            impact_score_raw += 15                # Tier 2: +15 per impactful job

        # ── Leadership evidence ───────────────────────────────────────
        if any(term in desc for term in _LEADERSHIP_TERMS):
            leadership_evidence += 1

        # ── Verb counts ───────────────────────────────────────────────
        if any(v in desc for v in _BUILD_VERBS):
            built_count += 1
        if any(v in desc for v in _SHIP_VERBS):
            shipped_count += 1
        if any(v in desc for v in _SCALE_VERBS):
            scaled_count += 1
        if any(v in desc for v in _LEAD_VERBS):
            led_count += 1

    # ── Composite evidence score ──────────────────────────────────────────
    evidence_score = (
        built_count   * 5
        + shipped_count * 5
        + scaled_count  * 8
        + led_count     * 8
        + impact_evidence  * 10
        + scale_evidence   * 6
    )

    # Normalize impact/ownership scores to 0-100
    impact_score    = min(100, impact_score_raw)
    ownership_score = min(100, ownership_score_raw)

    # ── Career trajectory (oldest → newest) ──────────────────────────────
    career_trajectory = " → ".join(
        j.get("title", "") for j in career if j.get("title")
    )

    # ── Why selected / why rejected (Tier 5 trust) ───────────────────────
    why_selected: list[str] = []
    why_rejected: list[str] = []

    if production_ai_evidence >= 2:
        why_selected.append(f"Production AI/ML experience in {production_ai_evidence} roles")
    if ownership_evidence >= 2:
        why_selected.append(f"Strong builder signals — ownership in {ownership_evidence} roles")
    if impact_evidence >= 1:
        why_selected.append(f"Quantified impact in {impact_evidence} role(s)")
    if scale_evidence >= 1:
        why_selected.append(f"Scale evidence: worked at meaningful system scale")
    if leadership_evidence >= 1:
        why_selected.append(f"Leadership signals in {leadership_evidence} role(s)")

    if production_ai_evidence == 0:
        why_rejected.append("No clear AI/ML production experience found")
    if ownership_evidence == 0:
        why_rejected.append("Descriptions lack builder/ownership language")
    if impact_evidence == 0:
        why_rejected.append("No quantified outcomes found in career descriptions")
    if scale_evidence == 0:
        why_rejected.append("No evidence of working at meaningful scale")

    return {
        # Evidence counts
        "production_ai_evidence": production_ai_evidence,
        "ownership_evidence":     ownership_evidence,
        "scale_evidence":         scale_evidence,
        "impact_evidence":        impact_evidence,
        "leadership_evidence":    leadership_evidence,
        # Evidence scores
        "impact_score":           impact_score,
        "ownership_score":        ownership_score,
        "evidence_score":         evidence_score,
        # Evidence snippets
        "ir_ml_evidence":         ir_ml_evidence[:10],
        "ownership_signals":      ownership_signals[:10],
        "scale_signals":          scale_signals[:10],
        "impact_signals":         impact_signals[:10],
        # Metadata
        "key_skills":             skills[:30],
        "career_trajectory":      career_trajectory,
        # Verb counts
        "built_count":            built_count,
        "shipped_count":          shipped_count,
        "scaled_count":           scaled_count,
        "led_count":              led_count,
        # Trust layer
        "why_selected":           why_selected,
        "why_rejected":           why_rejected,
    }
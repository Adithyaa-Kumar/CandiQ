"""
pipeline/role_match.py
──────────────────────
Domain relevance scoring. Returns 0–100.

ROOT CAUSE FIX
──────────────
The previous version could give graphic designers and project managers
10–18 points purely from skill-list substring accidents and partial
description hits. Since the disqualifier gate was < 15, they slipped through.

This rewrite uses DOMAIN SIGNALS as the primary gate:
  1. Domain keyword check — does the candidate's career contain ANY signal
     from the role's domain? If zero signals → score is capped at 15 max.
  2. Title alignment — exact or strong partial overlap.
  3. Skill overlap — how many JD skills appear in candidate profile.
  4. Career description overlap — how much JD vocabulary appears in career text.

DOMAIN ZERO-SIGNAL CAP:
If a candidate has no domain keywords in their entire career history,
their role relevance is capped at 15 — meaning they ALWAYS fail the
disqualifier gate (which requires ≥ 20). This eliminates:
  - Graphic designers (no ML/engineering terms anywhere)
  - Customer support reps (no tech terms)
  - Operations managers with zero technical background
  - Project managers with no domain vocabulary

These candidates correctly score 0–15 and are filtered before the agents.
"""

from __future__ import annotations

from app.pipeline.jd_analyzer import JDSignals

# ── Domain vocabulary clusters ──────────────────────────────────────────────
# These are the minimum signals required to be considered "in the domain".
# A candidate with zero of these terms in their career text is wrong-domain.

_DOMAIN_VOCABULARY: dict[str, list[str]] = {
    "machine_learning": [
        "machine learning", "deep learning", "neural network", "pytorch", "tensorflow",
        "scikit-learn", "xgboost", "lightgbm", "embedding", "transformer", "llm",
        "nlp", "computer vision", "model training", "inference", "data science",
        "ai engineer", "ml engineer", "data scientist", "research engineer",
        "recommendation", "ranking", "retrieval", "vector", "rag", "fine-tuning",
        "gradient descent", "backpropagation", "feature engineering", "classification",
        "regression", "clustering", "reinforcement learning", "generative ai",
    ],
    "data_science": [
        "data science", "machine learning", "statistical", "analytics", "pandas",
        "numpy", "sql", "r programming", "hypothesis testing", "a/b test",
        "data analysis", "python", "visualization", "tableau", "power bi",
        "experiment design", "predictive model", "regression", "classification",
    ],
    "data_engineering": [
        "data pipeline", "etl", "spark", "kafka", "airflow", "data warehouse",
        "snowflake", "bigquery", "redshift", "databricks", "dbt", "data lake",
        "data engineer", "stream processing", "batch processing", "sql", "python",
        "hadoop", "hive", "data platform", "ingestion", "orchestration",
    ],
    "software_engineering": [
        "software engineer", "backend", "api", "microservice", "system design",
        "python", "java", "go", "rust", "javascript", "typescript", "node",
        "postgresql", "redis", "kafka", "docker", "kubernetes", "aws", "gcp",
        "rest", "grpc", "distributed system", "scalability", "latency",
    ],
    "frontend": [
        "frontend", "react", "vue", "angular", "javascript", "typescript",
        "css", "html", "next.js", "web development", "ui", "ux", "component",
        "browser", "responsive design", "webpack", "vite",
    ],
    "mobile": [
        "mobile", "ios", "android", "swift", "kotlin", "react native", "flutter",
        "app development", "xcode", "android studio", "mobile app",
    ],
    "devops": [
        "devops", "sre", "infrastructure", "kubernetes", "docker", "terraform",
        "ci/cd", "jenkins", "github actions", "monitoring", "alerting",
        "deployment", "cloud", "aws", "gcp", "azure", "linux", "bash",
        "reliability", "observability",
    ],
    "design": [
        "design", "ux", "ui", "figma", "sketch", "adobe", "user research",
        "wireframe", "prototype", "visual design", "product design", "typography",
        "interaction design", "usability",
    ],
    "product": [
        "product manager", "product management", "roadmap", "stakeholder",
        "user research", "prioritization", "product strategy", "agile", "scrum",
        "okr", "metrics", "kpi", "customer discovery", "go-to-market",
    ],
    "finance": [
        "finance", "financial", "accounting", "investment", "portfolio",
        "quantitative", "trading", "risk", "valuation", "equity", "bonds",
        "derivatives", "hedge fund", "asset management", "cfa", "ca",
    ],
    "other": [],  # No domain filter applied — any candidate passes
}


def _get_domain_vocabulary(domain: str) -> list[str]:
    """Return domain vocabulary; fall back to empty list for unknown domains."""
    return _DOMAIN_VOCABULARY.get(domain, [])


def _count_domain_signals(career_text: str, title_text: str, skills_text: str,
                           domain_vocab: list[str]) -> int:
    """Count distinct domain vocabulary terms appearing anywhere in candidate data."""
    all_text = (career_text + " " + title_text + " " + skills_text).lower()
    return sum(1 for term in domain_vocab if term in all_text)


def compute_role_relevance(flags: dict, signals: JDSignals) -> float:
    """
    Returns 0–100 domain relevance score.

    DOMAIN ZERO-SIGNAL CAP:
    If a candidate has zero domain vocabulary signals across their entire
    career history, title, and skills → capped at 15 → fails gate (< 20).
    """
    career_jobs   = flags.get("raw", {}).get("career_history", [])
    career_text   = " ".join(j.get("description", "").lower() for j in career_jobs)
    skills_text   = " ".join(flags.get("skills", []))
    current_title = flags.get("current_title", "")

    # ── DOMAIN SIGNAL CHECK ──────────────────────────────────────────────
    domain_vocab = _get_domain_vocabulary(signals.domain)
    if domain_vocab:  # "other" domain has no filter
        domain_signal_count = _count_domain_signals(
            career_text, current_title, skills_text, domain_vocab
        )
        # Zero domain signals → hard cap at 15 (always fails the ≥ 20 gate)
        if domain_signal_count == 0:
            return 0.0
        # Very low domain signals → reduced cap
        domain_cap = 100.0 if domain_signal_count >= 3 else 35.0

    score = 0.0

    # ── 1. Title alignment (0–40) ─────────────────────────────────────────
    role_terms = {
        t for t in signals.role_title.lower().replace("/", " ").split()
        if len(t) >= 3
    }
    title_terms = {
        t for t in current_title.lower().replace("/", " ").split()
        if len(t) >= 3
    }
    title_overlap = len(role_terms & title_terms)
    score += min(title_overlap * 15, 40)

    # ── 2. Skill overlap (0–40) ───────────────────────────────────────────
    # HEATMAP FIX: match skills against BOTH the skills list AND career text.
    # Previously: only skills list. This caused "ranking systems" mentioned in
    # career descriptions to score 0 in the heatmap even when clearly present.
    candidate_skills = {s.lower() for s in flags["skills"]}
    jd_skills        = {s.lower() for s in signals.skill_weights.keys()}
    # Combined text for broader matching (skills list + career descriptions)
    all_candidate_text = skills_text + " " + career_text

    matched_jd_skills: set[str] = set()
    for jd_s in jd_skills:
        # Match against skills list (exact)
        if any(jd_s in cs or cs in jd_s for cs in candidate_skills):
            matched_jd_skills.add(jd_s)
        # Match against career text (broader — catches "built ranking systems")
        elif jd_s in all_candidate_text:
            matched_jd_skills.add(jd_s)

    skill_overlap = len(matched_jd_skills)

    # Synonym expansion — only for skills not already matched
    for canonical, aliases in signals.skill_synonyms.items():
        if canonical.lower() not in matched_jd_skills:
            if any(alias in all_candidate_text for alias in aliases):
                skill_overlap += 1

    score += min(skill_overlap * 8, 40)

    # ── 3. Career description overlap (0–20) ──────────────────────────────
    desc_hits = sum(1 for jd_s in jd_skills if jd_s in career_text)
    desc_hits += sum(
        1
        for aliases in signals.skill_synonyms.values()
        for alias in aliases
        if alias in career_text
    )
    score += min(desc_hits * 5, 20)

    # Apply domain cap
    if domain_vocab and domain_signal_count < 3:
        score = min(score, domain_cap)

    return min(score, 100.0)
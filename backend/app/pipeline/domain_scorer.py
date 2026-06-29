"""
pipeline/domain_scorer.py
──────────────────────────
The BIGGEST missing piece per product spec.

Problem: the system asks "Does candidate have AI skills?"
It should ask: "Has candidate solved the SAME PROBLEM as this JD?"

A JD for "Senior AI Engineer — Retrieval/Ranking" has three wrong kinds
of AI candidates:

  CORRECT:    Retrieval Engineer, Recommendation Engineer, Search Engineer
  WRONG AI:   NLP Classification Engineer, Computer Vision Engineer
  WRONG FIELD: Data Analyst, Graphic Designer

Current system scores WRONG AI nearly as high as CORRECT because
both have "AI skills". This is the root cause of "AI Specialist" beating
real search/ranking engineers.

This module computes `candidate_domain_score` (0–100) based on
subdomain alignment — not just broad domain. It is MULTIPLIED into the
composite score as a gate, not added.

Architecture
────────────
  JDSignals.subdomain → maps to a set of PROBLEM SIGNALS
  Candidate career text + skills → counted against those PROBLEM SIGNALS
  → candidate_domain_score

Key design decisions:
  1. Subdomain signals are SPECIFIC. "transformer" alone doesn't prove
     retrieval. "elasticsearch", "ranking loss", "BM25" do.
  2. Score is tiered (0/30/55/75/90/100) not linear — no gradient gaming.
  3. Title bonus: if current title matches subdomain roles → +bonus.
  4. Wrong-subdomain penalty: if candidate signals map to a DIFFERENT
     AI subdomain → explicit penalty (NLP → ranking = -20).
"""

from __future__ import annotations

# ── Subdomain → Problem Signals ─────────────────────────────────────────────
# These are the vocabulary signals that prove you've solved THIS problem.
# Ordered: earlier terms are stronger signals.

_SUBDOMAIN_SIGNALS: dict[str, list[str]] = {

    # ── RETRIEVAL & RANKING ───────────────────────────────────────────────
    "retrieval_ranking": [
        # Core ranking/retrieval
        "ranking", "retrieval", "search", "information retrieval",
        "bm25", "elasticsearch", "opensearch", "solr", "lucene",
        "learning to rank", "ltr", "lambdamart", "ranknet", "listwise",
        "pointwise", "pairwise", "reranking", "re-ranking",
        # Embeddings for retrieval
        "bi-encoder", "cross-encoder", "dense retrieval", "sparse retrieval",
        "hybrid retrieval", "semantic search", "vector search", "ann",
        "approximate nearest neighbor", "hnsw", "ivf", "faiss", "qdrant",
        "pinecone", "weaviate", "milvus", "vespa",
        # Recommendation (close cousin)
        "recommendation", "collaborative filtering", "matrix factorization",
        "two-tower", "item2vec", "recall layer", "candidate generation",
        # Eval metrics for retrieval
        "ndcg", "map@", "mrr", "precision@", "recall@",
    ],

    # ── LLM APPS / GENERATIVE AI ─────────────────────────────────────────
    "llm_apps": [
        "langchain", "llamaindex", "haystack", "rag", "retrieval augmented",
        "prompt engineering", "function calling", "tool use", "agent",
        "llm", "gpt", "claude api", "gemini api", "openai api",
        "fine-tuning", "lora", "qlora", "rlhf", "dpo",
        "chat application", "conversational ai", "chatbot",
        "llm evaluation", "hallucination", "grounding",
        "embeddings", "semantic similarity",
    ],

    # ── COMPUTER VISION ───────────────────────────────────────────────────
    "computer_vision": [
        "computer vision", "image classification", "object detection",
        "yolo", "resnet", "vit", "image segmentation", "ocr", "cnn",
        "opencv", "image recognition", "visual", "detection model",
        "pose estimation", "depth estimation", "generative image",
        "stable diffusion", "diffusion model", "gan",
    ],

    # ── NLP CLASSIFICATION (different from retrieval!) ────────────────────
    "nlp_classification": [
        "sentiment analysis", "text classification", "named entity recognition",
        "ner", "intent detection", "topic modeling", "text mining",
        "bert", "roberta", "xlm", "sequence classification",
        "spam detection", "content moderation", "toxicity",
        "language detection", "summarization", "translation",
    ],

    # ── ML PLATFORM / MLOPS ───────────────────────────────────────────────
    "ml_platform": [
        "mlflow", "kubeflow", "sagemaker", "vertex ai", "mlops",
        "model registry", "feature store", "feast", "tecton",
        "model serving", "triton", "torchserve", "model monitoring",
        "data drift", "ml pipeline", "training pipeline",
        "experiment tracking", "wandb", "weights and biases",
        "hyperparameter tuning", "optuna", "ray tune",
    ],

    # ── RECOMMENDATION SYSTEMS ────────────────────────────────────────────
    "recommendation_systems": [
        "recommendation", "collaborative filtering", "content-based filtering",
        "matrix factorization", "als", "svd", "lightfm",
        "two-tower", "item2vec", "word2vec", "session-based",
        "click-through rate", "ctr prediction", "conversion rate",
        "user-item", "item embedding", "user embedding",
        "implicit feedback", "explicit feedback", "cold start",
        "recbole", "candidate generation", "ranking layer",
    ],

    # ── TABULAR ML / GRADIENT BOOSTING ───────────────────────────────────
    "tabular_ml": [
        "xgboost", "lightgbm", "catboost", "gradient boosting",
        "random forest", "tabular", "feature engineering",
        "feature selection", "hyperparameter", "cross-validation",
        "sklearn", "scikit-learn", "fraud detection", "churn prediction",
        "credit risk", "propensity model",
    ],

    # ── DATA ENGINEERING ─────────────────────────────────────────────────
    "data_pipelines": [
        "data pipeline", "etl", "spark", "kafka", "airflow", "dagster",
        "prefect", "flink", "data warehouse", "snowflake", "bigquery",
        "redshift", "databricks", "dbt", "data lake", "s3", "delta lake",
        "stream processing", "batch processing", "orchestration",
    ],

    # ── BACKEND SYSTEMS ───────────────────────────────────────────────────
    "backend_systems": [
        "api", "microservice", "rest", "grpc", "system design",
        "distributed system", "scalability", "high availability",
        "fastapi", "django", "spring boot", "golang", "rust",
        "postgresql", "redis", "kafka", "message queue",
        "load balancer", "caching", "database design",
    ],

    # ── ANALYTICS ────────────────────────────────────────────────────────
    "analytics": [
        "business intelligence", "bi", "tableau", "power bi", "looker",
        "sql", "data analysis", "reporting", "dashboard", "kpi",
        "a/b testing", "experiment", "metrics", "funnel analysis",
        "cohort analysis", "data analyst", "analytics engineer",
    ],

    # ── GENERAL (no subdomain discrimination) ─────────────────────────────
    "general": [],
}

# ── Subdomain title signals — job titles that PROVE subdomain expertise ──────
_SUBDOMAIN_TITLES: dict[str, list[str]] = {
    "retrieval_ranking": [
        "search engineer", "ranking engineer", "retrieval engineer",
        "recommendation engineer", "information retrieval",
        "search relevance", "search scientist", "ranking scientist",
        "relevance engineer", "discovery engineer",
    ],
    "llm_apps": [
        "llm engineer", "ai engineer", "generative ai", "prompt engineer",
        "nlp engineer", "applied ai", "ml engineer", "ai research",
    ],
    "computer_vision": [
        "computer vision", "vision engineer", "cv engineer",
        "imaging", "perception engineer",
    ],
    "nlp_classification": [
        "nlp engineer", "text mining", "language engineer",
        "computational linguist",
    ],
    "ml_platform": [
        "ml platform", "mlops", "ml infrastructure", "ml infra",
        "platform engineer", "ml engineer",
    ],
    "recommendation_systems": [
        "recommendation", "recommender", "personalization",
        "discovery engineer", "feed ranking",
    ],
    "tabular_ml": [
        "data scientist", "ml engineer", "applied scientist",
    ],
    "data_pipelines": [
        "data engineer", "data platform", "analytics engineer",
        "etl engineer", "pipeline engineer",
    ],
    "backend_systems": [
        "backend engineer", "software engineer", "platform engineer",
        "systems engineer", "sde", "swe",
    ],
    "analytics": [
        "data analyst", "analytics", "business intelligence",
        "bi developer", "reporting analyst",
    ],
}

# ── Cross-subdomain penalty map ──────────────────────────────────────────────
# If a candidate's STRONGEST subdomain is a wrong AI subdomain, penalize.
# e.g. NLP Classification candidate for Retrieval/Ranking JD → -20

_CROSS_DOMAIN_PENALTY: dict[str, dict[str, int]] = {
    "retrieval_ranking": {
        "nlp_classification": -20,
        "computer_vision":    -30,
        "analytics":          -25,
        "general":            -10,
    },
    "llm_apps": {
        "computer_vision":    -20,
        "analytics":          -20,
    },
    "computer_vision": {
        "retrieval_ranking":  -20,
        "nlp_classification": -10,
        "analytics":          -30,
    },
}


def _collect_candidate_text(candidate: dict) -> str:
    """Merge all candidate text for signal scanning."""
    intel  = candidate.get("intelligence_profile") or {}
    career = candidate.get("career_history", [])

    parts = [
        " ".join(intel.get("key_skills", [])),
        intel.get("career_trajectory", ""),
        " ".join(intel.get("ir_ml_evidence", [])),
        " ".join(intel.get("ownership_signals", [])),
        candidate.get("profile", {}).get("summary", ""),
    ]
    for job in career:
        parts.append(job.get("description", ""))
        parts.append(job.get("title", ""))

    return " ".join(parts).lower()


def _count_subdomain_signals(text: str, subdomain: str) -> int:
    """Count distinct subdomain signals present in text."""
    signals = _SUBDOMAIN_SIGNALS.get(subdomain, [])
    return sum(1 for s in signals if s in text)


def _best_candidate_subdomain(text: str) -> tuple[str, int]:
    """Find which subdomain this candidate is strongest in."""
    best_sub   = "general"
    best_count = 0
    for sub, signals in _SUBDOMAIN_SIGNALS.items():
        if sub == "general":
            continue
        count = sum(1 for s in signals if s in text)
        if count > best_count:
            best_count = count
            best_sub   = sub
    return best_sub, best_count


def _title_bonus(candidate: dict, subdomain: str) -> int:
    """Bonus if current title strongly aligns with the JD subdomain."""
    title = candidate.get("profile", {}).get("current_title", "").lower()
    title_signals = _SUBDOMAIN_TITLES.get(subdomain, [])
    return 15 if any(t in title for t in title_signals) else 0


def compute_candidate_domain_score(candidate: dict, subdomain: str) -> int:
    """
    Compute 0–100 candidate_domain_score.

    This answers: "Has this candidate solved the same PROBLEM as the JD?"

    Scoring tiers (before bonuses/penalties):
      0  signals → 0
      1  signal  → 20
      2  signals → 35
      3  signals → 50
      4  signals → 65
      5  signals → 75
      6+ signals → 85

    Title bonus: +15 if title matches subdomain roles
    Cross-domain penalty: -10 to -30 if candidate's strongest domain ≠ JD subdomain

    Hard cap at 100, floor at 0.
    """
    if subdomain == "general" or not subdomain:
        # No subdomain discrimination — everyone passes at neutral 60
        return 60

    text = _collect_candidate_text(candidate)
    count = _count_subdomain_signals(text, subdomain)

    # Tiered scoring
    if count == 0:
        base = 0
    elif count == 1:
        base = 20
    elif count == 2:
        base = 35
    elif count == 3:
        base = 50
    elif count == 4:
        base = 65
    elif count == 5:
        base = 75
    else:
        base = min(85, 75 + (count - 5) * 2)

    # Title alignment bonus
    bonus = _title_bonus(candidate, subdomain)

    # Cross-domain penalty
    penalty = 0
    if count < 3:  # Only penalize if weak on target subdomain
        candidate_sub, candidate_count = _best_candidate_subdomain(text)
        if candidate_sub != subdomain and candidate_count >= 2:
            penalties = _CROSS_DOMAIN_PENALTY.get(subdomain, {})
            penalty = penalties.get(candidate_sub, 0)

    score = base + bonus + penalty
    return max(0, min(100, score))


def get_subdomain_label(subdomain: str) -> str:
    """Human-readable label for UI display."""
    labels = {
        "retrieval_ranking":      "Retrieval & Ranking",
        "llm_apps":               "LLM Applications",
        "computer_vision":        "Computer Vision",
        "nlp_classification":     "NLP & Classification",
        "ml_platform":            "ML Platform & MLOps",
        "recommendation_systems": "Recommendation Systems",
        "tabular_ml":             "Tabular ML",
        "data_pipelines":         "Data Engineering",
        "backend_systems":        "Backend Systems",
        "analytics":              "Analytics",
        "general":                "General",
    }
    return labels.get(subdomain, subdomain.replace("_", " ").title())

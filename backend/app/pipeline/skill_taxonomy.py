"""
pipeline/skill_taxonomy.py
───────────────────────────
Capability-level taxonomy that maps what a recruiter *means* when they
write "LangChain" to the broader capability cluster it belongs to.

When scoring skill overlap we compare CAPABILITY clusters, not raw tool
names. A JD that asks for LangChain and a candidate who knows Haystack
both demonstrate RAG expertise — the recruiter cares about the
capability, not the library.
Usage
─────
  from app.pipeline.skill_taxonomy import get_capability_for_skill, CAPABILITY_CLUSTERS
  cap = get_capability_for_skill("haystack")     # → "retrieval_augmented_generation"
  peers = CAPABILITY_CLUSTERS[cap]               # → ["langchain", "llamaindex", ...]
"""

from __future__ import annotations

# ── Canonical capability → member tools/frameworks ──────────────────────
# Keys are snake_case capability names.
# Values are lowercase tool/framework/concept names that demonstrate the capability.
CAPABILITY_CLUSTERS: dict[str, list[str]] = {
    # ─── Retrieval & RAG ──────────────────────────────────────────────────
    "retrieval_augmented_generation": [
        "langchain", "llamaindex", "llama_index", "haystack", "ragas",
        "langchain4j", "embedchain", "semantic kernel", "dspy", "rag",
    ],
    "information_retrieval": [
        "elasticsearch", "opensearch", "solr", "lucene", "bm25",
        "haystack", "whoosh", "typesense", "meilisearch",
    ],

    # ─── Vector Databases ─────────────────────────────────────────────────
    "vector_database": [
        "qdrant", "pinecone", "weaviate", "milvus", "faiss", "chroma",
        "chromadb", "pgvector", "redis vector", "vespa", "marqo",
    ],

    # ─── LLM Frameworks & Models ──────────────────────────────────────────
    "large_language_models": [
        "openai", "gpt-4", "gpt4", "gpt-3.5", "claude", "gemini",
        "llama", "mistral", "mixtral", "falcon", "bloom", "cohere",
        "hugging face", "transformers", "sentence transformers",
        "chatgpt", "instruct", "anthropic",
    ],
    "llm_fine_tuning": [
        "fine-tuning", "fine tuning", "lora", "qlora", "peft", "rlhf",
        "instruction tuning", "sft", "dpo", "reward model",
    ],

    # ─── ML Frameworks ────────────────────────────────────────────────────
    "deep_learning_frameworks": [
        "pytorch", "tensorflow", "keras", "jax", "flax", "mxnet",
        "paddle", "caffe",
    ],
    "ml_experimentation": [
        "mlflow", "wandb", "weights and biases", "comet", "neptune",
        "optuna", "ray tune", "hyperopt",
    ],

    # ─── Recommendation & Ranking ─────────────────────────────────────────
    "recommendation_systems": [
        "collaborative filtering", "content-based filtering", "matrix factorization",
        "als", "svd", "two-tower", "item2vec", "word2vec", "lightfm",
        "recbole", "implicit", "surprise",
    ],
    "learning_to_rank": [
        "lambdamart", "xgboost rank", "lightgbm rank", "catboost rank",
        "learning to rank", "ltr", "ranknet", "listnet",
    ],

    # ─── Gradient Boosting ────────────────────────────────────────────────
    "gradient_boosting": [
        "xgboost", "lightgbm", "catboost", "gbm", "gbdt", "gradient boosting",
    ],

    # ─── Data Engineering ─────────────────────────────────────────────────
    "stream_processing": [
        "kafka", "flink", "spark streaming", "kinesis", "pulsar",
        "storm", "samza", "redpanda",
    ],
    "batch_processing": [
        "spark", "hadoop", "hive", "dbt", "airflow", "prefect", "dagster",
        "luigi", "beam", "dataflow",
    ],
    "data_warehousing": [
        "snowflake", "bigquery", "redshift", "databricks", "synapse",
        "hive", "presto", "trino", "duckdb",
    ],

    # ─── Backend / APIs ───────────────────────────────────────────────────
    "api_development": [
        "fastapi", "flask", "django", "express", "nestjs", "spring boot",
        "rails", "gin", "fiber", "actix", "axum", "grpc", "rest api",
        "graphql",
    ],
    "message_queues": [
        "kafka", "rabbitmq", "sqs", "pubsub", "celery", "rq", "sidekiq",
        "bull", "nats",
    ],

    # ─── Databases ────────────────────────────────────────────────────────
    "relational_databases": [
        "postgresql", "postgres", "mysql", "sqlite", "oracle", "sqlserver",
        "sql server", "mariadb", "cockroachdb",
    ],
    "nosql_databases": [
        "mongodb", "cassandra", "dynamodb", "couchdb", "redis", "memcached",
        "hbase", "scylladb",
    ],

    # ─── Cloud & Infrastructure ───────────────────────────────────────────
    "cloud_platforms": [
        "aws", "gcp", "google cloud", "azure", "aws lambda", "ec2", "s3",
        "gke", "eks", "aks", "cloud run",
    ],
    "containerization": [
        "docker", "kubernetes", "k8s", "helm", "openshift", "podman",
        "docker compose",
    ],
    "infrastructure_as_code": [
        "terraform", "pulumi", "cdk", "cloudformation", "ansible",
        "chef", "puppet",
    ],

    # ─── Observability ────────────────────────────────────────────────────
    "observability": [
        "datadog", "prometheus", "grafana", "kibana", "splunk",
        "newrelic", "opentelemetry", "jaeger", "zipkin",
    ],

    # ─── Frontend ─────────────────────────────────────────────────────────
    "frontend_frameworks": [
        "react", "reactjs", "vue", "vuejs", "angular", "svelte",
        "next.js", "nextjs", "nuxt", "remix",
    ],

    # ─── Mobile ───────────────────────────────────────────────────────────
    "mobile_development": [
        "react native", "flutter", "swift", "kotlin", "android",
        "ios", "xamarin", "ionic",
    ],

    # ─── Programming Languages ────────────────────────────────────────────
    "python_ecosystem": [
        "python", "cython", "numba", "numpy", "pandas", "scipy",
    ],
    "jvm_languages": [
        "java", "kotlin", "scala", "groovy", "clojure",
    ],
    "javascript_typescript": [
        "javascript", "typescript", "node.js", "nodejs", "deno", "bun",
    ],
    "systems_languages": [
        "rust", "c++", "c", "go", "golang", "zig",
    ],
}

# ── Reverse index: lowercase tool → capability ───────────────────────────
_SKILL_TO_CAPABILITY: dict[str, str] = {
    tool.lower(): capability
    for capability, tools in CAPABILITY_CLUSTERS.items()
    for tool in tools
}


def get_capability_for_skill(skill: str) -> str | None:
    """Return the capability cluster name for a given skill, or None."""
    return _SKILL_TO_CAPABILITY.get(skill.lower())


def get_capability_peers(skill: str) -> list[str]:
    """
    Return all skills that share the same capability as the given skill.
    Includes the skill itself.
    """
    cap = get_capability_for_skill(skill)
    if not cap:
        return [skill.lower()]
    return CAPABILITY_CLUSTERS[cap]


def capability_match_score(
    jd_skills: dict[str, int],
    candidate_skills: list[str],
    skill_synonyms: dict[str, list[str]],
) -> tuple[int, list[str]]:
    """
    Score candidate against JD using capability-level matching.

    Returns (score_0_to_100, list_of_matched_capabilities).

    Matching priority:
      1. Exact match (candidate has the exact tool) → full weight
      2. Capability peer match (candidate has a different tool in the
         same capability cluster) → 85% weight
      3. Synonym match (LLM-generated alias in skill_synonyms) → 80% weight
    """
    candidate_lc = [s.lower() for s in candidate_skills]
    max_possible = sum(jd_skills.values()) or 1
    raw_score = 0.0
    matched_caps: list[str] = []

    for jd_skill, weight in jd_skills.items():
        jd_skill_lc = jd_skill.lower()
        match_found = False
        match_mult  = 0.0

        # 1. Exact / substring match
        if any(jd_skill_lc in cs or cs in jd_skill_lc for cs in candidate_lc):
            match_found = True
            match_mult  = 1.0

        # 2. Capability peer match
        if not match_found:
            jd_cap = get_capability_for_skill(jd_skill_lc)
            if jd_cap:
                peers = CAPABILITY_CLUSTERS[jd_cap]
                for peer in peers:
                    if peer == jd_skill_lc:
                        continue
                    if any(peer in cs or cs in peer for cs in candidate_lc):
                        match_found = True
                        match_mult  = 0.85
                        matched_caps.append(f"{jd_skill}→{peer} [{jd_cap}]")
                        break

        # 3. Synonym match (from JD analyzer)
        if not match_found:
            for alias in skill_synonyms.get(jd_skill_lc, []):
                if any(alias in cs or cs in alias for cs in candidate_lc):
                    match_found = True
                    match_mult  = 0.80
                    matched_caps.append(f"{jd_skill}≈{alias}")
                    break

        if match_found:
            raw_score += weight * match_mult

    return min(100, int((raw_score / max_possible) * 100)), matched_caps
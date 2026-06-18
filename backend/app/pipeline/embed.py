"""
pipeline/embed.py
───────────────────
Loads the sentence-transformers model exactly once per process (model
load is the expensive part, not inference) and exposes simple encode
functions used in two places only:

  1. Ingest task — embeds each candidate ONCE when they're added to the pool.
  2. Evaluate task — embeds the JD ONCE per evaluation (milliseconds).

Candidates are NEVER re-embedded at evaluation time. This is the fix
for the original 30-minute bottleneck.
"""

from functools import lru_cache

from sentence_transformers import SentenceTransformer

from app.config import get_settings

settings = get_settings()


@lru_cache(maxsize=1)
def _get_model() -> SentenceTransformer:
    return SentenceTransformer(settings.embedding_model_name)


def embed_text(text: str) -> list[float]:
    """Embed a single string (e.g. a job description)."""
    model = _get_model()
    vector = model.encode(text, convert_to_numpy=True, show_progress_bar=False)
    return vector.tolist()


def embed_texts_batch(texts: list[str], batch_size: int = 64) -> list[list[float]]:
    """
    Embed many strings efficiently. Used once at ingest time for a
    candidate batch — never re-run per evaluation.
    """
    model = _get_model()
    vectors = model.encode(
        texts,
        batch_size=batch_size,
        convert_to_numpy=True,
        show_progress_bar=False,
    )
    return vectors.tolist()

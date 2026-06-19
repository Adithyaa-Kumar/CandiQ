"""
config.py
─────────
Centralised, typed application settings loaded from environment variables.
Nothing here is hardcoded for a specific deployment — every value is
overridable via .env or real environment variables in production.
"""

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # ── App ──
    environment: str = "development"
    log_level: str = "INFO"
    api_v1_prefix: str = "/api/v1"

    # ── Database ──
    database_url: str = "postgresql://candiq:candiq_dev_password@localhost:5432/candiq"

    # ── Redis / Celery ──
    redis_url: str = "redis://localhost:6379/0"

    # ── Qdrant ──
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection_name: str = "candidates"

    # ── Gemini ──
    gemini_api_key: str = ""
    
    # Gemini Models
    gemini_panel_model: str = "gemini-2.5-flash"
    gemini_arbitrator_model: str = "gemini-2.5-flash"
    gemini_fast_model: str = "gemini-2.5-flash"
    
    # ── Security ──
    jwt_secret_key: str = "insecure-dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    # ── CORS ──
    cors_origins: str = "http://localhost:3000"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    # ── Rate limiting ──
    rate_limit_per_minute: int = 20

    # ── Embeddings ──
    embedding_model_name: str = "all-MiniLM-L6-v2"

    # ── Retrieval / shortlist tuning ──
    shortlist_min_size: int = 5
    shortlist_max_size: int = 500
    shortlist_percentage: float = 0.10

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"


@lru_cache
def get_settings() -> Settings:
    """Cached settings instance — env is read once per process."""
    return Settings()

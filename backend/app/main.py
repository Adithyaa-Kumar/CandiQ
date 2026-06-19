"""
main.py
─────────
FastAPI application entrypoint. Run with:
  uvicorn app.main:app --reload
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.logging_conf import configure_logging, get_logger

settings = get_settings()
configure_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("app.startup", environment=settings.environment)
    yield
    logger.info("app.shutdown")


def _assert_prod_secrets() -> None:
    """Fail fast at startup rather than silently running with insecure defaults."""
    if not settings.is_production:
        return

    errors: list[str] = []

    if settings.jwt_secret_key == "insecure-dev-secret-change-me":
        errors.append("JWT_SECRET_KEY is still the insecure dev default — set a strong random value")

    if not settings.gemini_api_key:
        errors.append("GEMINI_API_KEY is not set — all agent calls will fail")

    flower_password = __import__("os").environ.get("FLOWER_PASSWORD", "changeme")
    if flower_password == "changeme":
        errors.append("FLOWER_PASSWORD is still the default 'changeme' — set a real password in .env")

    if errors:
        bullet_list = "\n  • ".join(errors)
        raise RuntimeError(
            f"CandiQ refusing to start in production with unsafe configuration:\n  • {bullet_list}"
        )


def create_app() -> FastAPI:
    _assert_prod_secrets()

    app = FastAPI(
        title="CandiQ API",
        version="2.0.0",
        description="AI-powered candidate ranking — multi-agent consensus panel over a hybrid-retrieved shortlist.",
        lifespan=lifespan,
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)
    app.include_router(api_router, prefix=settings.api_v1_prefix)

    return app


app = create_app()
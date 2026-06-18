"""
exceptions.py
─────────────
Domain-specific exceptions and the FastAPI handlers that convert them
into clean JSON error responses. Keeps business logic from importing
FastAPI/HTTPException directly — pipeline code stays framework-agnostic.
"""

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.core.rate_limit import RateLimitExceeded


class CandiQError(Exception):
    """Base class for all application-raised errors."""
    status_code = status.HTTP_400_BAD_REQUEST

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class InvalidInputError(CandiQError):
    status_code = status.HTTP_400_BAD_REQUEST


class NotFoundError(CandiQError):
    status_code = status.HTTP_404_NOT_FOUND


class AuthError(CandiQError):
    status_code = status.HTTP_401_UNAUTHORIZED


class PipelineError(CandiQError):
    """Raised when the evaluation pipeline (JD analysis, retrieval, agents) fails."""
    status_code = status.HTTP_502_BAD_GATEWAY


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(CandiQError)
    async def candiq_error_handler(request: Request, exc: CandiQError):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})

    @app.exception_handler(RateLimitExceeded)
    async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={"detail": "Rate limit exceeded. Please slow down."},
            headers={"Retry-After": str(exc.retry_after)},
        )

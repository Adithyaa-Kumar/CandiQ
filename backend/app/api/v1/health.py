"""
api/v1/health.py
───────────────────
/health        — liveness: is the process up at all
/health/ready  — readiness: can we actually reach Postgres, Redis, Qdrant
"""

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.config import get_settings

router = APIRouter(prefix="/health", tags=["health"])
settings = get_settings()


@router.get("")
def liveness():
    return {"status": "ok"}


@router.get("/ready")
def readiness(db: Session = Depends(get_db)):
    checks = {"postgres": False, "redis": False, "qdrant": False}

    try:
        db.execute(text("SELECT 1"))
        checks["postgres"] = True
    except Exception:
        pass

    try:
        import redis
        r = redis.from_url(settings.redis_url)
        r.ping()
        checks["redis"] = True
    except Exception:
        pass

    try:
        from app.vector_store.qdrant_client import get_qdrant_client
        get_qdrant_client().get_collections()
        checks["qdrant"] = True
    except Exception:
        pass

    all_ok = all(checks.values())
    return {"status": "ok" if all_ok else "degraded", "checks": checks}

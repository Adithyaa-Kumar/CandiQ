"""
api/v1/router.py
───────────────────
Aggregates every v1 sub-router. main.py mounts this single router
under the configured API prefix.
"""

from fastapi import APIRouter

from app.api.v1 import auth, candidates, health, jobs

api_router = APIRouter()

api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(candidates.router)
api_router.include_router(jobs.router)

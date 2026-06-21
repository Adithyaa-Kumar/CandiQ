"""
api/v1/pools.py
─────────────────
Candidate pool management endpoints.

BUG FIXES applied:
  1. Original GET /{pool_id} returned 500 if pool was not found (no null
     check before accessing pool.id). Added 404 guard.
  2. Added GET / to list all pools for the current user — the frontend
     needs this so a recruiter can see which pools are available and
     switch between them rather than always using the latest.
  3. pool_id is a UUID — parsing a malformed string caused an unhandled
     ValueError. Added try/except with 422.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_current_user
from app.db.models.candidate_pool import CandidatePool

router = APIRouter(prefix="/pools", tags=["pools"])


@router.get("")
def list_pools(
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """List all candidate pools owned by the current user, newest first."""
    pools = (
        db.query(CandidatePool)
        .filter(CandidatePool.owner_id == user.id)
        .order_by(CandidatePool.created_at.desc())
        .all()
    )
    return [
        {
            "id": str(p.id),
            "name": p.name,
            "status": p.status.value,
            "created_at": p.created_at.isoformat(),
        }
        for p in pools
    ]


@router.get("/{pool_id}")
def get_pool_status(
    pool_id: str,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    # FIX 3: handle malformed UUID
    try:
        pool_uuid = uuid.UUID(pool_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid pool_id format")

    pool = (
        db.query(CandidatePool)
        .filter(
            CandidatePool.id == pool_uuid,
            CandidatePool.owner_id == user.id,
        )
        .first()
    )

    # FIX 1: was missing null check — would 500 on missing pool
    if not pool:
        raise HTTPException(status_code=404, detail="Pool not found")

    return {
        "id": str(pool.id),
        "name": pool.name,
        "status": pool.status.value,
        "created_at": pool.created_at.isoformat(),
    }
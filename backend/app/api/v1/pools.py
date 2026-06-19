# api/v1/pools.py

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_current_user
from app.db.models.candidate_pool import CandidatePool

router = APIRouter(prefix="/pools", tags=["pools"])

@router.get("/{pool_id}")
def get_pool_status(
    pool_id: str,
    db: Session = Depends(get_db),
    user = Depends(get_current_user),
):
    pool = (
        db.query(CandidatePool)
        .filter(
            CandidatePool.id == pool_id,
            CandidatePool.owner_id == user.id,
        )
        .first()
    )

    return {
        "id": str(pool.id),
        "status": pool.status.value,
    }
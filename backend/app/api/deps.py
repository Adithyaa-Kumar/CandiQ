"""
deps.py
───────
Shared dependencies injected into route handlers:
  - get_db          → DB session (re-exported from db.session for convenience)
  - get_current_user → decodes JWT bearer token, loads User, raises 401 if invalid
  - enforce_rate_limit → per-user rate limiting for expensive routes
"""

import uuid

from fastapi import Depends, Header
from jose import JWTError
from sqlalchemy.orm import Session

from app.core.exceptions import AuthError
from app.core.rate_limit import check_rate_limit
from app.core.security import decode_token
from app.db.models.user import User
from app.db.session import get_db

__all__ = ["get_db", "get_current_user", "enforce_rate_limit"]


def get_current_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise AuthError("Missing or malformed Authorization header")

    token = authorization.split(" ", 1)[1]

    try:
        payload = decode_token(token)
    except JWTError:
        raise AuthError("Invalid or expired token")

    if payload.get("type") != "access":
        raise AuthError("Wrong token type — use an access token")

    user_id = payload.get("sub")
    if not user_id:
        raise AuthError("Token missing subject")

    user = db.get(User, uuid.UUID(user_id))
    if not user or not user.is_active:
        raise AuthError("User not found or inactive")

    return user


def enforce_rate_limit(user: User = Depends(get_current_user)) -> None:
    check_rate_limit(key=f"user:{user.id}")

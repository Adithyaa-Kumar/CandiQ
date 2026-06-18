"""
api/v1/auth.py
────────────────
Registration, login, and token refresh. Standard JWT access+refresh
pattern — access tokens are short-lived (30 min default), refresh
tokens are long-lived (7 days default) and used solely to mint new
access tokens.
"""

import uuid

from fastapi import APIRouter, Depends
from jose import JWTError
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.exceptions import AuthError, InvalidInputError
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.db.models.user import User
from app.schemas.user import RefreshRequest, TokenResponse, UserLogin, UserRegister, UserResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserResponse, status_code=201)
def register(payload: UserRegister, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == payload.email).first()
    if existing:
        raise InvalidInputError("An account with this email already exists")

    user = User(
        id=uuid.uuid4(),
        email=payload.email,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/login", response_model=TokenResponse)
def login(payload: UserLogin, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email).first()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise AuthError("Incorrect email or password")
    if not user.is_active:
        raise AuthError("This account has been deactivated")

    return TokenResponse(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
    )


@router.post("/refresh", response_model=TokenResponse)
def refresh(payload: RefreshRequest, db: Session = Depends(get_db)):
    try:
        decoded = decode_token(payload.refresh_token)
    except JWTError:
        raise AuthError("Invalid or expired refresh token")

    if decoded.get("type") != "refresh":
        raise AuthError("Wrong token type — use a refresh token")

    user_id = uuid.UUID(decoded["sub"])
    user = db.get(User, user_id)
    if not user or not user.is_active:
        raise AuthError("User not found or inactive")

    return TokenResponse(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
    )

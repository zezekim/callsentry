from __future__ import annotations

import asyncio
import secrets

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select

from callsentry.api.deps import SessionDep, UserDep
from callsentry.core.security import hash_password, issue_token, verify_password
from callsentry.models import User

router = APIRouter(prefix="/auth", tags=["auth"])

# Compared against when the email doesn't exist, so a missing account and a
# wrong password take the same amount of time.
_DUMMY_HASH = hash_password(secrets.token_urlsafe(16))


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"  # noqa: S105 - OAuth scheme name, not a secret
    role: str
    business_id: str


class MeResponse(BaseModel):
    id: str
    email: str
    role: str
    business_id: str


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, session: SessionDep) -> TokenResponse:
    user = await session.scalar(select(User).where(User.email == payload.email.lower()))

    stored = user.password_hash if user else _DUMMY_HASH
    ok = await asyncio.to_thread(verify_password, payload.password, stored)
    if not user or not ok:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid email or password")

    return TokenResponse(
        access_token=issue_token(
            user_id=str(user.id), business_id=str(user.business_id), role=user.role
        ),
        role=user.role,
        business_id=str(user.business_id),
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout() -> None:
    """Stateless JWTs - the client discards the token. Present for symmetry."""
    return None


@router.get("/me", response_model=MeResponse)
async def me(user: UserDep) -> MeResponse:
    return MeResponse(
        id=str(user.id), email=user.email, role=user.role, business_id=str(user.business_id)
    )

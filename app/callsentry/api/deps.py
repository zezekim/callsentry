"""Shared FastAPI dependencies: auth, tenancy, and internal-service access."""

from __future__ import annotations

import uuid
from typing import Annotated

import jwt
import structlog
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from callsentry.config import Settings, get_settings
from callsentry.core.db import get_session
from callsentry.core.security import decode_token
from callsentry.models import Business, User, UserRole

log = structlog.get_logger(__name__)

bearer = HTTPBearer(auto_error=False)

SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


async def current_user(
    session: SessionDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)] = None,
) -> User:
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    try:
        payload = decode_token(credentials.credentials)
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "token expired") from exc
    except jwt.PyJWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid token") from exc

    user = await session.get(User, uuid.UUID(payload["sub"]))
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "user no longer exists")
    return user


UserDep = Annotated[User, Depends(current_user)]


async def current_business(session: SessionDep, user: UserDep) -> Business:
    business = await session.get(Business, user.business_id)
    if business is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "business not found")
    return business


BusinessDep = Annotated[Business, Depends(current_business)]


async def require_operator(user: UserDep) -> User:
    """Platform staff only - cross-tenant provisioning and cost views."""
    if user.role != UserRole.OPERATOR:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "operator role required")
    return user


OperatorDep = Annotated[User, Depends(require_operator)]


async def require_internal(
    settings: SettingsDep,
    x_internal_token: Annotated[str | None, Header()] = None,
) -> None:
    """Guards endpoints that only the Pipecat container may call.

    Compared with `secrets.compare_digest` to keep the check constant-time.
    """
    import secrets

    if not x_internal_token or not secrets.compare_digest(
        x_internal_token, settings.internal_api_token
    ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "invalid internal token")


InternalDep = Annotated[None, Depends(require_internal)]

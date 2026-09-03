from __future__ import annotations

import base64
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from callsentry.api.deps import BusinessDep, OperatorDep, SessionDep, UserDep
from callsentry.config import get_settings
from callsentry.core.providers import get_registry
from callsentry.core.security import hash_password, mask
from callsentry.models import User, UserRole
from callsentry.services import platform_settings
from callsentry.services.calcom import CalComError, CalComService
from callsentry.services.credentials import read_credential, write_credential
from callsentry.services.tts import get_tts

router = APIRouter(prefix="/settings", tags=["settings"])


class SettingsOut(BaseModel):
    business_id: str
    name: str
    timezone: str
    business_hours: dict[str, Any]
    escalation_phone: str | None
    after_hours_message: str | None
    greeting_override: str | None
    twilio_number: str | None
    voice_id: str
    cal_com_event_type_id: str | None
    # Never the value itself - only whether one is set, and a masked tail.
    cal_com_api_key: str
    local_only: bool


class SettingsPatch(BaseModel):
    name: str | None = None
    timezone: str | None = None
    business_hours: dict[str, Any] | None = None
    escalation_phone: str | None = None
    after_hours_message: str | None = None
    greeting_override: str | None = None
    twilio_number: str | None = None
    voice_id: str | None = None


class ConnectCalRequest(BaseModel):
    api_key: str = Field(min_length=8)
    event_type_id: str


class ConnectCalResult(BaseModel):
    connected: bool
    detail: str


class VoiceTestRequest(BaseModel):
    text: str = Field(default="Hi, thanks for calling. How can I help you today?", max_length=400)
    voice: str | None = None


def _out(business: Any) -> SettingsOut:
    return SettingsOut(
        business_id=str(business.id),
        name=business.name,
        timezone=business.timezone,
        business_hours=business.business_hours,
        escalation_phone=business.escalation_phone,
        after_hours_message=business.after_hours_message,
        greeting_override=business.greeting_override,
        twilio_number=business.twilio_number,
        voice_id=business.voice_id,
        cal_com_event_type_id=business.cal_com_event_type_id,
        cal_com_api_key=mask(read_credential(business, "cal_com_api_key_enc")),
        local_only=get_settings().local_only,
    )


@router.get("", response_model=SettingsOut)
async def read_settings(business: BusinessDep) -> SettingsOut:
    return _out(business)


@router.patch("", response_model=SettingsOut)
async def patch_settings(
    payload: SettingsPatch, session: SessionDep, business: BusinessDep
) -> SettingsOut:
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(business, field, value)
    await session.flush()
    return _out(business)


@router.get("/providers")
async def providers(refresh: bool = False) -> dict[str, Any]:
    """Live health of every provider in every chain."""
    registry = get_registry()
    snapshot = await registry.snapshot(refresh=refresh)
    return {
        "local_only": get_settings().local_only,
        "components": snapshot,
    }


@router.post("/test-voice")
async def test_voice(payload: VoiceTestRequest, business: BusinessDep) -> Response:
    """Synthesise a sample so the operator can hear the configured voice."""
    result = await get_tts().synthesize(payload.text, voice=payload.voice or business.voice_id)
    return Response(
        content=result.audio,
        media_type=result.mime_type,
        headers={
            "X-Provider": result.provider,
            "X-Tier": result.tier,
            "X-Cost-USD": f"{result.cost_usd:.6f}",
        },
    )


@router.post("/connect-cal", response_model=ConnectCalResult)
async def connect_cal(
    payload: ConnectCalRequest, session: SessionDep, business: BusinessDep
) -> ConnectCalResult:
    """Validate the credentials against Cal.com before storing them.

    Storing an unvalidated key means the first real caller discovers it's
    wrong, mid-booking. Better to fail here.
    """
    from datetime import UTC, datetime, timedelta

    probe = CalComService(api_key=payload.api_key, event_type_id=payload.event_type_id)
    now = datetime.now(UTC)
    try:
        await probe.available_slots(
            start=now, end=now + timedelta(days=3), timezone=business.timezone
        )
    except CalComError as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"Cal.com rejected those credentials: {exc}"
        ) from exc

    write_credential(business, "cal_com_api_key_enc", payload.api_key)
    business.cal_com_event_type_id = payload.event_type_id
    await session.flush()
    return ConnectCalResult(connected=True, detail="Cal.com connected and verified.")


@router.get("/voices")
async def list_voices() -> dict[str, list[dict[str, str]]]:
    """Kokoro voice catalogue for the settings dropdown."""
    return {
        "voices": [
            {"id": "af_heart", "label": "Heart (US, warm)"},
            {"id": "af_bella", "label": "Bella (US, bright)"},
            {"id": "af_nicole", "label": "Nicole (US, soft)"},
            {"id": "am_michael", "label": "Michael (US, male)"},
            {"id": "am_fenrir", "label": "Fenrir (US, male, deep)"},
            {"id": "bf_emma", "label": "Emma (UK, female)"},
            {"id": "bm_george", "label": "George (UK, male)"},
        ]
    }


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


# --- Users -------------------------------------------------------------------

PASSWORD_MIN_LENGTH = 10


class UserOut(BaseModel):
    id: str
    email: str
    role: str
    created_at: datetime
    is_current_user: bool


class CreateUserRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=PASSWORD_MIN_LENGTH)
    role: UserRole = UserRole.ADMIN


class SetPasswordRequest(BaseModel):
    password: str = Field(min_length=PASSWORD_MIN_LENGTH)


def _user_out(user: User, current: User) -> UserOut:
    return UserOut(
        id=str(user.id),
        email=user.email,
        role=user.role,
        created_at=user.created_at,
        is_current_user=user.id == current.id,
    )


def _normalise_email(email: str) -> str:
    # Deliberately not EmailStr: it rejects reserved domains such as the seeded
    # demo@callsentry.local, and uniqueness is enforced by the database anyway.
    value = email.strip().lower()
    local, _, domain = value.partition("@")
    if not local or not domain or " " in value:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "enter a valid email address")
    return value


async def _business_user(session: Any, business: Any, user_id: uuid.UUID) -> User:
    target = await session.get(User, user_id)
    if target is None or target.business_id != business.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user not found")
    return target


@router.get("/users", response_model=list[UserOut])
async def list_users(session: SessionDep, business: BusinessDep, user: UserDep) -> list[UserOut]:
    rows = await session.scalars(
        select(User).where(User.business_id == business.id).order_by(User.created_at)
    )
    return [_user_out(row, user) for row in rows]


@router.post("/users", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: CreateUserRequest, session: SessionDep, business: BusinessDep, user: UserDep
) -> UserOut:
    if payload.role == UserRole.OPERATOR and user.role != UserRole.OPERATOR:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "only a platform operator can create operator accounts"
        )
    email = _normalise_email(payload.email)
    if await session.scalar(select(User).where(User.email == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "that email address is already in use")

    created = User(
        business_id=business.id,
        email=email,
        password_hash=hash_password(payload.password),
        role=payload.role,
    )
    session.add(created)
    await session.flush()
    return _user_out(created, user)


@router.put("/users/{user_id}/password", status_code=status.HTTP_204_NO_CONTENT)
async def set_user_password(
    user_id: uuid.UUID,
    payload: SetPasswordRequest,
    session: SessionDep,
    business: BusinessDep,
) -> None:
    target = await _business_user(session, business, user_id)
    target.password_hash = hash_password(payload.password)
    await session.flush()


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: uuid.UUID, session: SessionDep, business: BusinessDep, user: UserDep
) -> None:
    if user_id == user.id:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "you cannot remove your own account while signed in"
        )
    target = await _business_user(session, business, user_id)
    remaining = await session.scalar(
        select(func.count(User.id)).where(User.business_id == business.id)
    )
    if (remaining or 0) <= 1:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "a business must keep at least one user")
    await session.delete(target)
    await session.flush()


# --- Platform configuration ------------------------------------------------


class PlatformSettingsOut(BaseModel):
    can_edit: bool
    groups: list[dict[str, str]]
    fields: list[dict[str, Any]]


class PlatformSettingsUpdate(BaseModel):
    # key -> new value as typed. None or "" clears the override so the
    # environment value applies again.
    values: dict[str, str | None]


async def _platform_out(session: Any, user: User) -> PlatformSettingsOut:
    return PlatformSettingsOut(
        can_edit=user.role == UserRole.OPERATOR,
        groups=[{"id": gid, "label": label} for gid, label in platform_settings.GROUPS],
        fields=await platform_settings.describe(session),
    )


@router.get("/platform", response_model=PlatformSettingsOut)
async def read_platform_settings(session: SessionDep, user: UserDep) -> PlatformSettingsOut:
    """Effective platform configuration. Secrets are masked; admins see, operators edit."""
    return await _platform_out(session, user)


@router.put("/platform", response_model=PlatformSettingsOut)
async def update_platform_settings(
    payload: PlatformSettingsUpdate, session: SessionDep, user: OperatorDep
) -> PlatformSettingsOut:
    try:
        await platform_settings.update(session, payload.values)
    except platform_settings.SettingsValidationError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return await _platform_out(session, user)

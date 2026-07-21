from __future__ import annotations

import base64
from typing import Any

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import Response
from pydantic import BaseModel, Field

from callsentry.api.deps import BusinessDep, SessionDep
from callsentry.config import get_settings
from callsentry.core.providers import get_registry
from callsentry.core.security import mask
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

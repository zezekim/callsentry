from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select

from callsentry.api.deps import OperatorDep, SessionDep
from callsentry.core.security import hash_password
from callsentry.models import Business, Call, CostEntry, User, UserRole
from callsentry.models.business import DEFAULT_HOURS

router = APIRouter(prefix="/admin", tags=["admin"])


class ProvisionRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    timezone: str = "UTC"
    admin_email: EmailStr
    admin_password: str = Field(min_length=10)
    twilio_number: str | None = None
    escalation_phone: str | None = None


class BusinessOut(BaseModel):
    id: str
    name: str
    timezone: str
    twilio_number: str | None
    call_count: int
    total_cost_usd: float
    created_at: datetime


class PlatformCosts(BaseModel):
    total_usd: float
    by_tier: dict[str, float]
    by_category: dict[str, float]
    by_business: list[dict[str, str | float]]
    local_share_pct: float


@router.post("/businesses", response_model=BusinessOut, status_code=status.HTTP_201_CREATED)
async def provision(
    payload: ProvisionRequest, session: SessionDep, _: OperatorDep
) -> BusinessOut:
    existing = await session.scalar(select(User).where(User.email == payload.admin_email.lower()))
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT, "that admin email is already in use")

    business = Business(
        name=payload.name,
        timezone=payload.timezone,
        business_hours=dict(DEFAULT_HOURS),
        twilio_number=payload.twilio_number,
        escalation_phone=payload.escalation_phone,
        after_hours_message=(
            f"Thanks for calling {payload.name}. We're closed right now, "
            "but I can take a message."
        ),
    )
    session.add(business)
    await session.flush()

    session.add(
        User(
            business_id=business.id,
            email=payload.admin_email.lower(),
            password_hash=hash_password(payload.admin_password),
            role=UserRole.ADMIN,
        )
    )
    await session.flush()

    return BusinessOut(
        id=str(business.id),
        name=business.name,
        timezone=business.timezone,
        twilio_number=business.twilio_number,
        call_count=0,
        total_cost_usd=0.0,
        created_at=business.created_at,
    )


@router.get("/businesses", response_model=list[BusinessOut])
async def list_businesses(session: SessionDep, _: OperatorDep) -> list[BusinessOut]:
    rows = (
        await session.execute(
            select(
                Business,
                func.count(Call.id),
                func.coalesce(func.sum(Call.cost_usd), 0),
            )
            .outerjoin(Call, Call.business_id == Business.id)
            .group_by(Business.id)
            .order_by(Business.created_at.desc())
        )
    ).all()

    return [
        BusinessOut(
            id=str(b.id),
            name=b.name,
            timezone=b.timezone,
            twilio_number=b.twilio_number,
            call_count=int(count),
            total_cost_usd=round(float(total), 4),
            created_at=b.created_at,
        )
        for b, count, total in rows
    ]


@router.delete("/businesses/{business_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_business(
    business_id: uuid.UUID, session: SessionDep, _: OperatorDep
) -> None:
    """Hard delete, cascading to calls, appointments, KB, users, and costs.

    This is the GDPR Article 17 path. It is irreversible by design - a soft
    delete would not satisfy an erasure request.
    """
    business = await session.get(Business, business_id)
    if business is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "business not found")
    await session.delete(business)


@router.get("/costs", response_model=PlatformCosts)
async def platform_costs(session: SessionDep, _: OperatorDep) -> PlatformCosts:
    tier_rows = (
        await session.execute(
            select(CostEntry.tier, func.sum(CostEntry.cost_usd), func.count(CostEntry.id))
            .group_by(CostEntry.tier)
        )
    ).all()
    category_rows = (
        await session.execute(
            select(CostEntry.category, func.sum(CostEntry.cost_usd)).group_by(CostEntry.category)
        )
    ).all()
    business_rows = (
        await session.execute(
            select(Business.name, func.coalesce(func.sum(CostEntry.cost_usd), 0))
            .outerjoin(CostEntry, CostEntry.business_id == Business.id)
            .group_by(Business.id, Business.name)
            .order_by(func.coalesce(func.sum(CostEntry.cost_usd), 0).desc())
        )
    ).all()

    by_tier = {tier: round(float(total or 0), 6) for tier, total, _ in tier_rows}
    counts = {tier: int(count) for tier, _, count in tier_rows}
    total_ops = sum(counts.values())

    return PlatformCosts(
        total_usd=round(sum(by_tier.values()), 6),
        by_tier=by_tier,
        by_category={c: round(float(t or 0), 6) for c, t in category_rows},
        by_business=[{"name": n, "cost_usd": round(float(t or 0), 6)} for n, t in business_rows],
        local_share_pct=round(counts.get("local", 0) / total_ops * 100, 1) if total_ops else 100.0,
    )

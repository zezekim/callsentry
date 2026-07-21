from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import Integer, cast, func, select

from callsentry.api.deps import BusinessDep, SessionDep
from callsentry.models import Call, CallOutcome
from callsentry.services import costs

router = APIRouter(prefix="/analytics", tags=["analytics"])


class TimePoint(BaseModel):
    date: str
    calls: int
    bookings: int
    escalations: int
    cost_usd: float


class Analytics(BaseModel):
    volume: list[TimePoint]
    peak_hours: list[dict[str, int]]
    booking_conversion_pct: float
    escalation_rate_pct: float
    avg_cost_per_call_usd: float
    cost_by_category: dict[str, dict[str, float]]
    top_topics: list[dict[str, str | int]]


@router.get("", response_model=Analytics)
async def analytics(
    session: SessionDep, business: BusinessDep, days: int = 30
) -> Analytics:
    since = datetime.now(UTC) - timedelta(days=days)

    day = func.date_trunc("day", Call.created_at)
    volume_rows = (
        await session.execute(
            select(
                day.label("day"),
                func.count(Call.id),
                func.count(Call.id).filter(Call.outcome == CallOutcome.BOOKED),
                func.count(Call.id).filter(Call.escalated.is_(True)),
                func.coalesce(func.sum(Call.cost_usd), 0),
            )
            .where(Call.business_id == business.id, Call.created_at >= since)
            .group_by(day)
            .order_by(day)
        )
    ).all()

    hour = cast(func.extract("hour", Call.created_at), Integer)
    hour_rows = (
        await session.execute(
            select(hour.label("hour"), func.count(Call.id))
            .where(Call.business_id == business.id, Call.created_at >= since)
            .group_by(hour)
            .order_by(hour)
        )
    ).all()

    totals = (
        await session.execute(
            select(
                func.count(Call.id),
                func.count(Call.id).filter(Call.outcome == CallOutcome.BOOKED),
                func.count(Call.id).filter(Call.escalated.is_(True)),
                func.coalesce(func.sum(Call.cost_usd), 0),
            ).where(Call.business_id == business.id, Call.created_at >= since)
        )
    ).one()

    total_calls = int(totals[0] or 0)
    breakdown = await costs.business_breakdown(session, business.id)

    return Analytics(
        volume=[
            TimePoint(
                date=d.date().isoformat(),
                calls=int(c),
                bookings=int(b),
                escalations=int(e),
                cost_usd=round(float(cost), 4),
            )
            for d, c, b, e, cost in volume_rows
        ],
        peak_hours=[{"hour": int(h), "calls": int(c)} for h, c in hour_rows],
        booking_conversion_pct=(
            round(int(totals[1] or 0) / total_calls * 100, 1) if total_calls else 0.0
        ),
        escalation_rate_pct=(
            round(int(totals[2] or 0) / total_calls * 100, 1) if total_calls else 0.0
        ),
        avg_cost_per_call_usd=(
            round(float(totals[3] or 0) / total_calls, 4) if total_calls else 0.0
        ),
        cost_by_category={k: {kk: round(vv, 6) for kk, vv in v.items()}
                          for k, v in breakdown.items()},
        top_topics=await _top_topics(session, business.id, since),
    )


async def _top_topics(session: SessionDep, business_id: object, since: datetime) -> list[dict]:
    """Most common FAQ subjects, derived from call summaries.

    Topics are stored per-call by the analysis step; this counts the keywords
    that actually appear in summaries as a cheap proxy until there is enough
    volume to justify a dedicated topics table.
    """
    rows = (
        await session.scalars(
            select(Call.summary).where(
                Call.business_id == business_id,
                Call.created_at >= since,
                Call.summary.isnot(None),
            )
        )
    ).all()

    keywords = [
        "pricing", "price", "cost", "hours", "location", "address", "parking",
        "cancel", "reschedule", "insurance", "availability", "booking", "warranty",
    ]
    counts: dict[str, int] = {}
    for summary in rows:
        lowered = (summary or "").lower()
        for word in keywords:
            if word in lowered:
                counts[word] = counts.get(word, 0) + 1

    ranked = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[:8]
    return [{"topic": t, "count": c} for t, c in ranked]

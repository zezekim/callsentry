from __future__ import annotations

import csv
import io
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import Select, func, select

from callsentry.api.deps import BusinessDep, SessionDep
from callsentry.models import Call, CallOutcome, CostEntry, Sentiment

router = APIRouter(prefix="/calls", tags=["calls"])


class CallSummary(BaseModel):
    id: str
    caller_number: str
    duration_seconds: int
    outcome: str
    sentiment: str | None
    escalated: bool
    cost_usd: float
    created_at: datetime


class CallDetail(CallSummary):
    transcript: str | None
    summary: str | None
    recording_url: str | None
    escalation_reason: str | None
    provider_log: list[dict[str, Any]]


class CallStats(BaseModel):
    calls_today: int
    bookings_today: int
    escalations_today: int
    avg_duration_seconds: float
    cost_today_usd: float
    cost_all_time_usd: float
    local_share_pct: float
    sentiment: dict[str, int]
    outcomes: dict[str, int]


def _filtered(
    business_id: uuid.UUID,
    *,
    outcome: str | None,
    sentiment: str | None,
    since: datetime | None,
    until: datetime | None,
    search: str | None,
) -> Select[tuple[Call]]:
    stmt = select(Call).where(Call.business_id == business_id)
    if outcome:
        stmt = stmt.where(Call.outcome == outcome)
    if sentiment:
        stmt = stmt.where(Call.sentiment == sentiment)
    if since:
        stmt = stmt.where(Call.created_at >= since)
    if until:
        stmt = stmt.where(Call.created_at <= until)
    if search:
        pattern = f"%{search}%"
        stmt = stmt.where(
            Call.transcript.ilike(pattern)
            | Call.summary.ilike(pattern)
            | Call.caller_number.ilike(pattern)
        )
    return stmt


@router.get("", response_model=list[CallSummary])
async def list_calls(
    session: SessionDep,
    business: BusinessDep,
    outcome: str | None = None,
    sentiment: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    search: str | None = None,
    limit: Annotated[int, Query(le=200)] = 50,
    offset: int = 0,
) -> list[CallSummary]:
    stmt = (
        _filtered(business.id, outcome=outcome, sentiment=sentiment, since=since,
                  until=until, search=search)
        .order_by(Call.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    rows = (await session.scalars(stmt)).all()
    return [_summary(c) for c in rows]


@router.get("/stats", response_model=CallStats)
async def stats(session: SessionDep, business: BusinessDep) -> CallStats:
    day_start = datetime.now(UTC) - timedelta(hours=24)

    today = (
        await session.execute(
            select(
                func.count(Call.id),
                func.coalesce(func.avg(Call.duration_seconds), 0),
                func.coalesce(func.sum(Call.cost_usd), 0),
            ).where(Call.business_id == business.id, Call.created_at >= day_start)
        )
    ).one()

    bookings = await session.scalar(
        select(func.count(Call.id)).where(
            Call.business_id == business.id,
            Call.created_at >= day_start,
            Call.outcome == CallOutcome.BOOKED,
        )
    )
    escalations = await session.scalar(
        select(func.count(Call.id)).where(
            Call.business_id == business.id,
            Call.created_at >= day_start,
            Call.escalated.is_(True),
        )
    )
    all_time_cost = await session.scalar(
        select(func.coalesce(func.sum(Call.cost_usd), 0)).where(Call.business_id == business.id)
    )

    sentiment_rows = (
        await session.execute(
            select(Call.sentiment, func.count(Call.id))
            .where(Call.business_id == business.id, Call.sentiment.isnot(None))
            .group_by(Call.sentiment)
        )
    ).all()
    outcome_rows = (
        await session.execute(
            select(Call.outcome, func.count(Call.id))
            .where(Call.business_id == business.id)
            .group_by(Call.outcome)
        )
    ).all()

    # Share of provider interactions served without paying anyone.
    tier_rows = (
        await session.execute(
            select(CostEntry.tier, func.count(CostEntry.id))
            .where(CostEntry.business_id == business.id)
            .group_by(CostEntry.tier)
        )
    ).all()
    tier_counts = {tier: count for tier, count in tier_rows}
    total_ops = sum(tier_counts.values())
    local_share = (tier_counts.get("local", 0) / total_ops * 100) if total_ops else 100.0

    return CallStats(
        calls_today=int(today[0] or 0),
        bookings_today=int(bookings or 0),
        escalations_today=int(escalations or 0),
        avg_duration_seconds=round(float(today[1] or 0), 1),
        cost_today_usd=round(float(today[2] or 0), 4),
        cost_all_time_usd=round(float(all_time_cost or 0), 4),
        local_share_pct=round(local_share, 1),
        sentiment={s: c for s, c in sentiment_rows} or {s.value: 0 for s in Sentiment},
        outcomes={o: c for o, c in outcome_rows},
    )


@router.get("/export")
async def export_csv(
    session: SessionDep,
    business: BusinessDep,
    outcome: str | None = None,
    sentiment: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
) -> StreamingResponse:
    stmt = _filtered(
        business.id, outcome=outcome, sentiment=sentiment, since=since, until=until, search=None
    ).order_by(Call.created_at.desc())
    rows = (await session.scalars(stmt)).all()

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        ["id", "created_at", "caller_number", "duration_seconds", "outcome",
         "sentiment", "escalated", "escalation_reason", "cost_usd", "summary"]
    )
    for call in rows:
        writer.writerow(
            [str(call.id), call.created_at.isoformat(), call.caller_number,
             call.duration_seconds, call.outcome, call.sentiment or "",
             call.escalated, call.escalation_reason or "",
             f"{float(call.cost_usd):.6f}", (call.summary or "").replace("\n", " ")]
        )
    buffer.seek(0)

    stamp = datetime.now(UTC).strftime("%Y%m%d")
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="calls-{stamp}.csv"'},
    )


@router.get("/{call_id}", response_model=CallDetail)
async def get_call(call_id: uuid.UUID, session: SessionDep, business: BusinessDep) -> CallDetail:
    call = await session.get(Call, call_id)
    # Same 404 whether the row is missing or belongs to another tenant - a
    # different response would leak the existence of other businesses' calls.
    if call is None or call.business_id != business.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "call not found")

    base = _summary(call)
    return CallDetail(
        **base.model_dump(),
        transcript=call.transcript,
        summary=call.summary,
        recording_url=call.recording_url,
        escalation_reason=call.escalation_reason,
        provider_log=call.provider_log or [],
    )


def _summary(call: Call) -> CallSummary:
    return CallSummary(
        id=str(call.id),
        caller_number=call.caller_number,
        duration_seconds=call.duration_seconds,
        outcome=call.outcome,
        sentiment=call.sentiment,
        escalated=call.escalated,
        cost_usd=round(float(call.cost_usd), 6),
        created_at=call.created_at,
    )

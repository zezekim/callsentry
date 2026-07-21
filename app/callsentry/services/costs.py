"""Cost ledger.

Every provider interaction writes a row, including free local ones at $0.00.
The call's denormalised `cost_usd` is recomputed from the ledger rather than
incremented in place, so a retried webhook cannot double-count.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from callsentry.models import Call, CostCategory, CostEntry

log = structlog.get_logger(__name__)


async def record(
    session: AsyncSession,
    *,
    business_id: uuid.UUID,
    call_id: uuid.UUID | None,
    category: CostCategory | str,
    provider: str,
    tier: str = "local",
    units: float = 1.0,
    unit_name: str = "call",
    cost_usd: float = 0.0,
) -> CostEntry:
    entry = CostEntry(
        business_id=business_id,
        call_id=call_id,
        category=str(category),
        provider=provider,
        tier=tier,
        units=Decimal(str(round(units, 4))),
        unit_name=unit_name,
        cost_usd=Decimal(str(round(cost_usd, 6))),
    )
    session.add(entry)
    await session.flush()
    return entry


async def recompute_call_cost(session: AsyncSession, call_id: uuid.UUID) -> float:
    """Sum the ledger for a call and write it back onto the call row."""
    total = await session.scalar(
        select(func.coalesce(func.sum(CostEntry.cost_usd), 0)).where(CostEntry.call_id == call_id)
    )
    total_f = float(total or 0)
    call = await session.get(Call, call_id)
    if call is not None:
        call.cost_usd = Decimal(str(round(total_f, 6)))
    return total_f


async def business_breakdown(
    session: AsyncSession, business_id: uuid.UUID
) -> dict[str, dict[str, float]]:
    """Cost grouped by category and tier - powers the local-vs-cloud chart."""
    rows = (
        await session.execute(
            select(
                CostEntry.category,
                CostEntry.tier,
                func.sum(CostEntry.cost_usd),
                func.count(CostEntry.id),
            )
            .where(CostEntry.business_id == business_id)
            .group_by(CostEntry.category, CostEntry.tier)
        )
    ).all()

    out: dict[str, dict[str, float]] = {}
    for category, tier, total, count in rows:
        bucket = out.setdefault(category, {"cost_usd": 0.0, "calls": 0.0, "local_calls": 0.0})
        bucket["cost_usd"] += float(total or 0)
        bucket["calls"] += int(count)
        if tier == "local":
            bucket["local_calls"] += int(count)
    return out

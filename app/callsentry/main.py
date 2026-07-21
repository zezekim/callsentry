"""CallSentry API application."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from typing import Any

import structlog
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from callsentry import logging as app_logging
from callsentry.api.routes import (
    admin,
    analytics,
    appointments,
    auth,
    calls,
    internal,
    kb,
    webhooks,
)
from callsentry.api.routes import (
    settings as settings_routes,
)
from callsentry.config import get_settings
from callsentry.core.db import get_sessionmaker
from callsentry.core.providers import ProviderUnavailable, get_registry

log = structlog.get_logger(__name__)

BACKGROUND_INTERVAL_SECONDS = 60 * 30


async def _background_loop() -> None:
    """Retention sweep + appointment reminders, every 30 minutes."""
    from callsentry.agents.booking_agent import send_due_reminders
    from callsentry.services.retention import sweep

    while True:
        await asyncio.sleep(BACKGROUND_INTERVAL_SECONDS)
        try:
            async with get_sessionmaker()() as session:
                await sweep(session)
                sent = await send_due_reminders(session)
                await session.commit()
                if sent:
                    log.info("reminders.sent", count=sent)
        except Exception as exc:  # noqa: BLE001 - a failed sweep must not kill the loop
            log.error("background.failed", error=str(exc))


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    app_logging.configure(settings.log_level)

    snapshot = await get_registry().snapshot(refresh=True)
    for component, providers in snapshot.items():
        serving = next((p["provider"] for p in providers if p["healthy"]), "none")
        log.info("provider.selected", component=component, provider=serving)

    log.info(
        "callsentry.started",
        local_only=settings.local_only,
        public_base_url=settings.public_base_url,
    )

    task = asyncio.create_task(_background_loop())
    try:
        yield
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


app = FastAPI(
    title="CallSentry",
    version="1.0.0",
    description="Self-hosted, local-first AI voice receptionist.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    # The dashboard is the only browser client; it is served from the same
    # Caddy origin in production, so this matters only for local dev.
    allow_origins=["http://localhost:3000", get_settings().public_base_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(ProviderUnavailable)
async def provider_unavailable(_: Request, exc: ProviderUnavailable) -> JSONResponse:
    log.error("provider.chain_exhausted", error=str(exc))
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"detail": "no provider available for this operation"},
    )


@app.get("/health", tags=["health"])
async def health() -> dict[str, Any]:
    return {"status": "ok", "local_only": get_settings().local_only}


@app.get("/health/deep", tags=["health"])
async def health_deep() -> dict[str, Any]:
    """Health including a live database round-trip and provider probes."""
    from sqlalchemy import text

    database = "ok"
    try:
        async with get_sessionmaker()() as session:
            await session.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        database = f"error: {type(exc).__name__}"

    return {
        "status": "ok" if database == "ok" else "degraded",
        "database": database,
        "providers": await get_registry().snapshot(refresh=True),
    }


for router in (
    auth.router,
    calls.router,
    appointments.router,
    kb.router,
    settings_routes.router,
    analytics.router,
    webhooks.router,
    admin.router,
    internal.router,
):
    app.include_router(router)

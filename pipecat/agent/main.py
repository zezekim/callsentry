"""Twilio Media Streams websocket server.

Twilio connects here via <Connect><Stream> and exchanges JSON frames:

    inbound : connected -> start -> media* -> stop
    outbound: media (mu-law audio) | clear (flush) | mark

The websocket carries only audio. All conversation logic lives in the API's
/internal/turn endpoint, so this process stays stateless per call and can be
restarted without losing anything except in-flight audio.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os

import httpx
from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from agent.pipeline import CallContext, CallPipeline

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(message)s"
)
log = logging.getLogger("agent")

APP_BASE_URL = os.getenv("APP_BASE_URL", "http://app:8000")
WORKER_BASE_URL = os.getenv("WORKER_BASE_URL", "http://worker:8100")
INTERNAL_TOKEN = os.getenv("INTERNAL_API_TOKEN", "")

app = FastAPI(title="CallSentry Voice Agent", version="1.0.0")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "app": APP_BASE_URL, "worker": WORKER_BASE_URL}


async def _fetch_context(call_id: str) -> dict:
    """Ask the API for the greeting, voice, and business details."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            f"{APP_BASE_URL}/internal/call/{call_id}/context",
            headers={"X-Internal-Token": INTERNAL_TOKEN},
        )
        resp.raise_for_status()
        return dict(resp.json())


@app.websocket("/ws/call/{call_id}")
async def media_stream(websocket: WebSocket, call_id: str) -> None:
    await websocket.accept()
    log.info("stream opened call_id=%s", call_id)

    context = CallContext(call_id=call_id)
    pipeline = CallPipeline(
        context=context,
        send_json=websocket.send_json,
        app_base_url=APP_BASE_URL,
        worker_base_url=WORKER_BASE_URL,
        internal_token=INTERNAL_TOKEN,
    )

    try:
        while True:
            try:
                raw = await websocket.receive_text()
            except WebSocketDisconnect:
                log.info("caller disconnected call_id=%s", call_id)
                break

            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                continue

            event = message.get("event")

            if event == "start":
                start = message.get("start", {})
                context.stream_sid = start.get("streamSid", "")
                params = start.get("customParameters", {}) or {}

                # Prefer the parameters Twilio carried from the TwiML, and
                # fall back to the API if they're missing (e.g. a reconnect).
                context.greeting = params.get("greeting", "")
                context.voice = params.get("voice", "af_heart")
                if not context.greeting:
                    try:
                        fetched = await _fetch_context(call_id)
                        context.greeting = fetched.get("greeting", "")
                        context.voice = fetched.get("voice", context.voice)
                        context.business_name = fetched.get("business_name", "")
                    except httpx.HTTPError as exc:
                        log.error("context fetch failed call_id=%s error=%s", call_id, exc)

                log.info("stream started call_id=%s sid=%s", call_id, context.stream_sid)

                if context.greeting:
                    context.log_line("Assistant", context.greeting)
                    # Speak first - the caller should not have to say hello to
                    # a receptionist that answered.
                    asyncio.create_task(pipeline.say(context.greeting))

            elif event == "media":
                await pipeline.on_media(message["media"]["payload"])

                if pipeline.should_hangup:
                    # Let the closing line finish before dropping the line.
                    await asyncio.sleep(0.5)
                    log.info(
                        "ending call call_id=%s transfer_to=%s",
                        call_id,
                        pipeline.transfer_to,
                    )
                    break

            elif event == "stop":
                log.info("stream stopped call_id=%s", call_id)
                break

    except Exception:
        log.exception("stream error call_id=%s", call_id)
    finally:
        await pipeline.finish()
        await pipeline.close()
        try:
            await websocket.close()
        except RuntimeError:
            pass  # Already closed by the peer.
        log.info(
            "stream closed call_id=%s duration=%ss turns=%d",
            call_id,
            context.duration_seconds,
            len(context.transcript),
        )

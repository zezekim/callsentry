"""Seed a demo business, admin + operator users, and a starter FAQ document.

Idempotent: re-running only fills in what is missing.
"""

from __future__ import annotations

import asyncio

import structlog
from sqlalchemy import select

from callsentry import logging as app_logging
from callsentry.config import get_settings
from callsentry.core.db import get_sessionmaker
from callsentry.core.security import hash_password
from callsentry.models import Business, KBDocument, User, UserRole
from callsentry.models.business import DEFAULT_HOURS
from callsentry.services import kb

log = structlog.get_logger(__name__)

DEMO_EMAIL = "demo@callsentry.local"
DEMO_PASSWORD = "changeme"  # noqa: S105 - local demo seed, documented in the README
OPERATOR_EMAIL = "operator@callsentry.local"
VIEWER_EMAIL = "viewer@callsentry.local"  # read-only; the public demo signs in as this

FAQ = """# Northside Dental - Frequently Asked Questions

## Hours
We are open Monday through Friday, 9:00 AM to 5:00 PM. We are closed
Saturdays, Sundays, and public holidays.

## Location
We are at 42 Northside Avenue, Suite 3, on the second floor above the
pharmacy. Street parking is free for two hours, and there is a paid car
park directly behind the building.

## Services
We offer routine check-ups and cleanings, fillings, crowns and bridges,
teeth whitening, and emergency dental care. We do not perform orthodontics
or oral surgery; we refer those cases to Riverside Orthodontics.

## New patients
Yes, we are accepting new patients. Your first visit is a full examination
and cleaning and takes about an hour. Please arrive ten minutes early to
complete your intake forms.

## Insurance
We accept most major dental insurance plans, including Delta Dental,
Cigna, and MetLife. We are not currently in-network with Aetna. We can
process claims directly for in-network plans.

## Cancellations
Please give us at least 24 hours notice to cancel or reschedule. Missed
appointments without notice may be subject to a fee.

## Emergencies
If you have a dental emergency during opening hours, call us and we will
fit you in the same day. Outside of hours, please go to your nearest
emergency room for severe pain, bleeding, or facial swelling.
"""


async def main() -> None:
    settings = get_settings()
    app_logging.configure(settings.log_level)

    async with get_sessionmaker()() as session:
        business = await session.scalar(select(Business).limit(1))
        if business is None:
            business = Business(
                name="Northside Dental",
                timezone="America/New_York",
                business_hours=dict(DEFAULT_HOURS),
                escalation_phone=settings.twilio_phone_number or None,
                twilio_number=settings.twilio_phone_number or None,
                after_hours_message=(
                    "Thanks for calling Northside Dental. We're closed right now, "
                    "but I can take a message or book you in."
                ),
                voice_id="af_heart",
            )
            session.add(business)
            await session.flush()
            log.info("seed.business_created", name=business.name)

        for email, role in (
            (DEMO_EMAIL, UserRole.ADMIN),
            (OPERATOR_EMAIL, UserRole.OPERATOR),
            (VIEWER_EMAIL, UserRole.VIEWER),
        ):
            existing = await session.scalar(select(User).where(User.email == email))
            if existing is None:
                session.add(
                    User(
                        business_id=business.id,
                        email=email,
                        password_hash=hash_password(DEMO_PASSWORD),
                        role=role,
                    )
                )
                log.info("seed.user_created", email=email, role=role)

        has_docs = await session.scalar(
            select(KBDocument).where(KBDocument.business_id == business.id).limit(1)
        )
        if has_docs is None:
            try:
                _, embedded = await kb.index_document(
                    session,
                    business_id=business.id,
                    filename="northside-dental-faq.md",
                    data=FAQ.encode(),
                    content_type="text/markdown",
                )
                log.info("seed.kb_indexed", embedded=embedded)
                if not embedded:
                    log.warning(
                        "seed.kb_not_searchable",
                        hint="run `make models` to pull nomic-embed-text, then re-upload",
                    )
            except Exception as exc:  # noqa: BLE001 - seeding KB is best-effort
                log.warning("seed.kb_failed", error=str(exc))

        await session.commit()

    print(f"\nSeeded. Sign in at http://localhost:3000 as {DEMO_EMAIL} / {DEMO_PASSWORD}")
    print(f"Operator (cross-tenant view): {OPERATOR_EMAIL} / {DEMO_PASSWORD}")
    print(f"Viewer (read-only, public demo): {VIEWER_EMAIL} / {DEMO_PASSWORD}\n")


if __name__ == "__main__":
    asyncio.run(main())

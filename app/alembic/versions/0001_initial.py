"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-07-22
"""

from __future__ import annotations

import pgvector.sqlalchemy
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

EMBEDDING_DIM = 768


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "businesses",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("timezone", sa.String(64), nullable=False, server_default="UTC"),
        sa.Column("business_hours", postgresql.JSONB(), nullable=False),
        sa.Column("escalation_phone", sa.String(32)),
        sa.Column("after_hours_message", sa.Text()),
        sa.Column("greeting_override", sa.Text()),
        sa.Column("cal_com_api_key_enc", sa.Text()),
        sa.Column("cal_com_event_type_id", sa.String(64)),
        sa.Column("twilio_number", sa.String(32)),
        sa.Column("voice_id", sa.String(64), nullable=False, server_default="af_heart"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_businesses"),
    )
    op.create_index("ix_businesses_twilio_number", "businesses", ["twilio_number"], unique=True)

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("business_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.String(16), nullable=False, server_default="admin"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="CASCADE",
                                name="fk_users_business_id_businesses"),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "calls",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("business_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider_call_id", sa.String(64)),
        sa.Column("caller_number", sa.String(32), nullable=False),
        sa.Column("duration_seconds", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("outcome", sa.String(16), nullable=False, server_default="answered"),
        sa.Column("sentiment", sa.String(16)),
        sa.Column("transcript", sa.Text()),
        sa.Column("summary", sa.Text()),
        sa.Column("recording_url", sa.Text()),
        sa.Column("recording_expires_at", sa.DateTime(timezone=True)),
        sa.Column("escalated", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("escalation_reason", sa.Text()),
        sa.Column("cost_usd", sa.Numeric(10, 6), nullable=False, server_default="0"),
        sa.Column("provider_log", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="CASCADE",
                                name="fk_calls_business_id_businesses"),
        sa.PrimaryKeyConstraint("id", name="pk_calls"),
    )
    op.create_index("ix_calls_provider_call_id", "calls", ["provider_call_id"], unique=True)
    op.create_index("ix_calls_business_created", "calls", ["business_id", "created_at"])
    op.create_index("ix_calls_business_outcome", "calls", ["business_id", "outcome"])

    op.create_table(
        "appointments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("business_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("call_id", postgresql.UUID(as_uuid=True)),
        sa.Column("caller_name", sa.String(200), nullable=False),
        sa.Column("caller_phone", sa.String(32), nullable=False),
        sa.Column("caller_email", sa.String(320)),
        sa.Column("reason", sa.Text()),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("timezone", sa.String(64), nullable=False, server_default="UTC"),
        sa.Column("status", sa.String(16), nullable=False, server_default="confirmed"),
        sa.Column("cal_com_event_id", sa.String(128)),
        sa.Column("reminder_sent", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("confirmation_sent", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="CASCADE",
                                name="fk_appointments_business_id_businesses"),
        sa.ForeignKeyConstraint(["call_id"], ["calls.id"], ondelete="SET NULL",
                                name="fk_appointments_call_id_calls"),
        sa.PrimaryKeyConstraint("id", name="pk_appointments"),
    )
    op.create_index("ix_appointments_cal_com_event_id", "appointments",
                    ["cal_com_event_id"], unique=True)
    op.create_index("ix_appointments_business_scheduled", "appointments",
                    ["business_id", "scheduled_at"])

    op.create_table(
        "kb_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("business_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("filename", sa.String(500), nullable=False),
        sa.Column("content_type", sa.String(100), nullable=False, server_default="text/plain"),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("chunk_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="CASCADE",
                                name="fk_kb_documents_business_id_businesses"),
        sa.PrimaryKeyConstraint("id", name="pk_kb_documents"),
    )

    op.create_table(
        "kb_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("business_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("chunk_text", sa.Text(), nullable=False),
        sa.Column("embedding", pgvector.sqlalchemy.Vector(EMBEDDING_DIM)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="CASCADE",
                                name="fk_kb_chunks_business_id_businesses"),
        sa.ForeignKeyConstraint(["document_id"], ["kb_documents.id"], ondelete="CASCADE",
                                name="fk_kb_chunks_document_id_kb_documents"),
        sa.PrimaryKeyConstraint("id", name="pk_kb_chunks"),
    )
    op.create_index("ix_kb_chunks_business", "kb_chunks", ["business_id"])

    op.create_table(
        "cost_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("call_id", postgresql.UUID(as_uuid=True)),
        sa.Column("business_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("category", sa.String(16), nullable=False),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("tier", sa.String(16), nullable=False, server_default="local"),
        sa.Column("units", sa.Numeric(12, 4), nullable=False, server_default="0"),
        sa.Column("unit_name", sa.String(32), nullable=False, server_default="call"),
        sa.Column("cost_usd", sa.Numeric(10, 6), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="CASCADE",
                                name="fk_cost_entries_business_id_businesses"),
        sa.ForeignKeyConstraint(["call_id"], ["calls.id"], ondelete="CASCADE",
                                name="fk_cost_entries_call_id_calls"),
        sa.PrimaryKeyConstraint("id", name="pk_cost_entries"),
    )
    op.create_index("ix_cost_entries_business_created", "cost_entries",
                    ["business_id", "created_at"])


def downgrade() -> None:
    op.drop_table("cost_entries")
    op.drop_table("kb_chunks")
    op.drop_table("kb_documents")
    op.drop_table("appointments")
    op.drop_table("calls")
    op.drop_table("users")
    op.drop_table("businesses")

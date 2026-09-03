from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from pgvector.sqlalchemy import Vector
from sqlalchemy import ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from callsentry.core.db import Base, TimestampMixin, uuid_pk

if TYPE_CHECKING:
    pass

# nomic-embed-text produces 768-dim vectors. Changing the embedding model
# means changing this and reindexing every document - there is no way to
# mix dimensions in one column.
EMBEDDING_DIM = 768


class KBDocument(Base, TimestampMixin):
    __tablename__ = "kb_documents"

    id: Mapped[uuid.UUID] = uuid_pk()
    business_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False
    )
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), default="text/plain", nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    chunks: Mapped[list[KBChunk]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class KBChunk(Base, TimestampMixin):
    __tablename__ = "kb_chunks"
    __table_args__ = (
        Index("ix_kb_chunks_business", "business_id"),
        # IVFFlat needs training data to be useful; for the volumes a single
        # business produces, a plain index on business_id plus a sequential
        # scan over its chunks is faster and needs no reindexing.
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    document_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("kb_documents.id", ondelete="CASCADE"), nullable=False
    )
    business_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False
    )
    chunk_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))

    document: Mapped[KBDocument] = relationship(back_populates="chunks")

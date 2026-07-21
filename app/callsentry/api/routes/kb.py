from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import func, select

from callsentry.agents.kb_agent import answer as kb_answer
from callsentry.api.deps import BusinessDep, SessionDep
from callsentry.models import KBChunk, KBDocument
from callsentry.services import kb

router = APIRouter(prefix="/kb", tags=["knowledge-base"])

MAX_UPLOAD_BYTES = 10 * 1024 * 1024


class DocumentOut(BaseModel):
    id: str
    filename: str
    content_type: str
    chunk_count: int
    indexed: bool
    created_at: datetime


class UploadResult(DocumentOut):
    warning: str | None = None


class TestRequest(BaseModel):
    question: str


class TestResult(BaseModel):
    answered: bool
    answer: str
    confidence: float
    sources: list[str]
    provider: str | None = None
    tier: str | None = None


class ChunkOut(BaseModel):
    id: str
    chunk_index: int
    chunk_text: str
    has_embedding: bool


@router.post("/upload", response_model=UploadResult, status_code=status.HTTP_201_CREATED)
async def upload(
    session: SessionDep,
    business: BusinessDep,
    file: UploadFile = File(...),
) -> UploadResult:
    data = await file.read()
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "file is empty")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"file exceeds {MAX_UPLOAD_BYTES // 1024 // 1024} MB",
        )

    try:
        document, embedded = await kb.index_document(
            session,
            business_id=business.id,
            filename=file.filename or "upload.txt",
            data=data,
            content_type=file.content_type or "",
        )
    except kb.UnsupportedDocument as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    return UploadResult(
        id=str(document.id),
        filename=document.filename,
        content_type=document.content_type,
        chunk_count=document.chunk_count,
        indexed=embedded,
        created_at=document.created_at,
        warning=(
            None
            if embedded
            else "Stored, but no embedding provider was available - this document "
            "will not be searchable until you re-index it."
        ),
    )


@router.get("/documents", response_model=list[DocumentOut])
async def list_documents(session: SessionDep, business: BusinessDep) -> list[DocumentOut]:
    rows = (
        await session.execute(
            select(KBDocument, func.count(KBChunk.id).filter(KBChunk.embedding.isnot(None)))
            .outerjoin(KBChunk, KBChunk.document_id == KBDocument.id)
            .where(KBDocument.business_id == business.id)
            .group_by(KBDocument.id)
            .order_by(KBDocument.created_at.desc())
        )
    ).all()

    return [
        DocumentOut(
            id=str(doc.id),
            filename=doc.filename,
            content_type=doc.content_type,
            chunk_count=doc.chunk_count,
            indexed=embedded_count > 0,
            created_at=doc.created_at,
        )
        for doc, embedded_count in rows
    ]


@router.get("/documents/{document_id}/chunks", response_model=list[ChunkOut])
async def list_chunks(
    document_id: uuid.UUID, session: SessionDep, business: BusinessDep
) -> list[ChunkOut]:
    document = await session.get(KBDocument, document_id)
    if document is None or document.business_id != business.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "document not found")

    rows = (
        await session.scalars(
            select(KBChunk)
            .where(KBChunk.document_id == document_id)
            .order_by(KBChunk.chunk_index)
        )
    ).all()
    return [
        ChunkOut(
            id=str(c.id),
            chunk_index=c.chunk_index,
            chunk_text=c.chunk_text,
            has_embedding=c.embedding is not None,
        )
        for c in rows
    ]


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: uuid.UUID, session: SessionDep, business: BusinessDep
) -> None:
    ok = await kb.delete_document(session, business_id=business.id, document_id=document_id)
    if not ok:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "document not found")


@router.post("/test", response_model=TestResult)
async def test_question(
    payload: TestRequest, session: SessionDep, business: BusinessDep
) -> TestResult:
    """Run a question through the exact path a live caller would hit."""
    result = await kb_answer(
        session,
        business_id=str(business.id),
        business_name=business.name,
        question=payload.question,
    )
    return TestResult(
        answered=result.answered,
        answer=result.text
        or "I don't have that information - a live call would be handed to the team here.",
        confidence=round(result.confidence, 3),
        sources=result.sources,
        provider=result.llm.provider if result.llm else None,
        tier=result.llm.tier if result.llm else None,
    )

"""Embeddings: nomic-embed-text via Ollama (local) -> OpenAI (cloud) -> zero.

The mock tier returns a zero vector. That is intentional and safe: a zero
vector has cosine similarity 0.0 with everything, so it can never clear the
KB confidence threshold, and the agent escalates instead of answering from a
garbage retrieval.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import httpx
import structlog

from callsentry.config import get_settings
from callsentry.core.providers import Attempt, Component, ProviderSpec, get_registry
from callsentry.models.kb import EMBEDDING_DIM

log = structlog.get_logger(__name__)

OPENAI_EMBED_PER_MTOK = 0.02


@dataclass
class EmbeddingResult:
    vectors: list[list[float]]
    provider: str
    tier: str
    tokens: int = 0
    cost_usd: float = 0.0
    degraded: bool = False
    attempts: list[Attempt] = field(default_factory=list)


class EmbeddingService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.registry = get_registry()

    async def _via_ollama(self, texts: list[str]) -> EmbeddingResult:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{self.settings.ollama_base_url}/api/embed",
                json={"model": self.settings.ollama_embed_model, "input": texts},
            )
            resp.raise_for_status()
            data = resp.json()

        vectors = data.get("embeddings") or []
        if vectors and len(vectors[0]) != EMBEDDING_DIM:
            raise ValueError(
                f"embedding model returned {len(vectors[0])} dims, schema expects {EMBEDDING_DIM}"
            )
        return EmbeddingResult(
            vectors=vectors,
            provider="nomic-embed-text",
            tier="local",
            tokens=data.get("prompt_eval_count", 0),
        )

    async def _via_openai(self, texts: list[str]) -> EmbeddingResult:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                "https://api.openai.com/v1/embeddings",
                headers={"Authorization": f"Bearer {self.settings.openai_api_key}"},
                json={
                    "model": "text-embedding-3-small",
                    "input": texts,
                    # Match the column width so cloud and local vectors are
                    # interchangeable in the same table.
                    "dimensions": EMBEDDING_DIM,
                },
            )
            resp.raise_for_status()
            data = resp.json()

        tokens = data.get("usage", {}).get("total_tokens", 0)
        return EmbeddingResult(
            vectors=[item["embedding"] for item in data["data"]],
            provider="openai-embed",
            tier="cloud",
            tokens=tokens,
            cost_usd=round(tokens / 1_000_000 * OPENAI_EMBED_PER_MTOK, 8),
        )

    async def embed(self, texts: list[str]) -> EmbeddingResult:
        if not texts:
            return EmbeddingResult(vectors=[], provider="noop", tier="local")

        attempts: list[Attempt] = []

        async def ollama(_: ProviderSpec) -> EmbeddingResult:
            return await self._via_ollama(texts)

        async def openai(_: ProviderSpec) -> EmbeddingResult:
            return await self._via_openai(texts)

        async def mock(_: ProviderSpec) -> EmbeddingResult:
            log.warning("embeddings.degraded_to_zero", count=len(texts))
            return EmbeddingResult(
                vectors=[[0.0] * EMBEDDING_DIM for _ in texts],
                provider="mock-embed",
                tier="mock",
                degraded=True,
            )

        result, _ = await self.registry.run(
            Component.EMBEDDINGS,
            {"nomic-embed-text": ollama, "openai-embed": openai, "mock-embed": mock},
            attempts=attempts,
        )
        result.attempts = attempts
        return result

    async def embed_one(self, text: str) -> tuple[list[float], EmbeddingResult]:
        result = await self.embed([text])
        vector = result.vectors[0] if result.vectors else [0.0] * EMBEDDING_DIM
        return vector, result


_service: EmbeddingService | None = None


def get_embeddings() -> EmbeddingService:
    global _service
    if _service is None:
        _service = EmbeddingService()
    return _service

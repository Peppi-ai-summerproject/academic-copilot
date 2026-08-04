"""Narrow application boundary for academic-policy retrieval."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from app.services.rag_integration_service import RagIntegrationService


@dataclass(frozen=True)
class PolicyEvidenceCandidate:
    chunk_id: str
    text: str
    score: float
    source: str | None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PolicyContextResult:
    query: str
    candidates: tuple[PolicyEvidenceCandidate, ...] = ()
    error_code: str | None = None

    @property
    def succeeded(self) -> bool:
        return self.error_code is None


@runtime_checkable
class PolicyContextGateway(Protocol):
    async def retrieve_policy(
        self,
        query: str,
        *,
        top_k: int = 3,
    ) -> PolicyContextResult: ...


class RagPolicyContextGateway:
    """Adapt the established ``RagIntegrationService`` for agent use."""

    def __init__(self, service: RagIntegrationService) -> None:
        self._service = service

    async def retrieve_policy(
        self,
        query: str,
        *,
        top_k: int = 3,
    ) -> PolicyContextResult:
        result = await asyncio.to_thread(self._service.execute, query, top_k=top_k)
        if not result.succeeded:
            return PolicyContextResult(query=query, error_code=result.error_code)

        candidates = tuple(
            PolicyEvidenceCandidate(
                chunk_id=chunk.id,
                text=chunk.text,
                score=chunk.score,
                source=_source_from_metadata(chunk.metadata),
                metadata=dict(chunk.metadata),
            )
            for chunk in result.chunks
        )
        return PolicyContextResult(query=query, candidates=candidates)


class UnavailablePolicyContextGateway:
    """Safe default when query-time RAG has not been configured by the caller."""

    async def retrieve_policy(
        self,
        query: str,
        *,
        top_k: int = 3,
    ) -> PolicyContextResult:
        return PolicyContextResult(
            query=query,
            error_code="POLICY_CONTEXT_UNAVAILABLE",
        )


def _source_from_metadata(metadata: dict[str, Any]) -> str | None:
    for key in ("source", "filename", "title"):
        value = metadata.get(key)
        if value:
            return str(value)
    return None

"""Application-layer integration for the query-time RAG pipeline."""

from dataclasses import dataclass, field
import logging
from typing import Any, Protocol

from rag.context.models import InjectedContext
from rag.retriever.models import RetrievedChunk


logger = logging.getLogger(__name__)


class RetrievalServiceContract(Protocol):
    """Minimal retrieval dependency required by the backend integration."""

    def retrieve(
        self,
        query: str,
        top_k: int | None = None,
    ) -> list[RetrievedChunk]: ...


class ContextInjectorContract(Protocol):
    """Minimal context-injection dependency required by the integration."""

    def inject_context(
        self,
        question: str,
        chunks: list[RetrievedChunk],
    ) -> InjectedContext: ...


@dataclass(frozen=True)
class RagSource:
    """Source information exposed without losing the original chunk metadata."""

    chunk_id: str
    score: float
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RagIntegrationResult:
    """Deterministic backend result for one query-time RAG execution."""

    query: str
    injected_context: InjectedContext | None
    chunks: tuple[RetrievedChunk, ...]
    sources: tuple[RagSource, ...]
    retrieved_count: int
    warning: str | None = None
    error_code: str | None = None

    @property
    def succeeded(self) -> bool:
        return self.error_code is None


class RagIntegrationService:
    """Compose existing retrieval and context-injection components.

    This service deliberately knows nothing about Qdrant, embedding providers,
    API routing, chat sessions, agents, or LLM answer generation.
    """

    def __init__(
        self,
        *,
        retrieval_service: RetrievalServiceContract,
        context_injector: ContextInjectorContract,
    ) -> None:
        self._retrieval_service = retrieval_service
        self._context_injector = context_injector

    def execute(
        self,
        query: str,
        *,
        top_k: int | None = None,
    ) -> RagIntegrationResult:
        """Run retrieval followed by context injection.

        Invalid caller input remains a ``ValueError``. Infrastructure and
        context-assembly failures become controlled results so internal error
        details never cross the application boundary.
        """
        normalized_query = self._validate_request(query, top_k)

        try:
            chunks = self._retrieval_service.retrieve(
                normalized_query,
                top_k=top_k,
            )
        except ValueError:
            raise
        except Exception:
            logger.exception("RAG retrieval failed")
            return self._failure(
                normalized_query,
                error_code="RAG_RETRIEVAL_UNAVAILABLE",
            )

        ranked_chunks = tuple(chunks or ())
        sources = tuple(
            RagSource(
                chunk_id=chunk.id,
                score=chunk.score,
                metadata=dict(chunk.metadata),
            )
            for chunk in ranked_chunks
        )

        try:
            injected_context = self._context_injector.inject_context(
                normalized_query,
                list(ranked_chunks),
            )
        except ValueError:
            raise
        except Exception:
            logger.exception("RAG context injection failed")
            return RagIntegrationResult(
                query=normalized_query,
                injected_context=None,
                chunks=ranked_chunks,
                sources=sources,
                retrieved_count=len(ranked_chunks),
                error_code="RAG_CONTEXT_INJECTION_FAILED",
            )

        warning = None
        if not ranked_chunks:
            warning = "No relevant academic context was found."

        return RagIntegrationResult(
            query=normalized_query,
            injected_context=injected_context,
            chunks=ranked_chunks,
            sources=sources,
            retrieved_count=len(ranked_chunks),
            warning=warning,
        )

    @staticmethod
    def _validate_request(query: str, top_k: int | None) -> str:
        if not query or not query.strip():
            raise ValueError("Query must not be empty.")
        if top_k is not None and top_k < 1:
            raise ValueError(f"top_k must be >= 1, got {top_k}.")
        return query.strip()

    @staticmethod
    def _failure(query: str, *, error_code: str) -> RagIntegrationResult:
        return RagIntegrationResult(
            query=query,
            injected_context=None,
            chunks=(),
            sources=(),
            retrieved_count=0,
            error_code=error_code,
        )

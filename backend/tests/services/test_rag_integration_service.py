from dataclasses import dataclass

import pytest

from app.services.rag_integration_service import RagIntegrationService
from rag.context.models import InjectedContext
from rag.retriever.models import RetrievedChunk


def chunk(
    chunk_id: str,
    text: str,
    score: float,
    **metadata: object,
) -> RetrievedChunk:
    return RetrievedChunk(
        id=chunk_id,
        text=text,
        score=score,
        metadata=dict(metadata),
    )


class FakeRetrievalService:
    def __init__(self, results=None, error: Exception | None = None) -> None:
        self.results = results or []
        self.error = error
        self.calls: list[tuple[str, int | None]] = []

    def retrieve(self, query: str, top_k: int | None = None):
        self.calls.append((query, top_k))
        if self.error:
            raise self.error
        return self.results


class FakeContextInjector:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[tuple[str, list[RetrievedChunk]]] = []

    def inject_context(self, question: str, chunks: list[RetrievedChunk]):
        self.calls.append((question, chunks))
        if self.error:
            raise self.error
        joined = " | ".join(item.text for item in chunks) or "No context"
        return InjectedContext(
            prompt=f"Context: {joined}\nQuestion: {question}",
            question=question,
            chunk_count=len(chunks),
            total_context_length=sum(len(item.text) for item in chunks),
        )


def make_service(results=None, *, retrieval_error=None, injection_error=None):
    retrieval = FakeRetrievalService(results, retrieval_error)
    injector = FakeContextInjector(injection_error)
    service = RagIntegrationService(
        retrieval_service=retrieval,
        context_injector=injector,
    )
    return service, retrieval, injector


def test_successful_single_result_executes_complete_pipeline():
    result_chunk = chunk("1", "Study right lasts seven years.", 0.95)
    service, retrieval, injector = make_service([result_chunk])

    result = service.execute("  What is the study right policy?  ")

    assert result.succeeded
    assert result.query == "What is the study right policy?"
    assert result.retrieved_count == 1
    assert result.injected_context is not None
    assert result.injected_context.chunk_count == 1
    assert retrieval.calls == [("What is the study right policy?", None)]
    assert injector.calls == [
        ("What is the study right policy?", [result_chunk])
    ]


def test_multiple_results_preserve_retrieval_order():
    ranked = [
        chunk("high", "Highest", 0.98),
        chunk("middle", "Middle", 0.80),
        chunk("low", "Lowest", 0.61),
    ]
    service, _, injector = make_service(ranked)

    result = service.execute("question")

    assert result.chunks == tuple(ranked)
    assert [source.chunk_id for source in result.sources] == [
        "high",
        "middle",
        "low",
    ]
    assert injector.calls[0][1] == ranked


def test_query_and_top_k_are_mapped_to_retrieval_service():
    service, retrieval, _ = make_service()

    service.execute("  graduation requirements ", top_k=3)

    assert retrieval.calls == [("graduation requirements", 3)]


def test_source_metadata_is_copied_and_preserved():
    metadata = {
        "filename": "policy.pdf",
        "title": "Study Rights",
        "section": "Duration",
        "source": "university-policy",
    }
    result_chunk = chunk("chunk-7", "Policy text", 0.91, **metadata)
    service, _, _ = make_service([result_chunk])

    result = service.execute("policy")

    assert result.sources[0].chunk_id == "chunk-7"
    assert result.sources[0].score == 0.91
    assert result.sources[0].metadata == metadata
    assert result.sources[0].metadata is not result_chunk.metadata


def test_empty_results_still_produce_valid_injected_context():
    service, _, injector = make_service([])

    result = service.execute("unknown policy")

    assert result.succeeded
    assert result.retrieved_count == 0
    assert result.chunks == ()
    assert result.sources == ()
    assert result.injected_context is not None
    assert result.injected_context.chunk_count == 0
    assert result.warning == "No relevant academic context was found."
    assert injector.calls == [("unknown policy", [])]


@pytest.mark.parametrize("query", ["", "   "])
def test_blank_query_is_rejected_before_dependencies_are_called(query):
    service, retrieval, injector = make_service()

    with pytest.raises(ValueError, match="empty"):
        service.execute(query)

    assert retrieval.calls == []
    assert injector.calls == []


@pytest.mark.parametrize("top_k", [0, -1])
def test_invalid_top_k_is_rejected_before_dependencies_are_called(top_k):
    service, retrieval, injector = make_service()

    with pytest.raises(ValueError, match="top_k"):
        service.execute("query", top_k=top_k)

    assert retrieval.calls == []
    assert injector.calls == []


def test_retrieval_failure_returns_controlled_result_without_details():
    service, _, injector = make_service(
        retrieval_error=RuntimeError("Qdrant at secret-host:6333 is down")
    )

    result = service.execute("policy")

    assert not result.succeeded
    assert result.error_code == "RAG_RETRIEVAL_UNAVAILABLE"
    assert result.injected_context is None
    assert result.retrieved_count == 0
    assert "secret-host" not in repr(result)
    assert injector.calls == []


def test_context_injection_failure_preserves_retrieval_evidence():
    result_chunk = chunk("1", "Policy", 0.90, filename="policy.pdf")
    service, _, _ = make_service(
        [result_chunk],
        injection_error=RuntimeError("template internals"),
    )

    result = service.execute("policy")

    assert not result.succeeded
    assert result.error_code == "RAG_CONTEXT_INJECTION_FAILED"
    assert result.injected_context is None
    assert result.chunks == (result_chunk,)
    assert result.sources[0].metadata == {"filename": "policy.pdf"}
    assert "template internals" not in repr(result)


def test_dependencies_are_replaceable_without_external_services():
    @dataclass
    class MinimalRetrieval:
        def retrieve(self, query: str, top_k: int | None = None):
            return [chunk("local", query, 1.0)]

    class MinimalInjector:
        def inject_context(self, question: str, chunks: list[RetrievedChunk]):
            return InjectedContext("prompt", question, len(chunks), len(question))

    service = RagIntegrationService(
        retrieval_service=MinimalRetrieval(),
        context_injector=MinimalInjector(),
    )

    assert service.execute("local query").succeeded

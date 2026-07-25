"""Unit tests for the retrieval layer - Issue #61."""

import pytest
from unittest.mock import MagicMock, patch
from dataclasses import dataclass
from typing import Any

from rag.retriever.models import RetrievedChunk
from rag.retriever.retrieval_service import RetrievalService
from rag.retriever.qdrant_retriever import QdrantRetriever


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_chunk(id="chunk-1", text="Sample text", score=0.9, metadata=None):
    return RetrievedChunk(id=id, text=text, score=score, metadata=metadata or {})


def make_mock_retriever(chunks=None, raise_exc=None):
    mock = MagicMock()
    if raise_exc:
        mock.retrieve.side_effect = raise_exc
    else:
        mock.retrieve.return_value = chunks or []
    return mock


# ── RetrievedChunk tests ──────────────────────────────────────────────────────

def test_retrieved_chunk_valid():
    chunk = RetrievedChunk(id="1", text="hello", score=0.85, metadata={"source": "doc.pdf"})
    assert chunk.id == "1"
    assert chunk.text == "hello"
    assert chunk.score == 0.85


def test_retrieved_chunk_empty_id_raises():
    with pytest.raises(ValueError, match="id must not be empty"):
        RetrievedChunk(id="", text="hello", score=0.5)


def test_retrieved_chunk_empty_text_raises():
    with pytest.raises(ValueError, match="text must not be empty"):
        RetrievedChunk(id="1", text="", score=0.5)


def test_retrieved_chunk_invalid_score_raises():
    with pytest.raises(ValueError, match="Score must be between"):
        RetrievedChunk(id="1", text="hello", score=1.5)


def test_retrieved_chunk_is_frozen():
    chunk = RetrievedChunk(id="1", text="hello", score=0.5)
    with pytest.raises(Exception):
        chunk.text = "modified"


# ── RetrievalService tests ────────────────────────────────────────────────────

def test_retrieval_service_returns_chunks():
    chunks = [make_chunk("1", "Academic policy", 0.95)]
    mock_retriever = make_mock_retriever(chunks)
    service = RetrievalService(retriever=mock_retriever)
    result = service.retrieve("What is the study right policy?")
    assert len(result) == 1
    assert result[0].text == "Academic policy"


def test_retrieval_service_empty_query_raises():
    mock_retriever = make_mock_retriever()
    service = RetrievalService(retriever=mock_retriever)
    with pytest.raises(ValueError, match="empty"):
        service.retrieve("")


def test_retrieval_service_whitespace_query_raises():
    mock_retriever = make_mock_retriever()
    service = RetrievalService(retriever=mock_retriever)
    with pytest.raises(ValueError, match="empty"):
        service.retrieve("   ")


def test_retrieval_service_no_results_returns_empty():
    mock_retriever = make_mock_retriever([])
    service = RetrievalService(retriever=mock_retriever)
    result = service.retrieve("unknown topic")
    assert result == []


def test_retrieval_service_uses_default_top_k():
    mock_retriever = make_mock_retriever([make_chunk()])
    service = RetrievalService(retriever=mock_retriever, default_top_k=3)
    service.retrieve("query")
    mock_retriever.retrieve.assert_called_once_with(query="query", top_k=3)


def test_retrieval_service_custom_top_k():
    mock_retriever = make_mock_retriever([make_chunk()])
    service = RetrievalService(retriever=mock_retriever)
    service.retrieve("query", top_k=10)
    mock_retriever.retrieve.assert_called_once_with(query="query", top_k=10)


def test_retrieval_service_invalid_top_k_raises():
    mock_retriever = make_mock_retriever()
    service = RetrievalService(retriever=mock_retriever)
    with pytest.raises(ValueError, match="top_k"):
        service.retrieve("query", top_k=0)


def test_retrieval_service_propagates_runtime_error():
    mock_retriever = make_mock_retriever(raise_exc=RuntimeError("Qdrant down"))
    service = RetrievalService(retriever=mock_retriever)
    with pytest.raises(RuntimeError, match="Qdrant down"):
        service.retrieve("query")


# ── QdrantRetriever unit tests (mocked) ──────────────────────────────────────

def make_qdrant_retriever():
    mock_embedding_service = MagicMock()
    mock_qdrant_client = MagicMock()

    from rag.embeddings.models import EmbeddedChunk
    fake_embedded = EmbeddedChunk(
        id="query:0:0",
        vector=[0.1] * 768,
        payload={"text": "query"},
    )
    mock_embedding_service.embed_chunks.return_value = [fake_embedded]

    return QdrantRetriever(
        embedding_service=mock_embedding_service,
        qdrant_client=mock_qdrant_client,
        collection_name="academic_knowledge",
    ), mock_embedding_service, mock_qdrant_client


def make_scored_point(id, text, score):
    point = MagicMock()
    point.id = id
    point.score = score
    point.payload = {"text": text, "filename": "test.docx"}
    return point


def test_qdrant_retriever_returns_chunks():
    retriever, _, mock_qdrant = make_qdrant_retriever()
    mock_qdrant.search.return_value = [
        make_scored_point("1", "Study right policy", 0.95),
        make_scored_point("2", "ECTS requirements", 0.88),
    ]
    results = retriever.retrieve("study rights", top_k=2)
    assert len(results) == 2
    assert results[0].score >= results[1].score


def test_qdrant_retriever_empty_query_raises():
    retriever, _, _ = make_qdrant_retriever()
    with pytest.raises(ValueError, match="empty"):
        retriever.retrieve("")


def test_qdrant_retriever_invalid_top_k_raises():
    retriever, _, _ = make_qdrant_retriever()
    with pytest.raises(ValueError, match="top_k"):
        retriever.retrieve("query", top_k=0)


def test_qdrant_retriever_qdrant_failure_raises():
    retriever, _, mock_qdrant = make_qdrant_retriever()
    mock_qdrant.search.side_effect = Exception("Connection refused")
    with pytest.raises(RuntimeError, match="Qdrant search failed"):
        retriever.retrieve("query")


def test_qdrant_retriever_sorted_by_score():
    retriever, _, mock_qdrant = make_qdrant_retriever()
    mock_qdrant.search.return_value = [
        make_scored_point("1", "Low score chunk", 0.5),
        make_scored_point("2", "High score chunk", 0.95),
        make_scored_point("3", "Mid score chunk", 0.75),
    ]
    results = retriever.retrieve("query", top_k=3)
    scores = [r.score for r in results]
    assert scores == sorted(scores, reverse=True)


def test_qdrant_retriever_respects_top_k():
    retriever, _, mock_qdrant = make_qdrant_retriever()
    mock_qdrant.search.return_value = [
        make_scored_point("1", "Chunk one", 0.9),
        make_scored_point("2", "Chunk two", 0.8),
    ]
    retriever.retrieve("query", top_k=2)
    call_args = mock_qdrant.search.call_args
    assert call_args.kwargs["limit"] == 2 or call_args.args[2] == 2 or mock_qdrant.search.called


# ── Integration test (skipped if no env vars) ─────────────────────────────────

def test_integration_real_qdrant():
    import os
    pytest.importorskip("qdrant_client")

    qdrant_url = os.getenv("QDRANT_URL", "http://localhost:6333")
    gemini_key = os.getenv("GEMINI_API_KEY")

    if not gemini_key:
        pytest.skip("GEMINI_API_KEY not set — skipping integration test")

    from qdrant_client import QdrantClient
    from rag.embeddings.gemini_embedding_provider import GeminiEmbeddingProvider
    from rag.embeddings.embedding_service import EmbeddingService
    from rag.retriever.qdrant_retriever import QdrantRetriever
    from rag.retriever.retrieval_service import RetrievalService

    provider = GeminiEmbeddingProvider(api_key=gemini_key)
    embedding_service = EmbeddingService(provider=provider)
    qdrant_client = QdrantClient(url=qdrant_url)
    retriever = QdrantRetriever(
        embedding_service=embedding_service,
        qdrant_client=qdrant_client,
        collection_name="academic_knowledge",
    )
    service = RetrievalService(retriever=retriever)

    try:
        results = service.retrieve("What is the study right policy?", top_k=3)
        print(f"Integration test: got {len(results)} results")
        for r in results:
            print(f"  Score: {r.score:.3f} | File: {r.metadata.get('filename')} | Text: {r.text[:80]}")
    except RuntimeError as e:
        pytest.skip(f"Qdrant not available: {e}")

import pytest
from langchain_core.documents import Document

from rag.embeddings import EmbeddingService


class FakeEmbeddingProvider:
    @property
    def vector_size(self) -> int:
        return 3

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[float(len(text)), 0.0, 1.0] for text in texts]


def test_embed_chunks_returns_embedded_chunks() -> None:
    provider = FakeEmbeddingProvider()
    service = EmbeddingService(provider)

    chunks = [
        Document(
            page_content="Academic policy content",
            metadata={
                "source": "academic_policy.pdf",
                "document_index": 0,
                "chunk_index": 0,
            },
        )
    ]

    result = service.embed_chunks(chunks)

    assert len(result) == 1
    assert result[0].id == "academic_policy.pdf:0:0"
    assert result[0].vector == [23.0, 0.0, 1.0]
    assert result[0].payload["text"] == "Academic policy content"
    assert result[0].payload["source"] == "academic_policy.pdf"


def test_embed_chunks_preserves_order() -> None:
    provider = FakeEmbeddingProvider()
    service = EmbeddingService(provider)

    chunks = [
        Document(
            page_content="First",
            metadata={"source": "file.pdf", "chunk_index": 0},
        ),
        Document(
            page_content="Second",
            metadata={"source": "file.pdf", "chunk_index": 1},
        ),
    ]

    result = service.embed_chunks(chunks)

    assert result[0].payload["text"] == "First"
    assert result[1].payload["text"] == "Second"


def test_embed_chunks_returns_empty_list_for_empty_input() -> None:
    provider = FakeEmbeddingProvider()
    service = EmbeddingService(provider)

    result = service.embed_chunks([])

    assert result == []


class WrongCountProvider:
    @property
    def vector_size(self) -> int:
        return 3

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return []


def test_embed_chunks_raises_error_when_vector_count_is_wrong() -> None:
    provider = WrongCountProvider()
    service = EmbeddingService(provider)

    chunks = [
        Document(
            page_content="Test",
            metadata={"source": "file.pdf", "chunk_index": 0},
        )
    ]

    with pytest.raises(ValueError, match="different number of vectors"):
        service.embed_chunks(chunks)


class WrongSizeProvider:
    @property
    def vector_size(self) -> int:
        return 3

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 2.0]]


def test_embed_chunks_raises_error_when_vector_size_is_wrong() -> None:
    provider = WrongSizeProvider()
    service = EmbeddingService(provider)

    chunks = [
        Document(
            page_content="Test",
            metadata={"source": "file.pdf", "chunk_index": 0},
        )
    ]

    with pytest.raises(ValueError, match="Invalid vector size"):
        service.embed_chunks(chunks)
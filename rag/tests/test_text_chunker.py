"""Tests for the TextChunker component."""

import pytest
from langchain_core.documents import Document

from rag.chunking import TextChunker


def test_split_documents_creates_multiple_chunks() -> None:
    """A long document should be split into multiple chunks."""
    chunker = TextChunker(
        chunk_size=100,
        chunk_overlap=20,
    )

    document = Document(
        page_content=(
            "Academic tutoring supports students throughout their studies. "
            "Tutors monitor academic progress and help students plan courses. "
            "Students at risk should receive early guidance and recommendations. "
            "Regular meetings help identify challenges before they become serious."
        ),
        metadata={
            "source": "academic_policy.pdf",
            "category": "academic_policy",
        },
    )

    chunks = chunker.split_documents([document])

    assert len(chunks) > 1
    assert all(isinstance(chunk, Document) for chunk in chunks)
    assert all(chunk.page_content for chunk in chunks)


def test_split_documents_preserves_original_metadata() -> None:
    """Original document metadata should be copied to every chunk."""
    chunker = TextChunker(
        chunk_size=80,
        chunk_overlap=10,
    )

    document = Document(
        page_content=(
            "Tutoring meetings are organized during the academic year. "
            "Students can discuss progress, challenges, and future study plans."
        ),
        metadata={
            "source": "tutoring_calendar.pdf",
            "document_type": "calendar",
        },
    )

    chunks = chunker.split_documents([document])

    assert len(chunks) > 0

    for chunk in chunks:
        assert chunk.metadata["source"] == "tutoring_calendar.pdf"
        assert chunk.metadata["document_type"] == "calendar"


def test_split_documents_adds_chunk_metadata() -> None:
    """Each chunk should receive document and chunk metadata."""
    chunker = TextChunker(
        chunk_size=80,
        chunk_overlap=10,
    )

    document = Document(
        page_content=(
            "September includes orientation activities and initial tutoring "
            "meetings for new students. October focuses on study planning."
        ),
        metadata={"source": "calendar.pdf"},
    )

    chunks = chunker.split_documents([document])

    for expected_chunk_index, chunk in enumerate(chunks):
        assert chunk.metadata["document_index"] == 0
        assert chunk.metadata["chunk_index"] == expected_chunk_index
        assert chunk.metadata["chunk_size"] == len(chunk.page_content)


def test_split_documents_handles_multiple_documents() -> None:
    """Chunks should contain the correct parent document index."""
    chunker = TextChunker(
        chunk_size=60,
        chunk_overlap=10,
    )

    documents = [
        Document(
            page_content=(
                "First academic policy document containing information "
                "about student tutoring and academic guidance."
            ),
            metadata={"source": "policy.pdf"},
        ),
        Document(
            page_content=(
                "Second tutoring calendar document containing information "
                "about upcoming tutor meetings and activities."
            ),
            metadata={"source": "calendar.pdf"},
        ),
    ]

    chunks = chunker.split_documents(documents)

    document_indexes = {
        chunk.metadata["document_index"]
        for chunk in chunks
    }

    assert document_indexes == {0, 1}


def test_split_documents_returns_empty_list_for_empty_input() -> None:
    """An empty document collection should return an empty list."""
    chunker = TextChunker()

    result = chunker.split_documents([])

    assert result == []


def test_split_documents_rejects_empty_document() -> None:
    """A document without meaningful content should be rejected."""
    chunker = TextChunker()

    document = Document(
        page_content="   ",
        metadata={"source": "empty.pdf"},
    )

    with pytest.raises(
        ValueError,
        match="contains empty content",
    ):
        chunker.split_documents([document])


def test_chunk_size_must_be_positive() -> None:
    """Chunk size must be greater than zero."""
    with pytest.raises(
        ValueError,
        match="chunk_size must be greater than zero",
    ):
        TextChunker(chunk_size=0)


def test_chunk_overlap_cannot_be_negative() -> None:
    """Chunk overlap cannot be negative."""
    with pytest.raises(
        ValueError,
        match="chunk_overlap cannot be negative",
    ):
        TextChunker(
            chunk_size=100,
            chunk_overlap=-1,
        )


def test_chunk_overlap_must_be_smaller_than_chunk_size() -> None:
    """Chunk overlap must always be smaller than chunk size."""
    with pytest.raises(
        ValueError,
        match="chunk_overlap must be smaller than chunk_size",
    ):
        TextChunker(
            chunk_size=100,
            chunk_overlap=100,
        )
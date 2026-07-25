"""Data models for the retrieval layer."""

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class RetrievedChunk:
    """A single chunk retrieved from the vector store.

    Attributes:
        id: Unique identifier of the chunk in Qdrant.
        text: The raw text content of the chunk.
        score: Cosine similarity score (0.0 to 1.0, higher is better).
        metadata: Additional metadata stored alongside the chunk.
    """

    id: str
    text: str
    score: float
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("RetrievedChunk id must not be empty.")
        if not self.text:
            raise ValueError("RetrievedChunk text must not be empty.")
        if not (0.0 <= self.score <= 1.0):
            raise ValueError(f"Score must be between 0.0 and 1.0, got {self.score}.")

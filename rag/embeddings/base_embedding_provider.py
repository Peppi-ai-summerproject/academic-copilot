from typing import Protocol


class EmbeddingProvider(Protocol):
    @property
    def vector_size(self) -> int:
        """Return the dimension of each embedding vector."""
        ...

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Convert a list of texts into embedding vectors."""
        ...
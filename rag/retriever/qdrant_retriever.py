"""Qdrant-backed retriever implementation."""

from qdrant_client import QdrantClient
from qdrant_client.models import ScoredPoint
from qdrant_client import models

from rag.embeddings.embedding_service import EmbeddingService
from rag.retriever.models import RetrievedChunk
from langchain_core.documents import Document


class QdrantRetriever:
    """Retriever that uses Qdrant as the vector store backend.

    Reuses the existing EmbeddingService to embed queries.
    Does NOT call any LLM — only retrieves relevant chunks.

    Args:
        embedding_service: Existing EmbeddingService instance.
        qdrant_client: Connected QdrantClient instance.
        collection_name: Name of the Qdrant collection to search.
    """

    def __init__(
        self,
        embedding_service: EmbeddingService,
        qdrant_client: QdrantClient,
        collection_name: str = "academic_knowledge",
    ) -> None:
        if not collection_name:
            raise ValueError("collection_name must not be empty.")
        self._embedding_service = embedding_service
        self._qdrant = qdrant_client
        self._collection_name = collection_name

    def retrieve(
        self,
        query: str,
        top_k: int = 5,
    ) -> list[RetrievedChunk]:
        """Retrieve top-k most relevant chunks for a natural language query.

        Args:
            query: Natural language query string.
            top_k: Number of results to return (default 5).

        Returns:
            List of RetrievedChunk objects sorted by score descending.

        Raises:
            ValueError: If query is empty or top_k < 1.
            RuntimeError: If Qdrant is unavailable or collection not found.
        """
        if not query or not query.strip():
            raise ValueError("Query must not be empty.")
        if top_k < 1:
            raise ValueError(f"top_k must be at least 1, got {top_k}.")

        # Embed the query using existing EmbeddingService
        query_doc = Document(
            page_content=query.strip(),
            metadata={"source": "query", "document_index": 0, "chunk_index": 0},
        )
        embedded = self._embedding_service.embed_chunks([query_doc])
        if not embedded:
            raise RuntimeError("Embedding service returned no results for query.")

        query_vector = embedded[0].vector

        # Search Qdrant
        try:
            response = self._qdrant.query_points(
                collection_name=self._collection_name,
                query=query_vector,
                limit=top_k,
                with_payload=True,
            )
            results = response.points
        except Exception as exc:
            raise RuntimeError(
                f"Qdrant search failed for collection '{self._collection_name}': {exc}"
            ) from exc

        # Convert to RetrievedChunk objects
        chunks: list[RetrievedChunk] = []
        for point in results:
            payload = point.payload or {}
            text = payload.pop("text", "")
            if not text:
                continue
            chunks.append(
                RetrievedChunk(
                    id=str(point.id),
                    text=text,
                    score=float(point.score),
                    metadata=payload,
                )
            )

        # Sort by score descending (Qdrant usually returns sorted, but enforce)
        chunks.sort(key=lambda c: c.score, reverse=True)
        return chunks

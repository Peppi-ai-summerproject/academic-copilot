"""High-level retrieval service."""

from rag.retriever.base_retriever import Retriever
from rag.retriever.models import RetrievedChunk


class RetrievalService:
    """Higher-level service that orchestrates the retrieval pipeline.

    Responsible for input validation, calling the retriever,
    and returning RetrievedChunk results.

    Does NOT call any LLM. Does NOT generate answers.

    Args:
        retriever: Any object implementing the Retriever protocol.
        default_top_k: Default number of results if not specified.
    """

    def __init__(
        self,
        retriever: Retriever,
        default_top_k: int = 5,
    ) -> None:
        if default_top_k < 1:
            raise ValueError(f"default_top_k must be >= 1, got {default_top_k}.")
        self._retriever = retriever
        self._default_top_k = default_top_k

    def retrieve(
        self,
        query: str,
        top_k: int | None = None,
    ) -> list[RetrievedChunk]:
        """Retrieve relevant chunks for a natural language query.

        Args:
            query: Natural language question or search string.
            top_k: Number of results. Uses default_top_k if not provided.

        Returns:
            List of RetrievedChunk objects sorted by similarity score descending.
            Returns empty list if no results found.

        Raises:
            ValueError: If query is empty or top_k is invalid.
            RuntimeError: If the retrieval backend fails.
        """
        if not query or not query.strip():
            raise ValueError("Query must not be empty.")

        k = top_k if top_k is not None else self._default_top_k
        if k < 1:
            raise ValueError(f"top_k must be >= 1, got {k}.")

        results = self._retriever.retrieve(query=query.strip(), top_k=k)
        return results or []

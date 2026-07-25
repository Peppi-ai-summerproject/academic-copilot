"""Abstract retriever interface."""

from typing import Protocol, runtime_checkable
from rag.retriever.models import RetrievedChunk


@runtime_checkable
class Retriever(Protocol):
    """Protocol defining the retriever interface.

    Any class implementing retrieve() satisfies this protocol.
    """

    def retrieve(
        self,
        query: str,
        top_k: int = 5,
    ) -> list[RetrievedChunk]:
        """Retrieve the most relevant chunks for a query.

        Args:
            query: Natural language query string.
            top_k: Maximum number of results to return.

        Returns:
            List of RetrievedChunk objects sorted by similarity score descending.

        Raises:
            ValueError: If query is empty or top_k is invalid.
            RuntimeError: If the retrieval backend is unavailable.
        """
        ...

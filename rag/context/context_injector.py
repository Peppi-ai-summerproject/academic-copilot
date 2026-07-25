"""Context injector — orchestrates chunk validation and prompt assembly."""

from rag.retriever.models import RetrievedChunk
from rag.context.models import InjectedContext
from rag.context.prompt_builder import PromptBuilder


class ContextInjector:
    """Validates, deduplicates, and injects retrieved chunks into a prompt.

    This is the main entry point for the context injection layer.
    It does NOT perform retrieval and does NOT call the LLM.

    Args:
        prompt_builder: PromptBuilder instance for assembling the final prompt.
        max_chunks: Maximum number of chunks to inject (default 5).
        max_context_length: Maximum total character length of injected context (default 4000).
    """

    def __init__(
        self,
        prompt_builder: PromptBuilder,
        max_chunks: int = 5,
        max_context_length: int = 4000,
    ) -> None:
        if max_chunks < 1:
            raise ValueError(f"max_chunks must be >= 1, got {max_chunks}.")
        if max_context_length < 1:
            raise ValueError(f"max_context_length must be >= 1, got {max_context_length}.")
        self._builder = prompt_builder
        self._max_chunks = max_chunks
        self._max_context_length = max_context_length

    def inject_context(
        self,
        question: str,
        chunks: list[RetrievedChunk],
    ) -> InjectedContext:
        """Validate, clean, and inject retrieved chunks into a prompt.

        Pipeline:
            1. Validate question
            2. Remove empty chunks
            3. Deduplicate chunks by text content
            4. Limit to max_chunks
            5. Enforce max_context_length
            6. Build prompt via PromptBuilder
            7. Return InjectedContext

        Args:
            question: The user's natural language question.
            chunks: List of RetrievedChunk objects from the Retriever,
                    expected to be sorted by score descending.

        Returns:
            InjectedContext with the final prompt and metadata.

        Raises:
            ValueError: If question is empty.
        """
        if not question or not question.strip():
            raise ValueError("Question must not be empty.")

        # Step 1: Remove empty chunks
        valid_chunks = [c for c in chunks if c.text and c.text.strip()]

        # Step 2: Deduplicate by text content (preserve order = preserve ranking)
        seen_texts: set[str] = set()
        deduplicated: list[RetrievedChunk] = []
        for chunk in valid_chunks:
            normalized = chunk.text.strip()
            if normalized not in seen_texts:
                seen_texts.add(normalized)
                deduplicated.append(chunk)

        # Step 3: Limit to max_chunks
        limited = deduplicated[: self._max_chunks]

        # Step 4: Enforce max_context_length
        final_chunks: list[RetrievedChunk] = []
        total_length = 0
        for chunk in limited:
            chunk_len = len(chunk.text.strip())
            if total_length + chunk_len > self._max_context_length:
                break
            final_chunks.append(chunk)
            total_length += chunk_len

        # Step 5: Build prompt
        prompt = self._builder.build_prompt(
            user_question=question.strip(),
            retrieved_chunks=final_chunks,
        )

        return InjectedContext(
            prompt=prompt,
            question=question.strip(),
            chunk_count=len(final_chunks),
            total_context_length=total_length,
        )

"""Prompt builder for constructing LLM-ready prompts from retrieved chunks."""

from rag.retriever.models import RetrievedChunk
from rag.context.templates import (
    ACADEMIC_TUTOR_TEMPLATE,
    CHUNK_SEPARATOR,
    CONTEXT_CHUNK_TEMPLATE,
    CONTEXT_CHUNK_TEMPLATE_NO_METADATA,
)


class PromptBuilder:
    """Constructs a complete LLM prompt from retrieved chunks and a user question."""

    def __init__(self, template=ACADEMIC_TUTOR_TEMPLATE, include_metadata=True, chunk_separator=CHUNK_SEPARATOR):
        if not template:
            raise ValueError("Prompt template must not be empty.")
        self._template = template
        self._include_metadata = include_metadata
        self._chunk_separator = chunk_separator

    def build_prompt(self, user_question: str, retrieved_chunks: list) -> str:
        """Build a complete prompt string from a question and retrieved chunks."""
        if not user_question or not user_question.strip():
            raise ValueError("user_question must not be empty.")
        context_block = self._build_context_block(retrieved_chunks)
        return self._template.format(
            context=context_block,
            question=user_question.strip(),
            separator=self._chunk_separator,
        )

    def _build_context_block(self, chunks: list) -> str:
        """Format retrieved chunks into a readable context block."""
        if not chunks:
            return "No relevant context was found in the knowledge base."
        formatted_chunks = []
        for chunk in chunks:
            if self._include_metadata:
                filename = chunk.metadata.get("filename", "unknown")
                formatted = CONTEXT_CHUNK_TEMPLATE.format(
                    filename=filename,
                    score=chunk.score,
                    text=chunk.text.strip(),
                )
            else:
                formatted = CONTEXT_CHUNK_TEMPLATE_NO_METADATA.format(
                    text=chunk.text.strip(),
                )
            formatted_chunks.append(formatted)
        sep = "\n" + self._chunk_separator + "\n"
        return sep.join(formatted_chunks)

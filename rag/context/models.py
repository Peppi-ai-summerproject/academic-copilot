"""Data models for the context injection layer."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class InjectedContext:
    """The result of context injection — a fully formatted prompt ready for the LLM.

    Attributes:
        prompt: The complete prompt string with context and question injected.
        question: The original user question.
        chunk_count: Number of chunks injected into the prompt.
        total_context_length: Total character length of injected context.
    """

    prompt: str
    question: str
    chunk_count: int
    total_context_length: int

    def __post_init__(self) -> None:
        if not self.prompt:
            raise ValueError("InjectedContext prompt must not be empty.")
        if not self.question:
            raise ValueError("InjectedContext question must not be empty.")
        if self.chunk_count < 0:
            raise ValueError("chunk_count must not be negative.")
        if self.total_context_length < 0:
            raise ValueError("total_context_length must not be negative.")

"""Data models for the retrieval evaluation framework."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class EvaluationQuery:
    """A single evaluation query with metadata.

    Attributes:
        id: Unique query identifier.
        question: Natural language question.
        category: Topic category for grouping results.
        expected_keywords: Keywords expected to appear in retrieved chunks.
    """
    id: str
    question: str
    category: str
    expected_keywords: list[str] = field(default_factory=list)


@dataclass
class EvaluationResult:
    """Result of evaluating a single query against the retriever.

    Attributes:
        query: The original evaluation query.
        retrieved_chunks: Chunks returned by the retriever.
        top_k_hit: Whether any relevant chunk was found in top-k results.
        first_hit_rank: Rank of first relevant chunk (1-based), or None if not found.
        average_similarity: Mean similarity score of retrieved chunks.
        keyword_matches: Number of expected keywords found in retrieved text.
        keyword_match_rate: Fraction of expected keywords found (0.0 to 1.0).
        failure_reasons: List of detected failure reasons.
    """
    query: EvaluationQuery
    retrieved_chunks: list
    top_k_hit: bool
    first_hit_rank: int | None
    average_similarity: float
    keyword_matches: int
    keyword_match_rate: float
    failure_reasons: list[str] = field(default_factory=list)

    @property
    def is_successful(self) -> bool:
        """True if retrieval found at least one relevant chunk."""
        return self.top_k_hit and self.keyword_match_rate > 0.0

    @property
    def retrieved_text(self) -> str:
        """Combined text of all retrieved chunks."""
        return " ".join(c.text for c in self.retrieved_chunks).lower()


@dataclass
class EvaluationReport:
    """Summary report of all evaluation results.

    Attributes:
        total_queries: Total number of queries evaluated.
        successful_retrievals: Number of queries with successful retrieval.
        failed_retrievals: Number of queries with no relevant results.
        top_1_accuracy: Fraction of queries where top result was relevant.
        top_3_accuracy: Fraction of queries where top-3 contained relevant result.
        top_5_accuracy: Fraction of queries where top-5 contained relevant result.
        average_similarity: Mean similarity score across all queries.
        average_keyword_match_rate: Mean keyword match rate across all queries.
        results: All individual EvaluationResult objects.
        failure_analysis: Summary of common failure patterns.
        recommendations: List of improvement recommendations.
    """
    total_queries: int
    successful_retrievals: int
    failed_retrievals: int
    top_1_accuracy: float
    top_3_accuracy: float
    top_5_accuracy: float
    average_similarity: float
    average_keyword_match_rate: float
    results: list[EvaluationResult]
    failure_analysis: dict[str, int] = field(default_factory=dict)
    recommendations: list[str] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        """Overall success rate (0.0 to 1.0)."""
        if self.total_queries == 0:
            return 0.0
        return self.successful_retrievals / self.total_queries

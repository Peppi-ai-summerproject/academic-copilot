"""Source-grounded evaluation for the canonical RAG benchmark dataset.

The historic evaluator measures keyword occurrence in the older 25-query
dataset.  This module evaluates the canonical Issue #64 dataset using its
expected source-document metadata, so it does not infer relevance from a
similarity score or from answer text.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Protocol, Sequence


class RetrievalServiceContract(Protocol):
    """The retrieval boundary required for source-grounded evaluation."""

    def retrieve(self, query: str, top_k: int | None = None) -> Sequence[Any]: ...


@dataclass(frozen=True)
class BenchmarkCase:
    """A validated source-grounded benchmark case."""

    id: str
    category: str
    question_type: str
    difficulty: str
    question: str
    expected_sources: tuple[str, ...]

    @property
    def is_answerable(self) -> bool:
        return self.question_type == "answerable"


@dataclass(frozen=True)
class SourceRetrievalResult:
    """One benchmark retrieval result without making answer-quality claims."""

    case: BenchmarkCase
    retrieved_sources: tuple[str, ...]
    first_expected_rank: int | None
    retrieval_error: str | None = None

    @property
    def hit_at_1(self) -> bool:
        return self.first_expected_rank == 1

    @property
    def hit_at_k(self) -> bool:
        return self.first_expected_rank is not None

    @property
    def unanswerable_without_context(self) -> bool:
        return not self.case.is_answerable and not self.retrieved_sources


@dataclass(frozen=True)
class CategoryMetrics:
    """Source retrieval metrics for an answerable benchmark category."""

    category: str
    cases: int
    hit_at_1: float
    hit_at_k: float


@dataclass(frozen=True)
class SourceBenchmarkReport:
    """Aggregate source-rank evidence for the canonical benchmark."""

    top_k: int
    results: tuple[SourceRetrievalResult, ...]

    @property
    def answerable_results(self) -> tuple[SourceRetrievalResult, ...]:
        return tuple(result for result in self.results if result.case.is_answerable)

    @property
    def unanswerable_results(self) -> tuple[SourceRetrievalResult, ...]:
        return tuple(result for result in self.results if not result.case.is_answerable)

    @property
    def hit_at_1(self) -> float:
        return _ratio(self.answerable_results, lambda result: result.hit_at_1)

    @property
    def hit_at_k(self) -> float:
        return _ratio(self.answerable_results, lambda result: result.hit_at_k)

    @property
    def mean_reciprocal_rank(self) -> float:
        answerable = self.answerable_results
        if not answerable:
            return 0.0
        return sum(
            1 / result.first_expected_rank
            if result.first_expected_rank is not None
            else 0.0
            for result in answerable
        ) / len(answerable)

    @property
    def unanswerable_without_context_rate(self) -> float:
        return _ratio(
            self.unanswerable_results,
            lambda result: result.unanswerable_without_context,
        )

    @property
    def category_metrics(self) -> tuple[CategoryMetrics, ...]:
        grouped: dict[str, list[SourceRetrievalResult]] = defaultdict(list)
        for result in self.answerable_results:
            grouped[result.case.category].append(result)
        return tuple(
            CategoryMetrics(
                category=category,
                cases=len(results),
                hit_at_1=_ratio(results, lambda result: result.hit_at_1),
                hit_at_k=_ratio(results, lambda result: result.hit_at_k),
            )
            for category, results in sorted(grouped.items())
        )


class SourceBenchmarkEvaluator:
    """Evaluate a retriever with expected source filenames from the benchmark."""

    def __init__(self, retrieval_service: RetrievalServiceContract, *, top_k: int = 5) -> None:
        if top_k < 1:
            raise ValueError("top_k must be at least one")
        self._retrieval_service = retrieval_service
        self._top_k = top_k

    def evaluate(self, cases: Sequence[BenchmarkCase]) -> SourceBenchmarkReport:
        results = tuple(self.evaluate_case(case) for case in cases)
        return SourceBenchmarkReport(top_k=self._top_k, results=results)

    def evaluate_case(self, case: BenchmarkCase) -> SourceRetrievalResult:
        try:
            chunks = self._retrieval_service.retrieve(case.question, top_k=self._top_k)
        except Exception as exc:
            return SourceRetrievalResult(
                case=case,
                retrieved_sources=(),
                first_expected_rank=None,
                retrieval_error=type(exc).__name__,
            )

        sources = tuple(_source_name(chunk) for chunk in chunks)
        first_expected_rank = next(
            (
                rank
                for rank, source in enumerate(sources, start=1)
                if source in case.expected_sources
            ),
            None,
        )
        return SourceRetrievalResult(
            case=case,
            retrieved_sources=sources,
            first_expected_rank=first_expected_rank,
        )


def load_canonical_benchmark(path: str | Path) -> tuple[BenchmarkCase, ...]:
    """Load the repository's source-grounded benchmark without changing it."""

    with Path(path).open(encoding="utf-8") as file:
        data = json.load(file)

    raw_cases = data.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise ValueError("Canonical benchmark must contain a non-empty 'cases' list")

    cases: list[BenchmarkCase] = []
    for index, raw_case in enumerate(raw_cases, start=1):
        required = ("id", "category", "question_type", "difficulty", "question", "expected_sources")
        missing = [field for field in required if not raw_case.get(field) and field != "expected_sources"]
        if missing or not isinstance(raw_case.get("expected_sources"), list):
            raise ValueError(f"Invalid benchmark case at index {index}")
        cases.append(
            BenchmarkCase(
                id=str(raw_case["id"]),
                category=str(raw_case["category"]),
                question_type=str(raw_case["question_type"]),
                difficulty=str(raw_case["difficulty"]),
                question=str(raw_case["question"]),
                expected_sources=tuple(str(source) for source in raw_case["expected_sources"]),
            )
        )
    return tuple(cases)


def _source_name(chunk: Any) -> str:
    metadata = getattr(chunk, "metadata", {})
    if not isinstance(metadata, dict):
        return "unknown"
    filename = metadata.get("filename")
    if isinstance(filename, str) and filename:
        return filename
    source = metadata.get("source")
    return Path(str(source)).name if source else "unknown"


def _ratio(
    results: Sequence[SourceRetrievalResult],
    predicate: Any,
) -> float:
    return sum(bool(predicate(result)) for result in results) / len(results) if results else 0.0

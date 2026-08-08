"""Issue #122 tests for canonical source-grounded RAG evaluation."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.rag_integration_service import RagIntegrationService
from rag.evaluation.offline_benchmark import (
    DEFAULT_BENCHMARK_PATH,
    build_offline_benchmark_pipeline,
)
from rag.evaluation.source_benchmark import (
    BenchmarkCase,
    SourceBenchmarkEvaluator,
    load_canonical_benchmark,
)


def chunk(filename: str | None) -> SimpleNamespace:
    metadata = {"filename": filename} if filename else {"source": "C:/sources/policy.docx"}
    return SimpleNamespace(metadata=metadata)


class FakeRetrievalService:
    def __init__(self, responses: dict[str, list[SimpleNamespace] | Exception]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, int | None]] = []

    def retrieve(self, question: str, top_k: int | None = None):
        self.calls.append((question, top_k))
        response = self.responses[question]
        if isinstance(response, Exception):
            raise response
        return response


def case(
    case_id: str,
    *,
    category: str = "Study Rights",
    question_type: str = "answerable",
    sources: tuple[str, ...] = ("Academic_Policy_Document.docx",),
) -> BenchmarkCase:
    return BenchmarkCase(
        id=case_id,
        category=category,
        question_type=question_type,
        difficulty="easy",
        question=f"Question {case_id}",
        expected_sources=sources,
    )


def test_canonical_benchmark_is_loaded_with_source_grounded_cases() -> None:
    cases = load_canonical_benchmark(DEFAULT_BENCHMARK_PATH)

    assert len(cases) == 50
    assert sum(item.is_answerable for item in cases) == 43
    assert {source for item in cases for source in item.expected_sources} == {
        "Academic_Policy_Document.docx",
        "Tutoring_Calendar_2025_2026.docx",
    }


def test_source_metrics_use_expected_source_rank_and_keep_unanswerable_separate() -> None:
    first = case("A")
    second = case("B", category="Academic Calendar")
    unanswerable = case("C", question_type="unanswerable", sources=())
    service = FakeRetrievalService(
        {
            first.question: [chunk("Tutoring_Calendar_2025_2026.docx"), chunk("Academic_Policy_Document.docx")],
            second.question: [chunk("Tutoring_Calendar_2025_2026.docx")],
            unanswerable.question: [],
        }
    )

    report = SourceBenchmarkEvaluator(service, top_k=3).evaluate(
        [first, second, unanswerable]
    )

    assert report.hit_at_1 == 0.0
    assert report.hit_at_k == 0.5
    assert report.mean_reciprocal_rank == 0.25
    assert report.unanswerable_without_context_rate == 1.0
    assert report.results[0].first_expected_rank == 2
    assert report.results[1].first_expected_rank is None
    assert {item.category: item.cases for item in report.category_metrics} == {
        "Academic Calendar": 1,
        "Study Rights": 1,
    }
    assert service.calls == [
        (first.question, 3),
        (second.question, 3),
        (unanswerable.question, 3),
    ]


def test_source_evaluator_records_retrieval_failure_without_claiming_a_hit() -> None:
    failed_case = case("failure")
    service = FakeRetrievalService({failed_case.question: RuntimeError("offline store unavailable")})

    result = SourceBenchmarkEvaluator(service).evaluate_case(failed_case)

    assert result.retrieval_error == "RuntimeError"
    assert result.retrieved_sources == ()
    assert result.first_expected_rank is None


@pytest.fixture(scope="module")
def offline_pipeline():
    return build_offline_benchmark_pipeline()


def test_offline_pipeline_uses_real_documents_chunking_and_in_memory_qdrant(offline_pipeline) -> None:
    assert offline_pipeline.document_count == 2
    assert set(offline_pipeline.source_filenames) == {
        "Academic_Policy_Document.docx",
        "Tutoring_Calendar_2025_2026.docx",
    }
    assert offline_pipeline.chunk_count > offline_pipeline.document_count
    assert len(offline_pipeline.report.results) == 50
    assert len(offline_pipeline.report.answerable_results) == 43
    assert len(offline_pipeline.report.unanswerable_results) == 7
    assert 0.0 <= offline_pipeline.report.hit_at_1 <= offline_pipeline.report.hit_at_k <= 1.0
    assert 0.0 <= offline_pipeline.report.mean_reciprocal_rank <= 1.0


def test_question_retrieval_context_injection_boundary_preserves_question(offline_pipeline) -> None:
    benchmark_case = next(
        item
        for item in load_canonical_benchmark(DEFAULT_BENCHMARK_PATH)
        if item.id == "RAG-001"
    )
    service = RagIntegrationService(
        retrieval_service=offline_pipeline.retrieval_service,
        context_injector=offline_pipeline.context_injector,
    )

    result = service.execute(benchmark_case.question, top_k=5)

    assert result.succeeded
    assert result.query == benchmark_case.question
    assert result.retrieved_count > 0
    assert result.injected_context is not None
    assert result.injected_context.question == benchmark_case.question
    assert benchmark_case.question in result.injected_context.prompt
    assert {source.metadata["filename"] for source in result.sources} <= {
        "Academic_Policy_Document.docx",
        "Tutoring_Calendar_2025_2026.docx",
    }

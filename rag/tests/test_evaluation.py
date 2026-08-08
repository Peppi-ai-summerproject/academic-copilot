"""Unit tests for the retrieval evaluation framework - Issue #63."""

import json
import pytest
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

from rag.evaluation.models import EvaluationQuery, EvaluationResult, EvaluationReport
from rag.evaluation.metrics import RetrievalMetrics
from rag.evaluation.evaluator import RetrievalEvaluator
from rag.evaluation.report_generator import ReportGenerator
from rag.retriever.models import RetrievedChunk


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_query(id="q01", question="What is a study right?", keywords=None):
    return EvaluationQuery(
        id=id, question=question, category="study_rights",
        expected_keywords=keywords or ["study right", "permission", "7 years"]
    )

def make_chunk(text="A study right is permission to study.", score=0.85):
    return RetrievedChunk(id="chunk-1", text=text, score=score, metadata={"filename": "policy.docx"})

def make_retrieval_service(chunks=None, raise_exc=None):
    mock = MagicMock()
    if raise_exc:
        mock.retrieve.side_effect = raise_exc
    else:
        mock.retrieve.return_value = chunks or []
    return mock

def make_report(total=10, successful=8, failed=2):
    results = [
        EvaluationResult(
            query=make_query(id=f"q{i:02d}"),
            retrieved_chunks=[make_chunk()],
            top_k_hit=i < 8,
            first_hit_rank=1 if i < 8 else None,
            average_similarity=0.8,
            keyword_matches=2,
            keyword_match_rate=0.67,
        )
        for i in range(total)
    ]
    return EvaluationReport(
        total_queries=total, successful_retrievals=successful,
        failed_retrievals=failed, top_1_accuracy=0.7,
        top_3_accuracy=0.8, top_5_accuracy=0.85,
        average_similarity=0.8, average_keyword_match_rate=0.67,
        results=results, failure_analysis={"irrelevant_documents": 2},
        recommendations=["Consider increasing chunk overlap."],
    )


# ── EvaluationQuery tests ─────────────────────────────────────────────────────

def test_evaluation_query_valid():
    q = make_query()
    assert q.id == "q01"
    assert q.question == "What is a study right?"
    assert len(q.expected_keywords) > 0

def test_evaluation_result_is_successful():
    result = EvaluationResult(
        query=make_query(), retrieved_chunks=[make_chunk()],
        top_k_hit=True, first_hit_rank=1, average_similarity=0.85,
        keyword_matches=2, keyword_match_rate=0.67,
    )
    assert result.is_successful is True

def test_evaluation_result_not_successful_when_no_hit():
    result = EvaluationResult(
        query=make_query(), retrieved_chunks=[],
        top_k_hit=False, first_hit_rank=None, average_similarity=0.0,
        keyword_matches=0, keyword_match_rate=0.0,
    )
    assert result.is_successful is False


# ── RetrievalMetrics tests ────────────────────────────────────────────────────

def test_metrics_keyword_match():
    metrics = RetrievalMetrics()
    query = make_query(keywords=["study right", "permission"])
    chunks = [make_chunk(text="A study right gives permission to attend courses.")]
    result = metrics.compute(query=query, retrieved_chunks=chunks)
    assert result.keyword_matches == 2
    assert result.keyword_match_rate == 1.0

def test_metrics_no_results():
    metrics = RetrievalMetrics()
    query = make_query()
    result = metrics.compute(query=query, retrieved_chunks=[])
    assert result.top_k_hit is False
    assert result.first_hit_rank is None
    assert result.average_similarity == 0.0
    assert "no_results_returned" in result.failure_reasons

def test_metrics_first_hit_rank():
    metrics = RetrievalMetrics()
    query = make_query(keywords=["study right"])
    chunks = [
        make_chunk(text="Unrelated content about exams.", score=0.9),
        make_chunk(text="A study right lasts 7 years.", score=0.8),
    ]
    result = metrics.compute(query=query, retrieved_chunks=chunks)
    assert result.first_hit_rank == 2

def test_metrics_top_k_hit_true():
    metrics = RetrievalMetrics()
    query = make_query(keywords=["study right"])
    chunks = [make_chunk(text="Study right policy information.", score=0.85)]
    result = metrics.compute(query=query, retrieved_chunks=chunks)
    assert result.top_k_hit is True

def test_metrics_average_similarity():
    metrics = RetrievalMetrics()
    query = make_query(keywords=["study right"])
    chunks = [make_chunk(score=0.9), make_chunk(score=0.7)]
    result = metrics.compute(query=query, retrieved_chunks=chunks)
    assert abs(result.average_similarity - 0.8) < 0.01

def test_metrics_detects_weak_similarity():
    metrics = RetrievalMetrics()
    query = make_query(keywords=["study right"])
    chunks = [make_chunk(text="Unrelated text with no keywords.", score=0.3)]
    result = metrics.compute(query=query, retrieved_chunks=chunks)
    assert "weak_similarity_scores" in result.failure_reasons

def test_metrics_no_keywords_returns_zero_match():
    metrics = RetrievalMetrics()
    query = EvaluationQuery(id="q", question="?", category="test", expected_keywords=[])
    chunks = [make_chunk(text="Some text.")]
    result = metrics.compute(query=query, retrieved_chunks=chunks)
    assert result.keyword_match_rate == 0.0


# ── RetrievalEvaluator tests ──────────────────────────────────────────────────

def test_evaluator_evaluate_query_success():
    service = make_retrieval_service([make_chunk(text="Study right lasts 7 years permission.")])
    evaluator = RetrievalEvaluator(retrieval_service=service, metrics=RetrievalMetrics())
    result = evaluator.evaluate_query("What is a study right?", expected_keywords=["study right", "permission"])
    assert result.top_k_hit is True
    assert result.keyword_matches >= 1

def test_evaluator_evaluate_query_no_results():
    service = make_retrieval_service([])
    evaluator = RetrievalEvaluator(retrieval_service=service, metrics=RetrievalMetrics())
    result = evaluator.evaluate_query("unknown question")
    assert result.top_k_hit is False
    assert result.average_similarity == 0.0

def test_evaluator_handles_retrieval_error():
    service = make_retrieval_service(raise_exc=RuntimeError("Qdrant down"))
    evaluator = RetrievalEvaluator(retrieval_service=service, metrics=RetrievalMetrics())
    result = evaluator.evaluate_query("question?")
    assert result.top_k_hit is False
    assert any("retrieval_error" in r for r in result.failure_reasons)

def test_evaluator_dataset(tmp_path):
    dataset = {
        "queries": [
            {"id": "q01", "question": "Study right?", "category": "study_rights", "expected_keywords": ["study right"]},
            {"id": "q02", "question": "ECTS credits?", "category": "ects", "expected_keywords": ["ECTS"]},
        ]
    }
    dataset_file = tmp_path / "dataset.json"
    dataset_file.write_text(json.dumps(dataset))
    service = make_retrieval_service([make_chunk(text="Study right ECTS credits policy.")])
    evaluator = RetrievalEvaluator(retrieval_service=service, metrics=RetrievalMetrics())
    report = evaluator.evaluate_dataset(str(dataset_file))
    assert report.total_queries == 2

def test_evaluator_report_metrics():
    service = make_retrieval_service([make_chunk(text="Study right is permission to attend.")])
    evaluator = RetrievalEvaluator(retrieval_service=service, metrics=RetrievalMetrics())
    dataset = {"queries": [{"id": "q01", "question": "study right?", "category": "test", "expected_keywords": ["study right"]}]}
    import json, tempfile, os
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(dataset, f)
        path = f.name
    try:
        report = evaluator.evaluate_dataset(path)
        assert report.total_queries == 1
        assert report.top_1_accuracy >= 0.0
    finally:
        os.unlink(path)


# ── ReportGenerator tests ─────────────────────────────────────────────────────

def test_report_generator_markdown(tmp_path):
    gen = ReportGenerator(output_dir=str(tmp_path))
    report = make_report()
    path = gen.generate_markdown(report)
    content = Path(path).read_text(encoding="utf-8")
    assert "RAG Retrieval Accuracy Report" in content
    assert "Top-1 Accuracy" in content
    assert "Recommendations" in content
    assert "✅" in content

def test_report_generator_json(tmp_path):
    gen = ReportGenerator(output_dir=str(tmp_path))
    report = make_report()
    path = gen.generate_json(report)
    with open(path) as f:
        data = json.load(f)
    assert "summary" in data
    assert data["summary"]["total_queries"] == 10
    assert "recommendations" in data
    assert "results" in data

def test_report_generator_creates_output_dir(tmp_path):
    output = tmp_path / "new_dir" / "reports"
    gen = ReportGenerator(output_dir=str(output))
    assert output.exists()

def test_report_success_rate():
    report = make_report(total=10, successful=7, failed=3)
    assert abs(report.success_rate - 0.7) < 0.01


# ── Integration test ──────────────────────────────────────────────────────────

def test_integration_full_evaluation():
    import os
    if os.getenv("RUN_RAG_LIVE_INTEGRATION") != "1":
        pytest.skip("Set RUN_RAG_LIVE_INTEGRATION=1 to run live RAG integration tests.")

    gemini_key = os.getenv("GEMINI_API_KEY")
    if not gemini_key:
        pytest.skip("GEMINI_API_KEY not set")

    try:
        from qdrant_client import QdrantClient
        from rag.embeddings.gemini_embedding_provider import GeminiEmbeddingProvider
        from rag.embeddings.embedding_service import EmbeddingService
        from rag.retriever.qdrant_retriever import QdrantRetriever
        from rag.retriever.retrieval_service import RetrievalService

        provider = GeminiEmbeddingProvider(api_key=gemini_key)
        embedding_service = EmbeddingService(provider=provider)
        qdrant_client = QdrantClient(url="http://localhost:6333")
        retriever = QdrantRetriever(
            embedding_service=embedding_service,
            qdrant_client=qdrant_client,
            collection_name="academic_knowledge",
        )
        retrieval_service = RetrievalService(retriever=retriever)
        metrics = RetrievalMetrics()
        evaluator = RetrievalEvaluator(retrieval_service=retrieval_service, metrics=metrics, top_k=5)

        result = evaluator.evaluate_query(
            question="What is the study right policy?",
            category="study_rights",
            expected_keywords=["study right", "years", "permission"],
        )

        print(f"\nIntegration evaluation:")
        print(f"  Top-k hit: {result.top_k_hit}")
        print(f"  First hit rank: {result.first_hit_rank}")
        print(f"  Similarity: {result.average_similarity:.3f}")
        print(f"  Keyword match: {result.keyword_match_rate:.1%}")

        assert result.average_similarity > 0.0

    except RuntimeError as e:
        pytest.skip(f"Backend not available: {e}")

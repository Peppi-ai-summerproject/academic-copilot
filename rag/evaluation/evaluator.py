"""Main evaluator — orchestrates the full retrieval evaluation pipeline."""

import json
from pathlib import Path

from rag.evaluation.models import EvaluationQuery, EvaluationResult, EvaluationReport
from rag.evaluation.metrics import RetrievalMetrics


class RetrievalEvaluator:
    """Evaluates retrieval accuracy using a predefined evaluation dataset.

    Does NOT call any LLM.
    Does NOT modify the retrieval pipeline.
    Only measures and reports retrieval quality.

    Args:
        retrieval_service: RetrievalService instance for querying.
        metrics: RetrievalMetrics instance for computing metrics.
        top_k: Number of chunks to retrieve per query.
    """

    def __init__(self, retrieval_service, metrics: RetrievalMetrics, top_k: int = 5) -> None:
        if top_k < 1:
            raise ValueError(f"top_k must be >= 1, got {top_k}.")
        self._retrieval_service = retrieval_service
        self._metrics = metrics
        self._top_k = top_k

    def evaluate_query(self, question: str, category: str = "general", expected_keywords: list | None = None) -> EvaluationResult:
        """Evaluate retrieval accuracy for a single question.

        Args:
            question: Natural language question to evaluate.
            category: Topic category for grouping.
            expected_keywords: Keywords expected in retrieved chunks.

        Returns:
            EvaluationResult with all metrics.
        """
        query = EvaluationQuery(
            id="single",
            question=question,
            category=category,
            expected_keywords=expected_keywords or [],
        )
        try:
            chunks = self._retrieval_service.retrieve(question, top_k=self._top_k)
        except Exception as exc:
            return EvaluationResult(
                query=query,
                retrieved_chunks=[],
                top_k_hit=False,
                first_hit_rank=None,
                average_similarity=0.0,
                keyword_matches=0,
                keyword_match_rate=0.0,
                failure_reasons=[f"retrieval_error: {exc}"],
            )
        return self._metrics.compute(query=query, retrieved_chunks=chunks, top_k=self._top_k)

    def evaluate_dataset(self, dataset_path: str) -> EvaluationReport:
        """Run evaluation over the full evaluation dataset.

        Args:
            dataset_path: Path to evaluation_dataset.json.

        Returns:
            EvaluationReport with aggregated metrics and recommendations.
        """
        with open(dataset_path) as f:
            dataset = json.load(f)

        queries = [
            EvaluationQuery(
                id=q["id"],
                question=q["question"],
                category=q["category"],
                expected_keywords=q.get("expected_keywords", []),
            )
            for q in dataset["queries"]
        ]

        results = []
        for query in queries:
            print(f"  Evaluating {query.id}: {query.question[:60]}...")
            try:
                chunks = self._retrieval_service.retrieve(query.question, top_k=self._top_k)
            except Exception as exc:
                chunks = []
            result = self._metrics.compute(query=query, retrieved_chunks=chunks, top_k=self._top_k)
            results.append(result)

        return self._build_report(results)

    def _build_report(self, results: list[EvaluationResult]) -> EvaluationReport:
        """Aggregate individual results into a summary report."""
        total = len(results)
        if total == 0:
            return EvaluationReport(
                total_queries=0, successful_retrievals=0, failed_retrievals=0,
                top_1_accuracy=0.0, top_3_accuracy=0.0, top_5_accuracy=0.0,
                average_similarity=0.0, average_keyword_match_rate=0.0,
                results=[], failure_analysis={}, recommendations=[],
            )

        successful = sum(1 for r in results if r.is_successful)
        failed = total - successful

        top_1 = sum(1 for r in results if r.first_hit_rank == 1) / total
        top_3 = sum(1 for r in results if r.first_hit_rank is not None and r.first_hit_rank <= 3) / total
        top_5 = sum(1 for r in results if r.first_hit_rank is not None and r.first_hit_rank <= 5) / total

        avg_sim = sum(r.average_similarity for r in results) / total
        avg_kw = sum(r.keyword_match_rate for r in results) / total

        failure_analysis: dict[str, int] = {}
        for r in results:
            for reason in r.failure_reasons:
                failure_analysis[reason] = failure_analysis.get(reason, 0) + 1

        recommendations = self._generate_recommendations(
            top_1, top_3, avg_sim, avg_kw, failure_analysis
        )

        return EvaluationReport(
            total_queries=total,
            successful_retrievals=successful,
            failed_retrievals=failed,
            top_1_accuracy=top_1,
            top_3_accuracy=top_3,
            top_5_accuracy=top_5,
            average_similarity=avg_sim,
            average_keyword_match_rate=avg_kw,
            results=results,
            failure_analysis=failure_analysis,
            recommendations=recommendations,
        )

    def _generate_recommendations(self, top_1, top_3, avg_sim, avg_kw, failures) -> list[str]:
        """Generate improvement recommendations based on evaluation results."""
        recs = []
        if top_1 < 0.5:
            recs.append("Top-1 accuracy is low — consider reducing chunk size for more precise matches.")
        if top_3 < 0.7:
            recs.append("Top-3 accuracy needs improvement — increase chunk overlap to preserve context continuity.")
        if avg_sim < 0.6:
            recs.append("Average similarity scores are low — consider retrieving more chunks (increase top_k).")
        if avg_kw < 0.5:
            recs.append("Keyword match rate is low — enrich source documents with more domain-specific content.")
        if failures.get("irrelevant_documents", 0) > 3:
            recs.append("Multiple irrelevant document failures — consider metadata filtering by document type.")
        if failures.get("no_results_returned", 0) > 0:
            recs.append("Some queries returned no results — verify Qdrant collection is populated correctly.")
        if failures.get("weak_similarity_scores", 0) > 3:
            recs.append("Weak similarity scores detected — tune similarity threshold or improve document quality.")
        if failures.get("duplicated_chunks", 0) > 0:
            recs.append("Duplicate chunks found — review chunking strategy to reduce redundancy.")
        if not recs:
            recs.append("Retrieval performance is good. Consider adding more diverse documents to improve coverage.")
        return recs

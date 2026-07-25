"""Evaluation metrics for retrieval accuracy assessment."""

from rag.evaluation.models import EvaluationQuery, EvaluationResult


class RetrievalMetrics:
    """Computes retrieval accuracy metrics for a single query result.

    Does NOT call any LLM or external API.
    Metrics are computed purely from retrieved chunks and expected keywords.
    """

    def compute(
        self,
        query: EvaluationQuery,
        retrieved_chunks: list,
        top_k: int = 5,
    ) -> EvaluationResult:
        """Compute all metrics for a single query evaluation.

        Args:
            query: The evaluation query with expected keywords.
            retrieved_chunks: List of RetrievedChunk objects from the retriever.
            top_k: Number of results considered for top-k accuracy.

        Returns:
            EvaluationResult with all computed metrics.
        """
        if not retrieved_chunks:
            return EvaluationResult(
                query=query,
                retrieved_chunks=[],
                top_k_hit=False,
                first_hit_rank=None,
                average_similarity=0.0,
                keyword_matches=0,
                keyword_match_rate=0.0,
                failure_reasons=["no_results_returned"],
            )

        combined_text = " ".join(c.text for c in retrieved_chunks).lower()

        # Keyword matching
        matched = [kw for kw in query.expected_keywords if kw.lower() in combined_text]
        keyword_matches = len(matched)
        keyword_match_rate = (
            keyword_matches / len(query.expected_keywords)
            if query.expected_keywords else 0.0
        )

        # Top-k hit detection
        top_k_hit = keyword_match_rate > 0.0

        # First hit rank
        first_hit_rank = None
        for rank, chunk in enumerate(retrieved_chunks[:top_k], start=1):
            chunk_text = chunk.text.lower()
            if any(kw.lower() in chunk_text for kw in query.expected_keywords):
                first_hit_rank = rank
                break

        # Average similarity
        scores = [c.score for c in retrieved_chunks if hasattr(c, "score")]
        average_similarity = sum(scores) / len(scores) if scores else 0.0

        # Failure analysis
        failure_reasons = self._detect_failures(
            retrieved_chunks, keyword_match_rate, average_similarity
        )

        return EvaluationResult(
            query=query,
            retrieved_chunks=retrieved_chunks,
            top_k_hit=top_k_hit,
            first_hit_rank=first_hit_rank,
            average_similarity=average_similarity,
            keyword_matches=keyword_matches,
            keyword_match_rate=keyword_match_rate,
            failure_reasons=failure_reasons,
        )

    def _detect_failures(
        self,
        chunks: list,
        keyword_match_rate: float,
        average_similarity: float,
    ) -> list[str]:
        """Detect common failure patterns in retrieval results."""
        failures = []

        if not chunks:
            failures.append("no_results_returned")
            return failures

        if keyword_match_rate == 0.0:
            failures.append("irrelevant_documents")

        if average_similarity < 0.5:
            failures.append("weak_similarity_scores")

        texts = [c.text.strip() for c in chunks if hasattr(c, "text")]
        if len(texts) != len(set(texts)):
            failures.append("duplicated_chunks")

        if keyword_match_rate < 0.3 and average_similarity > 0.7:
            failures.append("poor_ranking")

        return failures

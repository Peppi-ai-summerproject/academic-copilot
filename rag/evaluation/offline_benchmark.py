"""Deterministic, in-memory execution of the canonical RAG benchmark.

This is a QA harness, not a production replacement for Gemini embeddings or a
remote Qdrant deployment.  It deliberately uses a local deterministic token
embedding so that the project-owned loader, chunker, embedding service,
Qdrant retriever, retrieval service, and context injector can be exercised
without credentials or network access.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import re

from qdrant_client import QdrantClient, models
from qdrant_client.models import PointStruct

from rag.chunking.text_chunker import TextChunker
from rag.context.context_injector import ContextInjector
from rag.context.prompt_builder import PromptBuilder
from rag.document_loader import DocumentLoader
from rag.embeddings.embedding_service import EmbeddingService
from rag.evaluation.source_benchmark import (
    SourceBenchmarkEvaluator,
    SourceBenchmarkReport,
    load_canonical_benchmark,
)
from rag.retriever.qdrant_retriever import QdrantRetriever
from rag.retriever.retrieval_service import RetrievalService


PROJECT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_BENCHMARK_PATH = PROJECT_DIR / "rag" / "evaluation" / "datasets" / "rag_test_dataset.json"
DEFAULT_KNOWLEDGE_BASE_PATH = PROJECT_DIR / "docs" / "knowledge_base"
_TOKEN_PATTERN = re.compile(r"[\w]+", re.UNICODE)


class DeterministicTokenEmbeddingProvider:
    """A fixed, local embedding provider used only by the QA harness."""

    vector_size = 128

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self.vector_size
        for token in _TOKEN_PATTERN.findall(text.lower()):
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.vector_size
            vector[index] += 1.0 if digest[4] % 2 else -1.0
        magnitude = sum(value * value for value in vector) ** 0.5
        return [value / magnitude for value in vector] if magnitude else vector


@dataclass(frozen=True)
class OfflineBenchmarkPipeline:
    """Inspectable deterministic pipeline and its benchmark report."""

    document_count: int
    chunk_count: int
    source_filenames: tuple[str, ...]
    retrieval_service: RetrievalService
    context_injector: ContextInjector
    report: SourceBenchmarkReport


def build_offline_benchmark_pipeline(
    *,
    benchmark_path: Path = DEFAULT_BENCHMARK_PATH,
    knowledge_base_path: Path = DEFAULT_KNOWLEDGE_BASE_PATH,
    top_k: int = 5,
) -> OfflineBenchmarkPipeline:
    """Build and evaluate the real local pipeline against the benchmark."""

    documents = DocumentLoader().load_directory(knowledge_base_path)
    chunks = TextChunker().split_documents(documents)
    embedding_service = EmbeddingService(DeterministicTokenEmbeddingProvider())
    embedded_chunks = embedding_service.embed_chunks(chunks)

    client = QdrantClient(location=":memory:")
    collection_name = "issue_122_offline_benchmark"
    client.create_collection(
        collection_name=collection_name,
        vectors_config=models.VectorParams(
            size=DeterministicTokenEmbeddingProvider.vector_size,
            distance=models.Distance.COSINE,
        ),
    )
    client.upsert(
        collection_name=collection_name,
        points=[
            PointStruct(id=index, vector=chunk.vector, payload=chunk.payload)
            for index, chunk in enumerate(embedded_chunks)
        ],
        wait=True,
    )

    retrieval_service = RetrievalService(
        QdrantRetriever(
            embedding_service=embedding_service,
            qdrant_client=client,
            collection_name=collection_name,
        ),
        default_top_k=top_k,
    )
    report = SourceBenchmarkEvaluator(retrieval_service, top_k=top_k).evaluate(
        load_canonical_benchmark(benchmark_path)
    )
    return OfflineBenchmarkPipeline(
        document_count=len(documents),
        chunk_count=len(chunks),
        source_filenames=tuple(document.metadata["filename"] for document in documents),
        retrieval_service=retrieval_service,
        context_injector=ContextInjector(PromptBuilder()),
        report=report,
    )


def main() -> None:
    """Print deterministic source-rank results without writing reports."""

    pipeline = build_offline_benchmark_pipeline()
    report = pipeline.report
    print(f"Documents: {pipeline.document_count}")
    print(f"Chunks: {pipeline.chunk_count}")
    print(f"Answerable cases: {len(report.answerable_results)}")
    print(f"Unanswerable cases: {len(report.unanswerable_results)}")
    print(f"Hit@1: {report.hit_at_1:.1%}")
    print(f"Hit@{report.top_k}: {report.hit_at_k:.1%}")
    print(f"MRR: {report.mean_reciprocal_rank:.3f}")
    print(
        "Unanswerable without context: "
        f"{report.unanswerable_without_context_rate:.1%}"
    )
    print("Category Hit@5:")
    for metric in report.category_metrics:
        print(f"  {metric.category}: {metric.hit_at_k:.1%} ({metric.cases} cases)")
    for result in report.results:
        rank = result.first_expected_rank if result.first_expected_rank is not None else "miss"
        print(f"{result.case.id}: rank={rank}; retrieved={','.join(result.retrieved_sources)}")


if __name__ == "__main__":
    main()

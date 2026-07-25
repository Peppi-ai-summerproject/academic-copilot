"""Run the full retrieval evaluation pipeline."""

import os
import sys
sys.path.insert(0, "/opt/academic-copilot/academic-copilot")

from rag.evaluation.metrics import RetrievalMetrics
from rag.evaluation.evaluator import RetrievalEvaluator
from rag.evaluation.report_generator import ReportGenerator


def main():
    gemini_key = os.getenv("GEMINI_API_KEY")
    if not gemini_key:
        print("ERROR: GEMINI_API_KEY not set.")
        sys.exit(1)

    from qdrant_client import QdrantClient
    from rag.embeddings.gemini_embedding_provider import GeminiEmbeddingProvider
    from rag.embeddings.embedding_service import EmbeddingService
    from rag.retriever.qdrant_retriever import QdrantRetriever
    from rag.retriever.retrieval_service import RetrievalService

    print("Setting up pipeline...")
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
    report_gen = ReportGenerator(output_dir="rag/evaluation/reports")

    dataset_path = "rag/evaluation/evaluation_dataset.json"
    print(f"Running evaluation on {dataset_path}...")
    report = evaluator.evaluate_dataset(dataset_path)

    print("\nGenerating reports...")
    md_path = report_gen.generate_markdown(report)
    json_path = report_gen.generate_json(report)

    print(f"\n{'='*50}")
    print(f"EVALUATION COMPLETE")
    print(f"{'='*50}")
    print(f"Total queries:      {report.total_queries}")
    print(f"Successful:         {report.successful_retrievals}")
    print(f"Failed:             {report.failed_retrievals}")
    print(f"Success rate:       {report.success_rate:.1%}")
    print(f"Top-1 accuracy:     {report.top_1_accuracy:.1%}")
    print(f"Top-3 accuracy:     {report.top_3_accuracy:.1%}")
    print(f"Top-5 accuracy:     {report.top_5_accuracy:.1%}")
    print(f"Avg similarity:     {report.average_similarity:.3f}")
    print(f"Avg keyword match:  {report.average_keyword_match_rate:.1%}")
    print(f"\nReports saved:")
    print(f"  {md_path}")
    print(f"  {json_path}")

    if report.recommendations:
        print(f"\nRecommendations:")
        for i, rec in enumerate(report.recommendations, 1):
            print(f"  {i}. {rec}")


if __name__ == "__main__":
    main()

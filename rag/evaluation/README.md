# RAG Retrieval Evaluation Framework

## Purpose

This module evaluates the quality of the RAG retrieval pipeline for the AI Academic Copilot project.

Evaluation helps identify:
- How accurately the retriever finds relevant academic knowledge
- Which query types fail or return irrelevant results
- Where to improve chunking, embeddings, or source documents

## Structure

```
rag/evaluation/
    __init__.py              # Package exports
    models.py                # EvaluationQuery, EvaluationResult, EvaluationReport
    metrics.py               # RetrievalMetrics — computes keyword match, similarity
    evaluator.py             # RetrievalEvaluator — runs queries and builds reports
    report_generator.py      # ReportGenerator — produces Markdown and JSON reports
    evaluation_dataset.json  # 25 predefined academic evaluation queries
    reports/
        retrieval_report.md  # Generated Markdown report
        retrieval_report.json # Generated JSON summary
```

## How to Run

### Prerequisites
- Qdrant running on localhost:6333
- Documents ingested: `python3 rag/ingest_pipeline.py`
- GEMINI_API_KEY set in environment

### Run full evaluation
```bash
cd /opt/academic-copilot/academic-copilot
source rag_env/bin/activate

GEMINI_API_KEY="your-key" \
PYTHONPATH="/opt/academic-copilot/academic-copilot" \
python3 rag/evaluation/run_evaluation.py
```

### Run unit tests only (no API needed)
```bash
PYTHONPATH="/opt/academic-copilot/academic-copilot" \
python3 -m pytest rag/tests/test_evaluation.py -v
```

## How to Interpret Metrics

| Metric | Good | Needs Work |
|--------|------|------------|
| Success Rate | > 80% | < 60% |
| Top-1 Accuracy | > 60% | < 40% |
| Top-3 Accuracy | > 80% | < 60% |
| Average Similarity | > 0.7 | < 0.5 |
| Keyword Match Rate | > 60% | < 40% |

## Current Limitations

- Keyword matching is a proxy metric — not perfect relevance judgment
- Manual annotation would give more accurate results
- Only 2 source documents currently — more documents = better coverage
- No LLM-based relevance scoring (by design — keeps evaluation cost-free)

## Future Improvements

- Add more tutoring calendar documents and policy files
- Implement human annotation interface for relevance judgments
- Add LLM-based relevance scoring as optional metric
- Track evaluation results over time to measure pipeline improvements
- Add category-level accuracy breakdown

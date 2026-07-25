# RAG Benchmark Dataset — Issue #64

## Purpose

This benchmark dataset provides ground-truth test cases for evaluating the AI Academic Copilot RAG retrieval pipeline.

It enables:
- Retrieval accuracy measurement
- Top-K hit evaluation
- Answer grounding verification
- Regression testing across pipeline changes
- Failure analysis and improvement tracking

## Relationship to Issue #63

This dataset is **directly compatible** with the Issue #63 evaluation framework.
The `EvaluationQuery` model from Issue #63 accepts the `id`, `question`, `category`,
and `expected_keywords` fields from each case in this dataset.

## Dataset Location

```
rag/evaluation/datasets/rag_test_dataset.json
```

## Schema

Each case contains:

| Field | Type | Description |
|-------|------|-------------|
| id | string | Unique identifier e.g. RAG-001 |
| category | string | Topic area |
| question_type | string | "answerable" or "unanswerable" |
| difficulty | string | "easy", "medium", or "hard" |
| question | string | Natural language question |
| expected_answer | string | Correct grounded answer |
| expected_keywords | list | Keywords expected in retrieved chunks |
| expected_sources | list | Source filenames expected to be retrieved |
| expected_relevant_text | string | Short reference passage from source |
| notes | string | Explanation of case design |

## Question Types

- **answerable**: The knowledge base contains enough information to answer correctly
- **unanswerable**: The knowledge base does not contain this information — system should say so

## Difficulty Levels

- **easy**: Direct terminology, one obvious source, nearly exact wording
- **medium**: Paraphrased, multiple chunks needed, moderate semantic matching
- **hard**: Indirect wording, multiple evidence pieces, boundary cases

## Source Documents

All answerable cases are grounded in:
- `Tutoring_Calendar_2025_2026.docx`
- `Academic_Policy_Document.docx`

## Validation

```bash
cd /opt/academic-copilot/academic-copilot
source rag_env/bin/activate
PYTHONPATH="." python3 rag/evaluation/validate_dataset.py
```

## Running Tests

```bash
PYTHONPATH="/opt/academic-copilot/academic-copilot" \
python3 -m pytest rag/tests/test_rag_dataset.py -v
```

## Adding New Cases

1. Add a new entry to `rag_test_dataset.json`
2. Assign a unique ID (e.g. RAG-051)
3. Ground the expected answer in an existing source document
4. Run the validator to confirm the case is valid
5. Run the tests to confirm compatibility

## Current Limitations

- Only 2 source documents currently ingested
- Topics like leave of absence, exam retakes, and programme transfers are not covered
- No LLM-based answer quality scoring (by design — keeps evaluation free)

## Future Extensions

- Add more source documents to expand coverage
- Implement LLM-based answer grounding scoring
- Add multi-hop reasoning test cases
- Track evaluation results over time

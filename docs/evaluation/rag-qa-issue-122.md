# RAG QA Report (Issue #122)

## Scope

Issue #122 audits and evaluates the existing RAG implementation. It does not
rebuild the pipeline, tune production retrieval, change benchmark expectations,
call Gemini, contact a remote Qdrant instance, or make answer-quality claims.

## RAG audit

The current query-time path is:

```text
Knowledge-base documents
  -> DocumentLoader
  -> TextChunker (800 characters, 100-character overlap)
  -> EmbeddingService
  -> Qdrant vector collection
  -> QdrantRetriever
  -> RetrievalService
  -> ContextInjector / PromptBuilder
  -> external answer-generation boundary
```

`RagIntegrationService` composes retrieval and context injection for backend
consumers. It preserves chunk order and source metadata, creates a safe
no-context prompt for an empty result, and does not generate an answer itself.

Existing coverage was already present for chunking, embedding-service mapping,
Qdrant retrieval contracts, context construction, integration-service failure
handling, the earlier keyword evaluator, and benchmark validation. The original
full RAG test run could not collect because this local environment lacked
`qdrant_client` and `langchain_core`; those declared local test dependencies
were installed into the virtual environment only, not committed to the
repository.

## Canonical dataset

The canonical source-grounded benchmark is
`rag/evaluation/datasets/rag_test_dataset.json`, documented by
`rag/evaluation/datasets/README.md` and validated by
`rag.evaluation.validate_dataset`.

It contains 50 cases:

| Dimension | Cases |
| --- | ---: |
| Answerable | 43 |
| Unanswerable | 7 |
| Easy | 17 |
| Medium | 25 |
| Hard | 8 |
| Categories | 13 |

Each case supplies an ID, category, question type, difficulty, question,
grounded expected answer, expected keywords, expected source filenames, and a
reference passage. Answerable cases reference only the two committed source
documents: `Academic_Policy_Document.docx` and
`Tutoring_Calendar_2025_2026.docx`.

The older `rag/evaluation/evaluation_dataset.json` remains configured for the
historic live evaluator. It has 25 keyword-only queries and its stored report
is not comparable to this 50-case source-grounded QA run. It was not altered.

## QA matrix

| RAG stage | Existing coverage | Added Issue #122 evidence | Final status |
| --- | --- | --- | --- |
| Document loading | Production loader and committed DOCX sources existed; no focused loader QA test was present. | Offline pipeline loads both real DOCX files, preserves filenames, and creates chunks. | Covered in deterministic pipeline. |
| Chunking | `rag/tests/test_text_chunker.py` | Real 800/100 chunker produces 24 non-empty indexed chunks from the two documents. | Reused and exercised. |
| Embedding/vector indexing | Embedding-service tests and mocked Qdrant retriever tests. | Real `EmbeddingService` indexes all chunks into local in-memory Qdrant with a deterministic provider. | Covered without Gemini. |
| Retrieval | `rag/tests/test_retriever.py` | Tests corrected to mock production `query_points`; 50 source-rank benchmark queries run through real QdrantRetriever/ RetrievalService. | Covered. |
| Context injection | `rag/tests/test_context_injection.py` and backend integration tests. | A canonical question is retrieved and injected through real ContextInjector/PromptBuilder via RagIntegrationService. | Covered. |
| Question-answer boundary | No LLM answer is part of the production integration service. | Test proves question and ranked evidence reach the prompt boundary. | Context only; generation intentionally untested. |
| Retrieval evaluation | Earlier 25-query keyword evaluator and dataset validator. | New source-rank evaluator supports canonical source expectations, Hit@1, Hit@5, MRR, categories, and separate unanswerable diagnostics. | Covered. |

## Evaluation method

`rag.evaluation.offline_benchmark` is a deterministic QA harness. It keeps the
project-owned `DocumentLoader`, `TextChunker`, `EmbeddingService`,
`QdrantRetriever`, `RetrievalService`, `ContextInjector`, and `PromptBuilder`
real. It replaces only the external Gemini embedding provider with a fixed
token-hash provider and uses `QdrantClient(location=":memory:")`.

This is therefore an offline control evaluation of the current pipeline shape,
not a claim about the quality of production Gemini embeddings or a remote
Qdrant deployment.

For an answerable case, a retrieval is successful when any returned chunk in
the configured top five has `metadata.filename` in the case's
`expected_sources`. The first such chunk position is the source rank. Hit@1,
Hit@5, and MRR use only the 43 answerable cases. Source filenames—not scores,
generated answers, or incidental keyword matches—define success.

For an unanswerable case no source hit is defined. The report separately shows
the rate at which retrieval returned no context. This is a retrieval diagnostic,
not an LLM-answer correctness metric.

## Offline retrieval results

The deterministic command loaded two documents, produced 24 chunks, and ran
all 50 benchmark questions at `top_k=5`.

| Metric | Result |
| --- | ---: |
| Answerable cases | 43 |
| Hit@1 | 74.4% |
| Hit@5 | 95.3% (41/43) |
| MRR | 0.835 |
| Unanswerable without context | 0.0% (0/7) |

| Category (answerable cases only) | Cases | Hit@5 |
| --- | ---: | ---: |
| Academic Calendar | 8 | 100.0% |
| Academic Policies | 4 | 100.0% |
| Course Completion | 2 | 100.0% |
| ECTS and Credit Requirements | 8 | 100.0% |
| Graduation | 3 | 100.0% |
| Registration | 2 | 50.0% |
| Student Services | 3 | 66.7% |
| Study Rights | 8 | 100.0% |
| Tutoring and Student Guidance | 5 | 100.0% |

## Weak cases

The following answerable cases were not ranked first. `Policy` means
`Academic_Policy_Document.docx`; `Calendar` means
`Tutoring_Calendar_2025_2026.docx`.

| Case | Expected source | Offline result | Rank | Evidence-based interpretation |
| --- | --- | --- | ---: | --- |
| RAG-001 | Calendar | Policy ranked first | 2 | Correct source remains in the top five; top-one ordering is weak. |
| RAG-015 | Policy | Calendar ranked first | 2 | Correct source remains in the top five; top-one ordering is weak. |
| RAG-017 | Policy | Calendar ranked first | 2 | Correct source remains in the top five; top-one ordering is weak. |
| RAG-024 | Policy | Calendar ranked first | 2 | Correct source remains in the top five; top-one ordering is weak. |
| RAG-025 | Policy | Calendar ranked first | 2 | Correct source remains in the top five; top-one ordering is weak. |
| RAG-029 | Calendar | Policy ranked ahead | 3 | Correct source is retrieved but lower-ranked. |
| RAG-030 | Calendar | Policy ranked ahead | 4 | Correct source is retrieved but lower-ranked. |
| RAG-031 | Policy | Calendar ranked first | 2 | Correct source remains in the top five; top-one ordering is weak. |
| RAG-037 | Calendar | Policy-only top five | miss | Expected source was absent from top five. Cause is not proven by this offline control run. |
| RAG-039 | Calendar | Policy-only top five | miss | Expected source was absent from top five. Cause is not proven by this offline control run. |
| RAG-050 | Policy | Calendar ranked ahead | 3 | Correct source is retrieved but lower-ranked. |

All seven unanswerable cases (RAG-042 through RAG-048) returned one or more
source chunks. This matches the current retriever contract: it returns the
nearest `top_k` chunks and exposes no relevance threshold or no-evidence
decision. The result identifies a generation-policy and/or retrieval-threshold
question; it does not establish that an answer generator would hallucinate.

## Improvements

### Recommended now

1. Provision an isolated test-only Qdrant snapshot and non-production Gemini
   credentials, then run the same canonical source-rank criteria against the
   real embedding provider. This separates the observed offline-control ranking
   weaknesses from semantic-embedding behavior.
2. Define a product-owned no-evidence policy before an answer generator uses
   nearest-neighbour context for unanswerable questions. The current retriever
   has no threshold, so this requires a separately approved contract change.
3. Add source-diversity and rank monitoring to future evaluations; top-five
   results often contain multiple chunks from the same source document.

### Future work

- Evaluate a metadata filter, hybrid retrieval, reranking, threshold, or
  chunking adjustment only after the isolated real-embedding run establishes a
  reproducible production weakness.
- Expand the knowledge base if the currently unanswerable benchmark topics
  should become answerable. Do not change benchmark expectations to match the
  current two-document corpus.
- Evaluate generated-answer grounding separately with an approved, controlled
  generation test; mocked or deterministic prompts do not prove LLM quality.

No retrieval-algorithm tuning was performed in Issue #122.

## Tests and production fixes

Files added:

- `rag/evaluation/source_benchmark.py` — canonical source-rank evaluator.
- `rag/evaluation/offline_benchmark.py` — deterministic in-memory benchmark
  command using real project-owned pipeline components.
- `rag/tests/test_source_benchmark.py` — benchmark loading, metrics,
  retrieval failure, real-document indexing, and context-boundary coverage.

Files modified:

- `rag/tests/test_retriever.py` — changes stale mocks from `search` to the
  current production `query_points` interface.
- `rag/evaluation/report_generator.py` — writes Markdown/JSON explicitly as
  UTF-8 so the existing checkmark/cross output is portable on Windows.
- `rag/tests/test_evaluation.py` — regression assertion for UTF-8 Markdown
  output and explicit live-evaluation opt-in.
- `rag/tests/test_context_injection.py`, `rag/tests/test_retriever.py`, and
  `rag/tests/test_gemini_embedding_integration.py` — live tests now require
  `RUN_RAG_LIVE_INTEGRATION=1`; default test collection no longer loads
  `backend/.env` or attempts provider/Qdrant access.

The UTF-8 change is the only production-code correction. It was demonstrated by
the existing report-generator test failing with `UnicodeEncodeError` under the
Windows `cp1252` default. No RAG retrieval, chunking, source data, or answer
generation behavior changed.

## Verification

Pre-change baseline:

```powershell
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider rag\tests -q
```

Before the local declared RAG dependencies were available, collection stopped
with six errors from missing `qdrant_client` and `langchain_core`. The baseline
full backend command stopped with eight collection errors from missing
`qdrant_client` and `langgraph`, plus one inherited FastAPI deprecation warning.

Canonical dataset validation:

```powershell
.\.venv\Scripts\python.exe -m rag.evaluation.validate_dataset
```

Result: validation passed, 50 cases, zero errors, zero warnings.

Canonical offline evaluation:

```powershell
$env:DEBUG='false'
.\.venv\Scripts\python.exe -m rag.evaluation.offline_benchmark
```

Result: two documents, 24 chunks, and the metrics reported above. No network,
remote Qdrant, Gemini call, LLM call, or production credentials were used.

Focused and affected deterministic suite:

```powershell
$env:DEBUG='false'
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider `
  --basetemp .issue122-pytest-temp `
  rag\tests backend\tests\services\test_rag_integration_service.py `
  -q -k "not integration"
```

Result: `108 passed, 16 deselected, 1 inherited dependency deprecation warning`.
The `integration` tests were deliberately deselected because they may require
Gemini credentials or a non-local Qdrant deployment; they are not default QA
evidence for this issue.

Complete RAG suite with the live opt-in explicitly disabled:

```powershell
$env:DEBUG='false'
$env:RUN_RAG_LIVE_INTEGRATION='0'
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider `
  --basetemp .issue122-pytest-temp rag\tests -q
```

Result: `108 passed, 4 skipped, 1 warning`. The four skipped tests are the
explicitly gated live Gemini/Qdrant integrations.

Full backend suite:

```powershell
$env:DEBUG='false'
$env:RUN_RAG_LIVE_INTEGRATION='0'
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider `
  --basetemp .issue122-pytest-temp backend\tests -q
```

Result: `894 passed, 24 failed, 2 warnings`. The pre-change run stopped earlier
at eight collection errors because dependencies were absent. With the declared
dependencies present, the failures are visible and remain outside #122:

- one existing agent-collaboration test reaches a CalendarAgent registry
  constructor mismatch;
- 23 existing MCP integration tests expect seven tools and obsolete module-level
  `SessionLocal` attributes, while current production registers nine tools and
  uses newer service boundaries.

No backend test failure is caused by the Issue #122 changes. The stale MCP
suite belongs to the separate MCP-testing scope rather than this RAG QA issue.

## Acceptance criteria

- [x] RAG test dataset used — canonical 50-case benchmark validated and run.
- [x] Retrieval results evaluated — source-rank metrics and category results
  recorded from the deterministic in-memory pipeline.
- [x] Weak retrieval cases identified — rank regressions, two top-five misses,
  and the unanswerable no-context diagnostic are documented.
- [x] Improvements documented — evidence-based recommendations are separated
  from unimplemented future work.

## Deferred scope

- #123: load and performance testing
- #124: security testing
- #125: production-like end-to-end testing

Live remote-Qdrant/Gemini validation also remains intentionally outside this
default deterministic suite until isolated non-production infrastructure is
available.

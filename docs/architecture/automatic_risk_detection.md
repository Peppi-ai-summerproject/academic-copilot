# Automatic Risk Detection (Issue #104)

## Purpose and ownership

Issue #104 is a reusable batch workflow that detects ACTIVE students requiring
tutor attention. It consumes the authoritative Issue #95 risk scorer; it does
not calculate ECTS, delay, study-right, event, or risk-level rules itself.

- Issue #102 owns daily scheduler registration and invokes this workflow.
- Issue #104 owns reusable batch orchestration and the non-identifying result.
- Issue #106 owns risk-alert decisions; #107 owns Telegram delivery.
- Issue #108 owns generic workflow execution logs; its nested execution record
  uses the #102 daily correlation ID when invoked automatically.

No second scheduler, database table, migration, queue, distributed lock, LLM,
RAG, Qdrant call, MCP tool, or Telegram delivery is introduced.

## Student scope and tutor attention

The repository method `StudentRepository.list_active_student_ids()` selects
only rows where `students.status = ACTIVE`, ordered by ID. Explicit IDs are
intersected with the same filter. Inactive, graduated, suspended, archived, and
any other non-ACTIVE students are excluded.

The canonical Issue #95 level names and order are used unchanged:

- `LOW`: no tutor attention.
- `MEDIUM`, `HIGH`, and `CRITICAL`: tutor attention required.

This is an attention policy, not a second risk-level model.

## Partial assessments and canonical scoring

`AcademicRiskScoringService.assess_student_risk()` retains its existing strict
default. Issue #104 opts in with `allow_partial_risk_level=True` because the
tutor-meeting indicator has no authoritative source yet.

For a partial assessment, Issue #95 normalizes the verified subtotal over the
maximum weights of verified indicators, producing a canonical 0â€“100 score and
the existing `LOW` / `MEDIUM` / `HIGH` / `CRITICAL` level. The result keeps:

- `assessment_status = PARTIAL`;
- `score_basis = available_indicator_weights`;
- `available_indicator_maximum`;
- the list of unavailable indicators, including `tutor_meetings`.

Unavailable evidence never counts as zero or safe. A partial result must never
be presented as a complete risk evaluation.

## Direct and agent-facing use

`AutomaticRiskDetectionWorkflow.run(evaluation_time=..., student_ids=...)`
works without FastAPI or a scheduler. The public convenience entry point
`run_database_automatic_risk_detection(...)` creates a short-lived database
session for callers such as AI-agent integrations.

The typed, serializable `RiskDetectionWorkflowResult` contains aggregate counts
and `StudentRiskDetectionResult` objects only for students requiring tutor
attention. Each result has a stable internal student ID, canonical score and
level, contributing indicator codes, non-zero `actionable_indicators`,
unavailable indicator codes, partial or complete status, scoring basis, and
policy version. It does not include names, study records, meeting notes,
Telegram information, or credentials. The actionable list preserves existing
canonical evidence for the deterministic Issue #105 adapter; it does not add a
new risk rule or recommendation policy.

## Status, logging, and limitations

- An empty ACTIVE population is `completed` with zero evaluated and at-risk
  students.
- A partial assessment remains a useful `partial` workflow outcome.
- Per-student unavailable or failed assessments produce a `partial` batch when
  other students were evaluated; all failures produce `failed`.
- At-risk results use deterministic severity order: `CRITICAL`, `HIGH`,
  `MEDIUM`, then internal student ID.

The workflow does not persist detections. Repeated direct execution, restarts,
and multiple application instances can re-evaluate the same student. No
`risk_events` repository, uniqueness key, risk lifecycle, resolution state, or
persistent deduplication contract exists yet.

Logs contain only execution keys, statuses, and aggregate counts.

## Testing

Focused tests use fakes and controlled clocks; they require no real database,
network, Telegram, LLM, Qdrant, or RAG service:

```powershell
$env:DEBUG='false'
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider backend\tests\services\test_academic_risk_scoring_service.py backend\tests\test_student_repository.py backend\tests\workflows\test_automatic_risk_detection.py backend\tests\workflows\test_daily_workflow.py backend\tests\test_scheduler.py
```

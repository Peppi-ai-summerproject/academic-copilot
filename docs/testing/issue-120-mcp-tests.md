# Issue #120: MCP test audit

## Scope and source of truth

The production registry in `backend/app/mcp/registry.py` is the source of truth. It
registers nine tools. The issue text mentions `find_students_at_risk` as an
example, but that tool is not registered and no production behavior was invented
for it.

| Tool | Public inputs | Tested output/error contract |
| --- | --- | --- |
| `ping` | none | health payload and server invocation |
| `get_student` | required integer `student_id` | profile, not found, database error |
| `get_progress` | required integer `student_id` | progress summary, not found, database error |
| `generate_report` | required integer `student_id`; `report_type="academic_summary"` | structured report, report-type forwarding, not found, database error |
| `get_study_right` | required integer `student_id` | study-right record, expiring status, not found, database error |
| `get_curriculum` | required string `programme` | curriculum rows, not found, database error |
| `get_upcoming_events` | optional `start_date`, `end_date` | event rows, invalid date range, database error |
| `search_students` | optional query/programme/group; `limit=20`, `offset=0` | results, empty results, filters, invalid limit, database error |
| `get_student_dashboard` | required integer `student_id` | composed dashboard, not found, database error, response preservation and request-scoped memoization |

The wrappers return structured dictionaries. Successful response details belong
to their services and are preserved by wrapper tests. Failure paths use the
existing structured `success`, `error`, and `message` response convention. Tests
mock repositories/services or sessions, so they do not call external systems or
write persistent data.

## Audit findings and changes

Before changes, the focused MCP suite reported **78 passed, 23 failed**. All 23
failures came from the older integration test module:

- its expected registry omitted `generate_report` and `get_student_dashboard`;
- it patched obsolete module-local `SessionLocal` names after five wrappers had
  moved to lazy imports from `app.db.database`.

The integration tests were aligned with current production wiring. A compact
boundary-contract test was added to assert:

- the exact nine-tool inventory;
- each public tool name is wired to its intended production handler;
- required inputs, field types, optional fields, and defaults;
- JSON-serializable input schemas;
- the unregistered issue example remains absent.

Existing dedicated tests already covered valid calls, empty/not-found results,
database failures, validation failures, session cleanup, and the complex
dashboard composition path. Those tests were retained rather than duplicated.

## Verification

Python 3.11 was used. Dependencies were loaded from temporary directories only;
`python-telegram-bot==22.8`, already pinned by `backend/requirements.txt`, was
temporarily supplied so the complete suite could collect.

Focused MCP suite:

```text
104 passed, 1 warning in 0.83s
```

Complete backend suite:

```text
920 passed, 1 failed, 1 warning in 2.45s
```

The sole full-suite failure is unrelated to MCP changes:
`backend/tests/agents/test_agent_collaboration.py::test_missing_collaborator_accumulates_error_and_preserves_completed_results`.
It attempts to instantiate `CalendarAgent` with an academic gateway, but the
current class initializer accepts no such argument. The warning is the existing
Pydantic `IncompleteFieldDefinitionWarning` emitted while loading FastMCP.

## Acceptance criteria mapping

- Tool discovery/registration: exact inventory and handler-wiring contract tests.
- Valid inputs and structured outputs: dedicated wrapper tests for all nine tools.
- Missing/invalid inputs: FastMCP input-schema assertions plus existing wrapper
  validation tests.
- Empty/not-found cases: covered for student, progress, report, study right,
  curriculum, search, and dashboard; events covers an empty result through the
  integration suite.
- Dependency failures: mocked database/service failures for every data-backed
  wrapper; `ping` has no dependency.
- Isolation and no side effects: mock-backed tests with session cleanup checks.
- Documentation: this inventory, coverage audit, contracts, and exact results.

Deferred scope: adding `find_students_at_risk`, changing production response
schemas, or fixing the unrelated CalendarAgent baseline failure.

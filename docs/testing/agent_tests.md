# Agent Tests (Issue #121)

## Scope and production boundary

This audit covers the current project-owned agent implementation only. It does
not add an agent, alter routing, call external infrastructure, or replace the
existing collaboration suite.

The canonical workflow is `AcademicAgentWorkflow.run(AgentState)`. It uses the
registered route sequence in `state.selected_agents`, moves routes through
`pending_agents` and `completed_agents`, accumulates canonical `AgentResult`
objects in `agent_results`, bounds execution with `max_steps`, and lets only
the communication result provide `final_response`.

## Production agent inventory

| Agent | Implemented | Registered | Existing test evidence | Issue #121 result |
| --- | --- | --- | --- | --- |
| Calendar | `CalendarAgent` | Yes, `calendar` | `test_calendar_agent.py` | Added date/datetime range normalization and context-preservation coverage. |
| Progress Analysis | `ProgressAnalysisAgent` | Yes, `progress` | `test_progress_analysis_agent.py` | Reused: identifier propagation, no-data, status variants, and gateway failure. |
| Study Rights | `StudyRightsAgent` | Yes, `study_rights` | `test_study_rights_agent.py` | Reused: active/risk states, no-data, and gateway failure. |
| Risk Detection | `RiskDetectionAgent` | Yes, `risk` | `test_risk_detection_agent.py` | Reused: structured risk contract, partial evidence, and orchestration scenarios; blocked locally by missing optional dependency. |
| Recommendation | `RecommendationAgent` | Yes, `recommendation` | `test_recommendation_agent.py` | Reused: deterministic policy/template behavior and upstream-result handling; blocked locally by missing optional dependency. |
| Reporting | `ReportingAgent` | Yes, `reporting` | `test_reporting_agent.py` | Reused: provenance, partial/unavailable reports, calendar inclusion, and privacy-safe failures. |
| Communication | `CommunicationAgent` | Yes, `communication` | `test_communication_agent.py` | Reused: advisory-only formatting, partial results, failed-source redaction, and no-delivery boundary. |
| Other production agents | None | N/A | N/A | No additional production agent module or registry entry exists. |

`AcademicAgent` is the protocol for agent implementations. `AgentResult`,
route/status enums, `AgentState`, reducers, the registry, and the LangGraph
workflow are the current shared contracts.

## Gap found and change made

Existing CalendarAgent tests covered ordinary date strings, no events, invalid
student identifiers, and tool failure, but not the documented date-range path
when values are Python `date`/`datetime` objects. The new test proves that the
agent forwards date-only strings and leaves request context unchanged.

It exposed a defect: `datetime` is a subclass of `date`, so the previous type
check forwarded an ISO timestamp instead of a date. `CalendarAgent` now checks
`datetime` before `date`; this is the minimal production correction needed to
honour the existing date-only tool contract. No agent responsibility, routing,
or result schema changed.

## Shared state and collaboration evidence

Existing `test_agent_state.py`, `test_agent_state_reducers.py`, and
`test_agent_types.py` validate initialization, identifiers, independent mutable
defaults, selected/pending/completed routes, result merging, warnings/errors,
status values, and step limits.

`test_academic_agent_workflow.py` uses the real project workflow with
deterministic agents to cover ordered execution, exceptions, unknown routes,
partial/failed terminal states, duplicate route de-duplication, communication
final response handling, and `max_steps` termination.

`test_agent_collaboration.py` is the real six-agent orchestration boundary:

```text
progress -> study_rights -> risk -> recommendation -> reporting -> communication
```

It uses deterministic academic/policy gateways while retaining production
agents, state, and orchestration. It verifies shared request/student/memory
context, downstream result use, preserved upstream results, bounded execution,
and qualified continuation after a missing collaborator.

## Failure matrix

| Failure or boundary | Expected existing behavior | Test evidence |
| --- | --- | --- |
| Invalid Calendar student identifier | Structured `FAILED` result; no tool call | `test_calendar_agent_handles_invalid_student_id` |
| Calendar dependency failure | Structured `FAILED` result with requested dates | `test_calendar_agent_handles_tool_failure` |
| Calendar receives date/datetime range values | Date-only tool arguments; input context retained | `test_calendar_agent_normalizes_date_range_and_preserves_request_context` |
| Progress or study-right data unavailable | Qualified `PARTIAL` result | Their respective `*_unavailable_returns_partial` tests |
| Academic gateway raises | Structured `FAILED` result | Their respective `test_gateway_exception_returns_failed_result` tests |
| Risk/recommendation upstream or policy conditions | Existing canonical partial/failure behavior | `test_risk_detection_agent.py`, `test_recommendation_agent.py` |
| Reporting lacks verified sources | Partial/unavailable report; no fabricated facts | `test_reporting_before_upstream_agents_is_partial_and_does_not_set_final_response`, `test_failed_results_do_not_expose_errors_or_fabricate_report_sections` |
| Failed communication source | Qualified response without internal error disclosure | `test_failed_results_do_not_expose_internal_errors_or_fabricate_an_answer` |
| Agent exception or unknown route | Error is accumulated; workflow reaches defined terminal status | `test_agent_exception_is_recorded_without_crashing_workflow`, `test_unknown_agent_is_handled_safely` |
| Step limit reached | Completed routes retained, remaining routes pending, partial terminal state | `test_max_steps_stops_execution_and_marks_workflow_failed`, `test_max_steps_bounds_collaboration_without_duplicate_execution` |

## Verification

Commands run from the repository root with `DEBUG=false` and pytest cache
disabled:

```powershell
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider `
  backend\tests\agents\test_calendar_agent.py `
  backend\tests\agents\test_communication_agent.py `
  backend\tests\agents\test_progress_analysis_agent.py `
  backend\tests\agents\test_study_rights_agent.py `
  backend\tests\agents\test_reporting_agent.py `
  backend\tests\test_agent_state.py `
  backend\tests\test_agent_state_reducers.py `
  backend\tests\test_agent_types.py -q
```

Result: `110 passed in 0.95s`.

```powershell
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider `
  backend\tests\test_mcp_events_tool.py `
  backend\tests\agents\test_calendar_agent.py -q
```

Result: `8 passed in 0.87s`.

The baseline and post-change complete agent suite both stop during collection
with four pre-existing local dependency errors:

- `qdrant_client` is missing while importing the registry's RAG policy path;
- `langgraph` is missing while importing the real workflow.

Affected modules are `test_academic_agent_workflow.py`,
`test_agent_collaboration.py`, `test_recommendation_agent.py`, and
`test_risk_detection_agent.py`. The full backend baseline similarly stops with
eight collection errors: these four plus four chat/integration modules that
import the same unavailable optional dependencies. These are environment
readiness limitations, not test failures introduced by Issue #121; no optional
packages were installed and no tests were skipped or weakened to conceal them.

## External boundaries and limitations

Default tests use mocks or deterministic fakes for calendar/MCP data, academic
gateway data, policy/RAG context, Telegram delivery, databases, and external
model providers. They do not access Supabase, Qdrant, Telegram, an LLM, or the
network.

The real LangGraph collaboration tests remain valid repository evidence but
cannot execute in this checkout until the declared local `langgraph` and
`qdrant_client` dependencies are installed. This issue intentionally does not
modify dependency management or external-service configuration.

## Deferred scope

- #122: RAG retrieval quality and real vector infrastructure
- #123: load and performance testing
- #124: security testing
- #125: production-like end-to-end journeys

# Copilot end-to-end validation

Issue #209 is validated with in-process Telegram adapters and FastAPI ASGI
transport. No live Telegram or external network is used.

## Results

| Scenario | Result | Boundaries exercised |
|---|---|---|
| General, ambiguous, unsupported, missing student | PASS | Telegram handler, BackendClient, Chat API, ChatService fallback |
| Progress | PASS | Chat API, routing, workflow, ProgressAnalysisAgent, academic gateway double |
| Risk | PASS | Chat API, routing, workflow, RiskDetectionAgent, academic gateway double |
| Recommendation | PASS | Dependency planning, RiskDetectionAgent, RecommendationAgent, policy gateway double |
| Reporting/student summary | PASS | Full ordered dependency plan and ReportingAgent |
| Calendar/events | PASS | CalendarAgent with deterministic academic gateway substitution |
| `/progress`, `/risk`, `/events`, `/student` | PASS | Telegram command, BackendClient, Chat API, routing, real workflow |
| Invalid command | PASS | Telegram validation; backend not contacted |
| Multi-message session/memory | PASS | Stable trusted conversation mapping, ordered history and memory |
| Academic data unavailable | PASS | Partial agent/workflow response without internal leakage |

## Route plans observed

- progress: `progress`
- risk: `risk`
- recommendation: `risk → recommendation`
- reporting/student: `progress → study_rights → risk → recommendation → reporting`
- events: `calendar`

## Infrastructure coverage

Progress, study-right, risk, recommendation, and reporting tests execute the
real agents. External academic-tool operations, including calendar events, are
replaced at the `AcademicToolGateway` boundary with deterministic data.

Recommendation exercises the real policy-context gateway contract with a
deterministic double. It does **not** exercise a live RAG retriever, embedding
provider, or vector database. No tested production path invokes an LLM.

## Limitations and assumptions

- Normal Telegram text does not structurally carry `student_id`; student-scoped
  text therefore requests the identifier. Academic commands and Chat API calls
  provide it explicitly.
- Tests do not claim live Telegram delivery, live MCP transport, PostgreSQL,
  production RAG, or production academic data coverage.
- Backend transport is real HTTP semantics over in-process ASGI transport.
- `DEBUG=false` is applied only to the test process because the local machine
  environment otherwise contains an invalid boolean setting.

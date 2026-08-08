# Issue #125: End-to-end testing report

## Audit and test boundary

The audit traced the current production path through Telegram webhook parsing,
`handle_message`, `BackendClient`, FastAPI chat routing, `ChatService`, LangGraph
workflow creation, production agents, academic/MCP and RAG gateways, repositories,
Monday/risk workflows, notification rendering, and workflow logging. Existing
integration, MCP, agent, RAG and workflow tests were classified before adding
coverage.

Existing `test_end_to_end_academic_workflow.py` is E2E-like at the application
boundary: it executes real `ChatService`, LangGraph orchestration and production
agents, but starts with `ChatRequest` and replaces the academic gateway. Existing
system-boundary tests independently prove Telegram parsing and agent → MCP tool →
service → repository wiring. Monday and weekly briefing tests prove workflow
generation. None previously crossed the actual Telegram handler and backend HTTP
client in one journey.

The Issue #125 tests therefore add that missing supported boundary without
duplicating lower-level analytics assertions.

## Important runtime gap

The current Telegram journey cannot initiate an agent workflow:

1. `handle_message` passes message, Telegram user/chat ID and username to
   `BackendClient`.
2. `BackendClient` posts only those fields to `/api/v1/chat/messages`.
3. `ChatRequest.selected_agents` defaults to an empty list and `student_id`
   defaults to `None`.
4. `ChatService` executes LangGraph only when `selected_agents` is non-empty.
5. No production intent classifier/router converts natural-language Telegram
   text into `student_id` and selected agent routes.

Consequently, a real Telegram request currently receives the non-workflow
“Backend received your message” response. There is no truthful production chain
for Telegram → agent → MCP, student-summary, at-risk-students, or risk-details
demo requests. Tests do not fabricate that missing product behavior.

## Environment and substitutions

- Local CPython 3.11 deterministic tests; no deployed server.
- Synthetic Telegram updates and identities only.
- Production Telegram webhook parser, handler, BackendClient, FastAPI route,
  `ChatService`, `SessionService`, and response behavior are real.
- Backend HTTP network is replaced narrowly with HTTPX ASGI transport.
- Telegram HTTP network is replaced with a capturing bot object.
- No production database/Supabase, Qdrant, LLM, embeddings, credentials, or
  external network is used.

| External boundary | Replacement | Reason |
| --- | --- | --- |
| Telegram network | capturing async bot transport | prevent real sends/token use |
| Backend network socket | HTTPX ASGI transport | run real FastAPI route locally |
| Production database | not reached by supported no-agent path | deterministic safety |
| LLM | not reached | no supported Telegram agent route |
| Qdrant/embeddings | not reached | no supported Telegram RAG route |

## New E2E scenarios

| Scenario | Input/trigger | Expected outcome | Actual outcome | Result |
| --- | --- | --- | --- | --- |
| Supported Telegram chat | signed synthetic webhook message | parse update, call backend route, create session, capture one response | exact production path executed; typing action and one tutor-facing response captured | PASS |
| Sequential-user isolation | two signed updates from distinct synthetic users/chats | replies and sessions remain isolated | each chat received only its own request text; distinct sessions retained correct chat IDs | PASS |
| Backend unavailable | signed update with backend transport failure | safe tutor response, no crash/internal detail | webhook completed and one generic connectivity message was captured | PASS |

Actual successful trace:

```text
FastAPI Telegram webhook
→ python-telegram-bot Update.de_json
→ ProcessingTelegramApplication.process_update (external dispatcher replacement)
→ production handle_message
→ production BackendClient
→ HTTPX ASGI transport (network replacement)
→ production FastAPI chat route
→ production ChatService / SessionService
→ production non-workflow response
→ Message.reply_text
→ captured Telegram bot transport
```

## Requested demo scenarios

### Tutor requests student summary — BLOCKED

Backend-level explicit `ChatRequest(selected_agents=["progress"], student_id=…)`
is validated by existing E2E-like tests and real production agents. The Telegram
client cannot create those fields from text, so the complete user journey stops
at the generic non-workflow response.

### Tutor asks which students are at risk — BLOCKED

There is no registered MCP `find_students_at_risk` tool and no Telegram intent
route for a cohort-risk query. Automatic risk detection exists as a separate
system workflow, but presenting it as a conversational Telegram feature would
invent behavior.

### System sends Monday briefing — PARTIAL/BLOCKED

Existing deterministic tests prove `MondayWorkflow` gathers tutors, progress,
risk and events and produces Telegram-ready delivery metadata/text. The current
Monday workflow labels delivery as not sent and does not cross a configured
Telegram sender, so generation passes but the “system sends” end-to-end outcome
is blocked.

### Tutor requests risk details — BLOCKED

Risk and recommendation agents, policy-context gateway and RAG integration are
covered below the E2E boundary. Telegram has no intent/student extraction bridge,
so a natural-language request does not initiate that chain.

### Failure scenario — PASS

The new transport-failure E2E test proves the signed update still produces one
safe tutor-facing connectivity response without leaking the internal exception.

## Component coverage matrix

`Real` means executed in that scenario; `separate` means evidenced by existing
lower-level tests but not claimed as part of the E2E scenario.

| Scenario | Telegram | Backend | Agents | MCP | DB | RAG | Workflow | Result |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Supported chat | Real | Real | No | No | No | No | non-agent ChatService path | PASS |
| Explicit student analysis (existing) | context only | Real | Real | gateway fake | fake | optional gateway fake | Real LangGraph | E2E-like PASS |
| Agent/MCP boundary (existing) | No | No | Real | Real | session fake, repository real | No | agent call | integration PASS |
| Monday briefing (existing) | rendered, not sent | workflow | No | providers fake | fake | No | Real | PARTIAL |
| RAG/backend (existing) | No | service | recommendation/policy tests | No | No | real integration with fakes | No | integration PASS |
| Full requested Telegram agent journey | input only | Real | not reached | not reached | not reached | not reached | not reached | BLOCKED |

No scenario is marked as covering a component merely because another test proves
that component independently.

## Baseline and verification

Pre-change full backend baseline:

```text
927 passed, 1 failed, 1 warning in 2.56s
```

The sole baseline failure is the known CalendarAgent constructor mismatch in
`test_missing_collaborator_accumulates_error_and_preserves_completed_results`.
The warning is the existing FastMCP/Pydantic incomplete field warning.

Existing E2E-like/system/workflow evidence:

```text
27 passed in 0.97s
```

Focused Issue #125 E2E suite:

```text
3 passed in 1.01s
```

Post-change related and full-suite results are added after final verification.

Related Telegram, integration, agent, MCP, RAG and workflow suites:

```text
268 passed, 1 failed, 1 warning in 2.17s
```

Post-change full backend regression:

```text
930 passed, 1 failed, 1 warning in 2.22s
```

The three new E2E tests account for the pass-count increase. Both verification
runs contain only the identical pre-existing CalendarAgent failure and existing
warning; Issue #125 introduced no new functional regression.

## Epic QA readiness summary

| QA area | Issue | Evidence present on current main | Status |
| --- | ---: | --- | --- |
| Unit | #118 | `docs/testing/issue-118-unit-tests.md` and unit suites | Present |
| Integration | #119 | `docs/testing/integration_tests.md` and integration suite | Present |
| MCP | #120 | MCP audit/report and 104-test evidence | Present |
| Agents | #121 | `agent_tests.md`, collaboration evidence and agent suites | Present; known CalendarAgent baseline failure remains |
| RAG | #122 | `docs/evaluation/rag-qa-issue-122.md` and RAG tests | Present |
| Load | #123 | safe runner and measured QA report | Present |
| Security | #124 | focused tests and redacted findings report | Present; high access-control risks documented |
| E2E | #125 | actual supported Telegram boundary tests and this report | Partial; required agent demo journeys blocked |

Evidence presence is not the same as production readiness. In particular, #124
documents unresolved high-severity access-control gaps, and #125 demonstrates the
missing Telegram-to-agent routing bridge.

## Changes

- Added `backend/tests/e2e/test_telegram_chat_journey.py` and package marker.
- Registered the `e2e` pytest marker in `pytest.ini`.
- Added this report.
- No production file changed.

## Acceptance criteria

- [ ] Full workflows tested — supported Telegram chat and failure journeys pass,
  but requested agent workflows cannot start from Telegram.
- [ ] Telegram-to-agent-to-tool flow works — BLOCKED by missing production
  intent/student/agent selection bridge.
- [ ] Demo scenarios validated — audited with one partial and three blocked;
  results were not fabricated.
- [x] End-to-end results documented — scenarios, traces, substitutions, evidence,
  gaps and limitations are recorded here.

## Recommended follow-ups

1. Define and implement an authenticated Telegram intent/entity-routing contract
   that produces validated `student_id` and allowed `selected_agents`.
2. Add a supported cohort at-risk query/service contract if required by product.
3. Connect Monday briefing generation to the approved Telegram delivery boundary
   with recipient authorization, idempotency and delivery logging.
4. After those product features exist, extend this suite to Telegram → LangGraph
   → MCP/RAG → captured Telegram and make the blocked scenarios pass.

## Limitations

These tests validate local assembled application behavior only. They do not prove
deployed Telegram connectivity, production database/Qdrant/LLM behavior, network
security, capacity, or real user-data correctness. The missing routing features
prevent completion of the issue's central end-to-end acceptance criterion.

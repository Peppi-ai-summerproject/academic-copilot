# Backend Integration Tests (Issue #119)

## Purpose and boundary

Issue #119 verifies communication between meaningful backend components. It
does not replace unit tests (#118), exhaustive MCP/agent/RAG suites (#120–#122),
load/security testing (#123–#124), or full user journeys (#125).

The default tests are deterministic and local. They never use production
credentials, mutate Supabase, send a Telegram message, call an LLM, create an
embedding, or contact Qdrant.

## Audit and integration matrix

| Connection | Existing | Added in #119 | Evidence |
| --- | --- | --- | --- |
| API → service | `test_progress_dashboard_api.py` exercises route response mapping with a dependency override. | FastAPI health route → real dependency resolution → `HealthService`. | `test_database_health_route_uses_real_dependency_service_and_sqlalchemy_session` |
| API/service → database | Repository tests use mocked SQLAlchemy sessions. | The health route uses a real local SQLite SQLAlchemy session. | Same API/database test |
| Backend → Supabase | No Supabase SDK, adapter, or safe test project exists; the backend uses generic SQLAlchemy repositories configured by `DATABASE_URL`. | None; no live Supabase test is claimed. | Local SQLite verifies the database abstraction only. |
| Backend → Telegram | Notification-delivery tests cover alert rendering, recipient resolution, and a fake provider; backend-client tests mock HTTP. | Production webhook route → `telegram.Update` parsing → application dispatch. | `test_telegram_webhook_parses_update_and_invokes_application_without_network` |
| Backend → RAG | `test_rag_integration_service.py` composes real `RagIntegrationService` with deterministic retrieval/context fakes. | None; existing coverage already tests the integration boundary. | `RagIntegrationService.execute` tests |
| Backend → MCP | `test_mcp_server.py`, `test_mcp_registry.py`, and `test_mcp_integration.py` cover server/registry/tool contracts. | None; representative agent path below adds cross-layer evidence. | Existing MCP tests plus agent test |
| Agent → tool | `test_progress_analysis_agent.py` uses a fake gateway. | Real `MCPAcademicToolGateway` → real MCP functions → real service/repository classes. | `test_progress_agent_uses_concrete_mcp_gateway_tools_services_and_repository` |
| Workflow → components | Daily, weekly, alert, briefing, and execution-log workflow suites already exercise orchestration with deterministic fakes. | None; no parallel workflow architecture was added. | `backend/tests/workflows/` |

## Tests added

`backend/tests/integration/test_system_boundaries.py` covers three focused
boundaries in four tests:

1. API route → dependency injection → `HealthService` → real local SQLAlchemy
   connection. The database is an in-memory SQLite engine created for the test
   and disposed afterwards.
2. Telegram webhook HTTP route → secret validation → real `telegram.Update`
   deserialization → application `process_update`, plus the invalid-secret
   rejection path. The Telegram application is a local fake; no Telegram
   network client is initialized.
3. `ProgressAnalysisAgent` → `MCPAcademicToolGateway` → actual MCP tool
   functions → `StudentService`/`ProgressService` → repository interfaces. The
   database session factory is replaced only at the database boundary with a
   deterministic query-aware fake, and every opened session is verified closed.

No production code was changed for Issue #119.

## External boundaries

### Tested locally and deterministic

- FastAPI routing and dependency injection
- SQLAlchemy against local, in-memory SQLite for a connection-health query
- Telegram update parsing and application dispatch
- Agent, MCP gateway, MCP tool, service, and repository composition
- Existing RAG composition tests using deterministic retrieval and context
  injection dependencies
- Existing workflow and notification-delivery orchestration tests

### Faked or mocked external infrastructure

- Telegram application/provider: local fake application in the webhook test;
  existing notification tests use a fake sender.
- Database behind the agent/MCP tool path: a local query-aware session fake.
- Retrieval/context dependencies in existing RAG integration tests: deterministic
  fakes, not Qdrant or embedding services.

### Requires optional external/test infrastructure

There is no repository-supported isolated Supabase project, Qdrant instance,
Telegram sandbox, or LLM test provider. Live validation of those systems is
intentionally not part of normal local or CI tests. A configured `DATABASE_URL`
may point at Supabase PostgreSQL in deployment, but this issue does not connect
to it or use any credentials.

## Execution and results

Run the deterministic Issue #119 tests:

```powershell
$env:DEBUG='false'
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider backend\tests\integration\test_system_boundaries.py -q
```

Result: `4 passed`, with one inherited FastAPI/TestClient deprecation warning.

Run related existing integration suites:

```powershell
$env:DEBUG='false'
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider `
  backend\tests\integration\test_system_boundaries.py `
  backend\tests\api\test_progress_dashboard_api.py `
  backend\tests\telegram\test_backend_client_memory.py `
  backend\tests\telegram\test_notification_delivery.py `
  backend\tests\test_mcp_server.py `
  backend\tests\test_mcp_registry.py `
  backend\tests\test_mcp_progress_tool.py `
  backend\tests\test_academic_tool_gateway.py `
  backend\tests\agents\test_progress_analysis_agent.py `
  backend\tests\workflows\test_daily_workflow.py `
  backend\tests\workflows\test_weekly_workflow.py `
  backend\tests\workflows\test_weekly_analytics.py -q
```

Result: `92 passed, 3 skipped`, with one inherited FastAPI/TestClient
deprecation warning.

`backend/tests/services/test_rag_integration_service.py` is structurally an
existing deterministic RAG boundary suite, but this checkout cannot collect it
without the optional `qdrant_client` package because the current `rag` package
imports its Qdrant retriever eagerly. It was not changed in this issue.

`backend/tests/test_mcp_integration.py` is an inherited stale suite: against
current `main` it reports `78 passed, 23 failed, 2 skipped`. The failures expect
only seven registered tools and patch obsolete module-level `SessionLocal`
attributes. Issue #119 neither changes MCP production code nor absorbs the
exhaustive MCP repair scope assigned to #120.

Run the repository baseline/full suite:

```powershell
$env:DEBUG='false'
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider backend\tests -q
```

The pre-change baseline reaches collection errors in eight unrelated
agent/chat/integration modules because local `langgraph` and `qdrant_client`
packages are absent. These errors are preserved and reported; they are not
hidden or changed by Issue #119.

## Deferred scope

- #120: exhaustive MCP contracts and transport testing
- #121: exhaustive agent routing and behavior testing
- #122: RAG retrieval quality/precision/recall and real vector infrastructure
- #123: load and performance testing
- #124: security testing
- #125: end-to-end production-like user journeys

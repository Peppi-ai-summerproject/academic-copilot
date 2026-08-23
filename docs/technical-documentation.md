# Academic Copilot technical documentation

This is the technical entry point for the Academic Copilot repository. It
describes the implementation currently present in the repository and links to
the detailed design and test records that own lower-level detail.

## Contents

1. [System overview](#system-overview)
2. [Technology stack](#technology-stack)
3. [Repository structure](#repository-structure)
4. [Architecture](#architecture)
5. [Request workflow](#request-workflow)
6. [Installation and local setup](#installation-and-local-setup)
7. [Configuration](#configuration)
8. [Running the system](#running-the-system)
9. [HTTP API](#http-api)
10. [Telegram integration](#telegram-integration)
11. [Database design](#database-design)
12. [Migration strategy](#migration-strategy)
13. [MCP tools and gateway](#mcp-tools-and-gateway)
14. [Agent system](#agent-system)
15. [RAG pipeline](#rag-pipeline)
16. [Analytics](#analytics)
17. [Risk and recommendations](#risk-and-recommendations)
18. [Autonomous workflows](#autonomous-workflows)
19. [Conversation memory and entity context](#conversation-memory-and-entity-context)
20. [Testing](#testing)
21. [Deployment](#deployment)
22. [Security considerations](#security-considerations)
23. [Demo data](#demo-data)
24. [Known limitations](#known-limitations)
25. [Related documentation](#related-documentation)

## System overview

Academic Copilot is a tutor-facing academic support backend. It has two entry
patterns:

- **Conversational:** Telegram or an HTTP client sends a message. The chat
  service restores bounded conversation context, detects intent, resolves
  canonical academic entities, selects only the required agents, and returns a
  deterministic tutor-facing response.
- **Autonomous:** an in-process scheduler runs Monday, daily, and weekly jobs.
  These jobs read the same academic service/repository layer, persist execution
  records, and, where implemented, deliver Telegram notifications.

The application does not use a generative model to compose final chat answers.
Its intent rules, entity resolution, agent summaries, analytics, risk scoring,
and recommendation rules are deterministic. Gemini is used only by the optional
RAG embedding pipeline.

## Technology stack

| Area | Current implementation |
|---|---|
| Runtime and API | Python 3.11 container, FastAPI, Uvicorn, Pydantic 2 |
| Orchestration | LangGraph and project-owned agent routing/state contracts |
| Academic persistence | SQLAlchemy 2 with PostgreSQL/psycopg; Supabase-hosted PostgreSQL may provide the deployed database |
| Conversation persistence | SQLAlchemy store backed by PostgreSQL tables |
| Telegram | `python-telegram-bot`, HTTPS webhook delivery |
| Tool boundary | FastMCP plus `AcademicToolGateway` |
| RAG | document loader, LangChain text splitting, Gemini embeddings, Qdrant retrieval |
| Scheduling | project-owned asynchronous scheduler and timezone-aware daily triggers |
| Tests | pytest; unit, integration, E2E, security, load, migration, and RAG suites |
| Packaging | `backend/requirements.txt`, `backend/Dockerfile`, root `docker-compose.yml` |

Pinned and constrained versions are authoritative in
[`backend/requirements.txt`](../backend/requirements.txt).

## Repository structure

```text
academic-copilot/
|-- backend/
|   |-- app/
|   |   |-- agents/          routing, shared state, and agent implementations
|   |   |-- api/             FastAPI routes and dependencies
|   |   |-- gateways/        academic-tool and optional policy boundaries
|   |   |-- mcp/             FastMCP registry and tool adapters
|   |   |-- repositories/    structured-data queries
|   |   |-- services/        domain and orchestration services
|   |   |-- telegram/        bot commands, handlers, and delivery
|   |   `-- workflows/       Monday, daily, and weekly automation
|   |-- db/migrations/       ordered PostgreSQL SQL migrations
|   |-- scripts/             guarded operational/demo commands
|   `-- tests/               backend tests by layer and capability
|-- docs/                    architecture, API, demo, test, and operations docs
|-- rag/                     ingestion, embeddings, retrieval, and evaluation
|-- docker-compose.yml
`-- pytest.ini
```

## Architecture

The [system architecture diagram](architecture/system-architecture.md) is the
authoritative component view. The key boundaries are:

- FastAPI and Telegram adapters accept requests; they do not query academic
  tables directly.
- `ChatService` owns conversational orchestration, not academic persistence.
- Agents consume the `AcademicToolGateway`; MCP tools call domain services;
  services call repositories.
- PostgreSQL is authoritative for students, structures, enrollments,
  completions, tutor relationships, memory, and workflow records.
- Qdrant stores retrievable document chunks, not student academic records.
- `AgentState` exists for one workflow run. Durable conversation messages and
  entity context live in PostgreSQL.

## Request workflow

The detailed sequence and failure paths are in the
[system workflow guide](architecture/system-workflow.md). In summary:

```text
Telegram webhook or POST /api/v1/chat/messages
  -> ChatService
  -> load memory and canonical entity context
  -> intent detection and tutor-query parsing
  -> AcademicEntityResolver
  -> context merge and stale-context safeguards
  -> AgentSelector and DependencyResolver
  -> AcademicAgentWorkflow (selected agents only)
  -> AcademicToolGateway -> MCP tool -> service -> repository
  -> aggregate status and tutor-facing response
  -> save successful/partial turn and resolved context
```

Explicit valid route selections supplied through the chat API are supported.
Otherwise the deterministic detector selects a route. Unsupported, missing,
ambiguous, or failed explicit entity references produce controlled responses
instead of silently reusing an incompatible stale entity.

## Installation and local setup

### Prerequisites

- Git
- Python 3.11 or a compatible Python supported by the pinned dependencies
- Docker with Docker Compose for container execution
- PostgreSQL for the complete academic-data and conversation-memory feature set
- Qdrant and a Gemini API key only when running or evaluating RAG
- A Telegram bot token and public HTTPS endpoint only for webhook integration

### Native Python setup

From the repository root on PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r backend/requirements.txt
Copy-Item backend/.env.example backend/.env
Set-Location backend
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

On POSIX shells, activate with `source .venv/bin/activate` and copy the example
with `cp`. Run Uvicorn from `backend/` so the `app` package resolves exactly as
it does in the container.

The example configuration defaults `DATABASE_URL` to a local SQLite file. That
is useful for limited startup and isolated development, but the supplied SQL
migrations and the full deployed academic/memory model target PostgreSQL.
Configure a prepared PostgreSQL database for end-to-end behavior.

### Docker setup

```powershell
Copy-Item backend/.env.example backend/.env
docker compose build
docker compose up -d
docker compose logs -f backend
```

The Compose file defines **only** the `backend` service and exposes port 8000.
It does not provision PostgreSQL or Qdrant. Set their externally reachable URLs
in `backend/.env`; from a container, `127.0.0.1` means the backend container
itself, not the Docker host.

Database migrations are operator-run SQL files, not an automatic application
startup step. Apply them only to an authorized PostgreSQL environment, in the
order described below. Never use a production database for local validation.

## Configuration

Settings are loaded by `app.core.config.Settings` from `backend/.env`.
Environment names are case-insensitive through Pydantic settings.

| Variable | Default/example | Purpose |
|---|---|---|
| `APP_NAME` | `AI Academic Copilot API` in example | FastAPI title |
| `APP_VERSION` | `0.1.0` | API version metadata |
| `APP_ENV` | `development` | Environment label returned at `/` |
| `DEBUG` | `true` | FastAPI debug mode |
| `DATABASE_URL` | local SQLite example | SQLAlchemy database URL; PostgreSQL is required for full schemas |
| `SUPABASE_URL`, `SUPABASE_KEY` | empty | Present in the example for Supabase integration; current repositories use `DATABASE_URL` |
| `INTERNAL_SERVICE_KEY` | empty, code setting only | Authenticates the Telegram backend client to chat; add it to `.env` for trusted Telegram requests |
| `BACKEND_BASE_URL` | `http://127.0.0.1:8000` | URL used by the Telegram backend client |
| `TELEGRAM_BOT_TOKEN` | empty | Bot credential |
| `TELEGRAM_WEBHOOK_URL` | empty | Public webhook URL configuration |
| `TELEGRAM_WEBHOOK_SECRET` | empty | Secret checked on inbound webhook requests |
| `TELEGRAM_WEBHOOK_ENABLED` | `false` | Initializes Telegram and enables webhook processing |
| `SCHEDULER_ENABLED` | `false` | Starts scheduled jobs with the FastAPI lifecycle |
| `SCHEDULER_TIMEZONE` | `UTC` | Scheduler/Monday IANA timezone |
| `MONDAY_WORKFLOW_HOUR`, `MONDAY_WORKFLOW_MINUTE` | `6`, `0` | Monday briefing time |
| `DAILY_WORKFLOW_HOUR`, `DAILY_WORKFLOW_MINUTE` | `6`, `0` | Daily risk job time |
| `DAILY_WORKFLOW_TIMEZONE` | `Europe/Helsinki` | Daily job IANA timezone |
| `WEEKLY_WORKFLOW_HOUR`, `WEEKLY_WORKFLOW_MINUTE` | `6`, `0` | Monday aggregate-report time |
| `WEEKLY_WORKFLOW_TIMEZONE` | `Europe/Helsinki` | Weekly job IANA timezone |
| `GEMINI_API_KEY` | empty | Optional embedding provider credential |
| `QDRANT_URL` | `http://127.0.0.1:6333` | Optional vector-store endpoint |
| `QDRANT_COLLECTION_NAME` | `academic_knowledge` | Qdrant collection |
| `KNOWLEDGE_BASE_DIR` | `docs/knowledge_base` | Optional source-document override |
| `RAG_EVALUATION_DATASET` | `rag/evaluation/evaluation_dataset.json` | Evaluation dataset override |
| `RAG_EVALUATION_REPORTS_DIR` | `rag/evaluation/reports` | Evaluation output override |

When Telegram webhook mode is enabled, startup validation requires a bot token
and webhook secret. Keep every real credential out of Git.

## Running the system

From `backend/` with the environment activated:

```powershell
python -m uvicorn app.main:app --reload
python -m app.mcp
python scripts/run_scheduler_checks.py
```

The API root is `GET /`. Due to the prefixes currently declared in both router
layers, the health URLs are `GET /api/v1/health/health/` and
`GET /api/v1/health/health/database`. Interactive OpenAPI documentation is at
`/docs`; the schema is at `/openapi.json`.

## HTTP API

These are the routes registered by `app.main` and `app.api.api_router`.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/` | Process metadata and liveness message |
| `GET` | `/api/v1/health/health/` | Application health service status |
| `GET` | `/api/v1/health/health/database` | Database connectivity status |
| `POST` | `/api/v1/chat/messages` | Process one conversational turn |
| `GET` | `/api/v1/sessions/{telegram_user_id}` | Read the legacy in-process Telegram session view |
| `DELETE` | `/api/v1/sessions/{telegram_user_id}` | Delete that legacy session view |
| `GET` | `/api/v1/students/{student_id}/progress-dashboard` | Canonical dashboard; optional `as_of_date=YYYY-MM-DD` |
| `POST` | `/api/v1/telegram/webhook` | Accept a Telegram update when enabled and authenticated |

`backend/app/api/routes/reports.py` and `students.py` exist but are not included
by the current API router, so they are not public endpoints.

Example chat request (fictional identifiers):

```http
POST /api/v1/chat/messages HTTP/1.1
Content-Type: application/json

{
  "message": "How is student S001 progressing?",
  "telegram_user_id": 900001,
  "telegram_chat_id": 900001,
  "username": "demo_tutor"
}
```

```json
{
  "reply": "Progress analysis completed. ...",
  "conversation_id": "00000000-0000-4000-8000-000000000001"
}
```

The response text depends on available academic evidence. `message` is 1–4000
characters. `student_id`, `selected_agents`, and `conversation_id` are optional.
The Telegram client adds `X-Internal-Service-Key` when configured; the webhook
expects `X-Telegram-Bot-Api-Secret-Token`.

Example dashboard request:

```http
GET /api/v1/students/1/progress-dashboard?as_of_date=2025-10-15
```

Successful service output is returned unchanged. A missing student is 404;
other controlled service failure is mapped to 500.

## Telegram integration

The bot registers `/start`, `/help`, `/status`, `/student <id>`,
`/progress <id>`, `/risk <id>`, and `/events <id>`, plus ordinary text
messages. Academic commands translate to chat messages and call the same
`POST /api/v1/chat/messages` path; they do not bypass orchestration.

Telegram sends an HTTPS update to `/api/v1/telegram/webhook`. The route checks
the configured secret header before deserializing and processing the update.
Application startup initializes the bot and notification sender only when
`TELEGRAM_WEBHOOK_ENABLED=true`.

Autonomous workflows use the notification adapter for proactive tutor messages.
Tutor-to-chat mappings and tutor assignments must already exist for delivery.
Tutor-facing message presentation is governed by the authoritative
[Telegram Response Design System](design/telegram-response-design-system.md).
See [Telegram webhook setup](deployment/telegram-webhook-setup.md); review all
environment-specific values in that historical deployment note before reuse.

## Database design

PostgreSQL holds authoritative structured records. Important domains are:

| Domain | Tables |
|---|---|
| Student and progress | `students`, `course_completions`, curriculum tables |
| Academic structure | `degree_programmes`, `student_groups`, `student_group_courses`, `courses` |
| Participation and teaching | `course_enrollments`, `teacher_course_assignments` |
| Tutor scope | `tutors`, `tutor_student_assignments`, `tutor_meetings` |
| Conversation | `conversation_memory_messages`, `telegram_conversation_mappings` |
| Automation | `weekly_workflow_reports`, `workflow_execution_logs` |

`course_enrollments` describes participation state (`ENROLLED`, `IN_PROGRESS`,
`COMPLETED`, or `WITHDRAWN`). `course_completions` is the authoritative academic
result and credit source, with `PASSED`/`FAILED`, grade, date, and canonical
course linkage. Enrollment status or grade truthiness must not be substituted
for the completion result status; grade `0` is meaningful data.

Foreign keys use restrictive deletion for academic relationships. Canonical
student/course and group/course pairs have uniqueness constraints. Programme
and group codes additionally have case-insensitive unique indexes. See the
[academic data model](data/tutor-academic-data-model.md) and
[student-group model](student-groups-and-academic-structure.md).

## Migration strategy

Migrations are additive PostgreSQL SQL scripts under `backend/db/migrations`.
There is no migration runner in application startup, and the duplicate numeric
prefixes are filenames rather than a framework-managed revision graph.

Apply creation/extension scripts in repository order while respecting their
dependencies and deployment records:

1. `001_create_conversation_memory.sql`
2. `002_create_tutor_assignments.sql`
3. `003_create_weekly_workflow_reports.sql`
4. both `004_create_tutor_meetings.sql` and `004_create_workflow_execution_logs.sql`
5. `005_extend_tutor_academic_data.sql`
6. `006_seed_tutor_academic_demo_data.sql`
7. `007_add_conversation_entity_context.sql`
8. `008_add_student_groups_and_academic_structure.sql`
9. `009_seed_dbs24_demo_completions.sql`
10. `010_seed_realistic_academic_demo_dataset.sql`

The seed migrations use canonical identifiers and preserve existing completion
records where documented. Migration 008 deliberately aborts on conflicting
legacy DIN24/DII101 completion records rather than discarding meaningful data.
Migration 009 and 010 are required for already-deployed environments because
editing an older applied migration would not update them.

Before production use: back up, review SQL, test against a disposable schema,
record application, and execute with an authorized PostgreSQL tool. Do not run
the drop script or any seed against production without an explicit data policy.

## MCP tools and gateway

The production agents depend on `AcademicToolGateway`. Its implementation calls
the same MCP tool functions in-process (offloading synchronous work with
`asyncio.to_thread`). `python -m app.mcp` exposes those functions through
FastMCP over its configured transport. This preserves one service/repository
contract without making chat depend on a separate MCP network process.

| Tools | Purpose |
|---|---|
| `ping` | MCP health |
| `get_student`, `get_student_by_number`, `search_students` | Student identity and search |
| `get_course`, `search_courses` | Course identity and discovery |
| `get_teacher`, `search_teachers` | Teacher identity and discovery |
| `get_course_roster`, `get_student_enrollments`, `get_enrollment` | Enrollment queries |
| `get_course_teachers`, `get_teacher_courses` | Teaching assignments |
| `get_course_results`, `get_student_results`, `get_course_completion_analytics` | Result records and course analytics |
| `search_student_groups`, `get_student_group`, `get_student_group_students`, `get_student_group_courses` | Student-group structure |
| `get_progress` | Completed versus expected progress |
| `get_study_right` | Study-right state and expiry |
| `get_curriculum` | Programme/semester milestones |
| `get_upcoming_events` | Date-filtered academic events |
| `get_student_dashboard` | Combined student overview |
| `generate_report` | Structured academic report |

See [MCP server](mcp-server.md) and the
[academic-tool gateway design](architecture/academic_tool_gateway.md).

## Agent system

| Agent | Responsibility | Main dependencies |
|---|---|---|
| `TutorDataQueryAgent` | Tutor search, lookup, roster, results, groups, and teaching queries | Academic gateway |
| `ProgressAnalysisAgent` | Completed/expected ECTS and delay summary | Academic gateway |
| `StudyRightsAgent` | Study-right status and expiry | Academic gateway |
| `CalendarAgent` | Upcoming academic events | Academic gateway |
| `RiskDetectionAgent` | Conversational progress/study-right/event risk factors | Academic gateway |
| `RecommendationAgent` | Evidence-based deterministic advice | Academic gateway, policy gateway, prior risk result |
| `ReportingAgent` | Aggregate prior academic agent results | Prior agent results |
| `CommunicationAgent` | Compose selected prior results for delivery | Prior agent results |

`AgentState` carries request metadata, resolved entities, parameters, selected
and pending routes, per-agent results, warnings/errors, final response, and
workflow status for one run. The selector maps detected intent to roots; the
dependency resolver expands only declared dependencies in topological order.
For example, recommendation depends on risk, while reporting expands progress,
study rights, risk, and recommendation. Not every agent runs on every request.

Every agent returns an `AgentResult` with `SUCCESS`, `PARTIAL`, `FAILED`, or
`SKIPPED`. The workflow is completed when all selected work succeeds, partial
when some usable success/partial evidence exists, and failed when no usable
selected work completes or orchestration fails. Results are aggregated into a
tutor-facing response; unavailable evidence remains visible through warnings.

The historical [multi-agent architecture](architecture/multi_agent_architecture.md)
is retained for design history. Current contracts are documented by the
[shared state](architecture/shared_agent_state.md) and
[LangGraph workflow](architecture/langgraph_agent_workflow.md) guides.

## RAG pipeline

```text
documents -> DocumentLoader -> TextChunker
          -> GeminiEmbeddingProvider via EmbeddingService
          -> Qdrant collection
query -> QdrantRetriever -> RetrievalService
      -> RagIntegrationService/context injection -> policy evidence
```

`rag/ingest_pipeline.py` performs ingestion. Retrieval reuses the embedding
service for query vectors and returns ranked document chunks. The backend
`RagPolicyContextGateway` adapts retrieved context for recommendations.

The default production `ChatService` creates the workflow without an explicit
policy gateway; the workflow therefore composes
`UnavailablePolicyContextGateway`. `RagPolicyContextGateway` is optional and
must be deliberately wired with a configured retrieval service. Consequently,
ordinary Telegram queries do not all use RAG, Qdrant contains no academic
records, and Gemini does not generate final responses.

See [RAG backend integration](architecture/rag_backend_integration.md).

## Analytics

- `ProgressService` combines completed ECTS from authoritative passed
  completions with the curriculum milestone for the student's current semester.
- `ExpectedProgressService` selects the cumulative curriculum milestone; it
  does not calculate completed credits.
- Delay is deterministic: `completed_ects < expected_ects`; the deficit is
  `max(expected_ects - completed_ects, 0)`. Equality is on track and there is no
  tolerance band.
- `EctsAnalyticsService` presents individual and cohort progress, percentages,
  status, and distance to the 240-ECTS graduation target.
- `StudentDashboardService` combines profile, progress, study right, risk,
  events/actions, and academic health through existing services.
- Weekly analytics aggregate tutor-scoped workflow evidence and persist the
  previous completed week's report.

Detailed behavior is covered by the [progress dashboard API](api/progress-dashboard.md)
and [academic health score](academic-health-score.md).

## Risk and recommendations

The canonical Issue #95 risk score is separate from the lighter risk-factor
classification used by `RiskDetectionAgent`. `AcademicRiskScoringService`
combines four verified indicators with maximum weights: academic delay 50,
study right 30, tutor meetings 10, and academic events 10. An expired study
right enforces a minimum score of 70. Classification thresholds and every
indicator rule are maintained in the
[academic risk scoring model](academic-risk-scoring-model.md).

Canonical assessment is `COMPLETE` when all indicators exist and `PARTIAL`
when optional meeting/event evidence is unavailable. By default a partial
assessment does not invent a score or risk level; explicitly enabled partial
classification normalizes over available indicator weights. Unavailable
evidence is never silently treated as safe. Academic health converts verified
risk evidence to an inverse support-oriented score with `URGENT_SUPPORT`,
`NEEDS_ATTENTION`, `STABLE`, and `STRONG` levels.

Recommendations follow:

```text
verified academic/risk evidence
  -> deterministic recommendation rules and templates
  -> optional retrieved policy evidence
  -> advisory recommendation with evidence and limitations
```

The recommendation engine reports `COMPLETE` or `PARTIAL`; it preserves missing
evidence and does not replace tutor judgment. See
[recommendation engine](architecture/recommendation-engine.md) and
[recommendation templates](architecture/recommendation-templates.md).

## Autonomous workflows

When `SCHEDULER_ENABLED=true`, FastAPI startup registers three independent jobs:

| Workflow | Schedule and behavior |
|---|---|
| Monday | Monday at configured scheduler/Monday timezone; builds tutor-scoped weekly briefings, delivers Telegram messages, and logs execution |
| Daily | Every day in its configured timezone; evaluates automatic risk, creates academic alerts, delivers configured notifications, and logs execution |
| Weekly | Monday in its configured timezone; aggregates the previous completed week and persists a weekly report plus execution metadata |

The Monday and weekly jobs are distinct: weekly aggregate persistence is not a
second tutor briefing delivery path. All use short-lived database sessions.
Duplicate scheduler job IDs are rejected rather than registered twice.

A guarded manual Monday demo is available from `backend/`:

```powershell
python scripts/run_monday_briefing.py --confirm-send
```

This command can send real Telegram messages using configured production-like
mappings. Use it only with explicit operational approval and do not repeat it
casually; delivery deduplication is not guaranteed by the CLI.

See [Monday workflow](architecture/monday_workflow.md),
[daily workflow](architecture/daily_workflow.md), and
[weekly workflow](architecture/weekly_workflow.md).

## Conversation memory and entity context

`SQLAlchemyConversationMemoryStore` maps a Telegram user/chat pair to a UUID
conversation and retains a bounded 20-message window. Completed and partial
turns persist user/assistant messages and canonical resolved entities.

Entity context supports `STUDENT`, `STUDENT_GROUP`, `COURSE`, and `TEACHER`.
An explicit successfully resolved entity in the current message replaces the
older entity of the same type while unrelated types remain. Group context may
narrow globally ambiguous courses only when exactly one candidate belongs to
that group. Zero or multiple remaining candidates stay controlled. Failed or
ambiguous explicit switches do not overwrite valid context and must not cause
the old entity to be answered as though it were the explicit target.

See the [system workflow](architecture/system-workflow.md#multi-turn-context-and-precedence)
for sequence diagrams and examples.

## Testing

Tests are organized under `backend/tests` by agents, API, services, workflows,
Telegram, integration, E2E, evaluation, load, security, MCP, repositories, and
migrations. RAG tests live under `rag/tests`. Most tests use deterministic fakes
or SQLite fixtures; PostgreSQL-specific migration tests inspect SQL safety and
contracts rather than applying changes to Supabase.

From the repository root:

```powershell
python -m pytest backend/tests -q
python -m pytest backend/tests/agents backend/tests/services -q
python -m pytest backend/tests/integration backend/tests/e2e -q
python -m pytest backend/tests/test_mcp_integration.py backend/tests/test_mcp_tool_contracts.py -q
python -m pytest backend/tests/workflows backend/tests/telegram -q
python -m pytest backend/tests/test_academic_data_migrations.py backend/tests/test_realistic_academic_demo_dataset.py -q
python -m pytest rag/tests -q
python -m compileall backend/app
git diff --check
```

External Gemini/Qdrant integration tests may skip when credentials or services
are unavailable. Do not hardcode a passing-test count. See the
[testing documentation](testing/) index files, especially
[integration tests](testing/integration_tests.md),
[E2E validation](testing/copilot-e2e-validation.md), and
[security testing](testing/issue-124-security-testing.md).

## Deployment

The checked-in deployment unit is the backend Docker image. Compose builds it,
loads `backend/.env`, publishes port 8000, and applies `unless-stopped` restart
behavior. PostgreSQL/Supabase and optional Qdrant are external services.

A typical server update is: review and back up, pull the approved revision,
apply any reviewed outstanding migrations to the target PostgreSQL database,
rebuild/restart the backend container, verify root/health/OpenAPI and database
connectivity, then verify Telegram webhook delivery. Rollback planning must
account for both image and schema compatibility.

Telegram webhook mode requires a public HTTPS URL. The existing deployment note
uses Nginx as a TLS reverse proxy, but Nginx is server configuration and is not
defined by `docker-compose.yml`. Set the webhook URL to
`https://<public-host>/api/v1/telegram/webhook`, register the same secret with
Telegram, and avoid exposing port 8000 publicly once the reverse proxy is
verified. See [Telegram webhook setup](deployment/telegram-webhook-setup.md).

## Security considerations

- Store bot tokens, API keys, database URLs, internal service keys, and webhook
  secrets in environment/secret management; never commit real values.
- The webhook rejects requests without the configured Telegram secret header.
  This is a shared-secret check, not a broad claim of end-user authorization.
- The internal service key marks chat calls from the Telegram adapter as
  trusted. Configure the same non-empty value on both sides.
- Academic records are sensitive personal data. Minimize access, retention,
  response scope, and logging; do not log complete records or credentials.
- Repository queries and workflows must preserve tutor-assignment boundaries.
  Administrative tutor/chat mappings require controlled provisioning.
- Restrict database, Qdrant, container, and server access; terminate HTTPS at a
  reviewed proxy and rotate exposed credentials.
- Tests establish selected contracts, not a complete security guarantee. See
  [security testing](testing/issue-124-security-testing.md).

## Demo data

The repository contains fictional, deterministic records for demonstrations.
DIN24 and the Issue #252 personas cover on-track and delayed progress,
PASSED/FAILED/no-result course cases, study-right and meeting risk evidence, and
recommendation scenarios. They are not real students and must not be confused
with production records. The authoritative matrix and expected conversations
are in the [realistic academic demo dataset](testing/issue-252-realistic-academic-demo-dataset.md).

## Known limitations

- Policy RAG is not composed into the default production chat singleton.
- Missing risk or policy evidence can yield partial analysis; the system does
  not infer that missing evidence means low risk.
- Intent and entity extraction are deterministic and cover bounded language
  patterns, so unfamiliar phrasing may require clarification.
- The canonical cohort-wide risk service is used by workflows but is not a
  dedicated public Telegram command or HTTP endpoint.
- Monday manual delivery has no general end-user deduplication guarantee.
- Event, study-right, and expected-progress results are date-sensitive.
- Telegram notification scope depends on correctly provisioned tutor
  assignments and chat mappings.
- There is no generative answer LLM in the production chat workflow.
- Compose does not provision PostgreSQL, Qdrant, Nginx, or database migrations.
- The session endpoints expose a legacy in-process view, distinct from the
  durable SQL conversation memory used by `ChatService`.

## Related documentation

| Document | Role |
|---|---|
| [System architecture](architecture/system-architecture.md) | Current component and data-boundary view |
| [System workflow](architecture/system-workflow.md) | Current request, routing, context, and failure sequence |
| [Demo scenario 1](demo/demo-scenario-1-student-progress.md) | Student progress walkthrough |
| [Demo scenario 2](demo/demo-scenario-2-risk-detection.md) | Risk and recommendation walkthrough |
| [Demo scenario 3](demo/demo-scenario-3-autonomous-weekly-briefing.md) | Autonomous Monday briefing walkthrough |
| [Realistic demo dataset](testing/issue-252-realistic-academic-demo-dataset.md) | Fictional personas and assertions |
| [Tutor academic data model](data/tutor-academic-data-model.md) | Structured academic schema extension |
| [Student groups and structure](student-groups-and-academic-structure.md) | Canonical programme/group model |
| [MCP server](mcp-server.md) | MCP process and registration |
| [Progress dashboard API](api/progress-dashboard.md) | Dashboard contract |
| [Telegram deployment](deployment/telegram-webhook-setup.md) | Environment-specific reverse proxy history |
| [Integration testing](testing/integration_tests.md) | Integration suite guidance |
| [Security testing](testing/issue-124-security-testing.md) | Tested security contracts and scope |
| [Multi-agent architecture](architecture/multi_agent_architecture.md) | Historical design; use current architecture/workflow docs for present behavior |

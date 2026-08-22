# Academic Copilot system architecture

This is the high-level source of truth for the implemented architecture. It
shows tutor-initiated conversations and system-initiated workflows; detailed
component documents remain authoritative for their individual contracts.

## System diagram

```mermaid
flowchart TB
    subgraph UI[User and interface]
        Tutor[Tutor teacher]
        Telegram[Telegram Bot API and private chat]
    end

    subgraph App[FastAPI application]
        Webhook[Telegram webhook route and handlers]
        BackendClient[Internal BackendClient]
        ChatAPI[Chat API route]
        ChatService[ChatService]
        EntityResolver[AcademicEntityResolver]
        Memory[Conversation memory and entity context]
    end

    subgraph AI[AI orchestration]
        Selection[Intent detection, agent selection, dependency planning]
        Graph[LangGraph workflow and AgentState]
        Agents[Selected deterministic agents]
        TutorAgent[TutorDataQueryAgent]
        AnalysisAgents[Progress, study-right, risk and calendar agents]
        Recommendation[RecommendationAgent]
        Reporting[ReportingAgent]
        Communication[CommunicationAgent and response formatting]
    end

    subgraph Tools[Tool and knowledge boundaries]
        AcademicGateway[AcademicToolGateway]
        MCPTools[MCP academic tool functions]
        MCPServer[FastMCP server and registry - stdio exposure]
        PolicyGateway[PolicyContextGateway - optional]
        RAG[RAG retrieval and context injection]
        Embeddings[EmbeddingService]
        Qdrant[(Qdrant policy and document vectors)]
    end

    subgraph Domain[Domain and structured data]
        AcademicServices[Student, group, course, result and event services]
        AnalysisServices[Progress, risk, health and analytics services]
        Repositories[SQLAlchemy repositories]
        PostgreSQL[(Supabase or PostgreSQL)]
    end

    subgraph Auto[Autonomous workflow layer]
        Scheduler[Timezone-aware Scheduler]
        Monday[Monday tutor briefing workflow]
        Daily[Daily risk and academic-alert workflow]
        Weekly[Weekly aggregate-report workflow]
        Briefings[Briefing and alert generation]
        Notification[Telegram notification delivery]
        ExecutionLog[WorkflowExecutionRecorder]
    end

    subgraph External[External model dependency]
        ModelAPI[Gemini embedding API when RAG is configured]
    end

    Tutor -->|message| Telegram
    Telegram -->|signed webhook update| Webhook
    Webhook -->|handler request| BackendClient
    BackendClient -->|authenticated chat request| ChatAPI
    ChatAPI --> ChatService
    ChatService <-->|load and save turns and canonical entities| Memory
    Memory -->|SQL persistence| PostgreSQL
    ChatService -->|resolve academic entities| EntityResolver
    EntityResolver --> AcademicGateway
    ChatService --> Selection
    Selection -->|ordered selected routes| Graph
    Graph -->|execute only selected agents| Agents
    Agents --- TutorAgent
    Agents --- AnalysisAgents
    Agents --- Recommendation
    Agents --- Reporting
    Agents --- Communication
    TutorAgent -->|structured academic operations| AcademicGateway
    AnalysisAgents -->|structured academic operations| AcademicGateway
    Recommendation -->|optional policy retrieval| PolicyGateway
    Reporting -->|consume prior AgentResults| Graph
    Communication -->|format verified AgentResults| Graph
    Graph -->|final response| ChatService
    ChatService --> ChatAPI
    ChatAPI --> BackendClient
    BackendClient -->|reply| Webhook
    Webhook -->|send response| Telegram

    AcademicGateway -->|in-process adapter| MCPTools
    MCPServer -.->|registers and exposes the same tools| MCPTools
    MCPTools --> AcademicServices
    MCPTools --> AnalysisServices
    AcademicServices --> Repositories
    AnalysisServices --> Repositories
    Repositories -->|SQL| PostgreSQL

    PolicyGateway --> RAG
    RAG -->|query embedding| Embeddings
    Embeddings -->|embedding request| ModelAPI
    RAG -->|vector search| Qdrant

    Scheduler -->|Monday schedule| Monday
    Scheduler -->|daily schedule| Daily
    Scheduler -->|previous-week schedule| Weekly
    Monday --> AcademicServices
    Monday --> AnalysisServices
    Daily --> AcademicServices
    Daily --> AnalysisServices
    Weekly --> AcademicServices
    Weekly --> AnalysisServices
    Monday --> Briefings
    Daily --> Briefings
    Monday -->|weekly tutor briefing| Notification
    Daily -->|academic alerts| Notification
    Notification -->|application-owned transport| Telegram
    Monday --> ExecutionLog
    Daily --> ExecutionLog
    Weekly --> ExecutionLog
    ExecutionLog -->|aggregate lifecycle metadata| PostgreSQL
```

`MCPAcademicToolGateway` invokes MCP tool functions in-process on worker
threads. `FastMCP` registers those same functions for a separate stdio server;
the gateway does not make a fictitious network hop through that server.

## Presentation view

```mermaid
flowchart LR
    Tutor[Tutor] --> Telegram[Telegram]
    Telegram --> FastAPI[FastAPI and ChatService]
    FastAPI --> Agents[LangGraph and selected agents]
    Agents --> MCP[MCP tools via AcademicToolGateway]
    MCP --> Services[Academic and analytics services]
    Services --> DB[(Supabase or PostgreSQL)]
    Agents -->|optional policy context| RAG[RAG retrieval]
    RAG <--> Qdrant[(Qdrant)]
    RAG --> Embed[External embedding model]
    Scheduler[Scheduler] --> Workflows[Monday, Daily and Weekly workflows]
    Workflows --> Services
    Workflows --> Notify[Briefings, alerts and Telegram delivery]
    Notify --> Telegram
    Workflows --> Logs[Execution logs]
    Logs --> DB
```

No answer-generation LLM is invoked by the current production agent workflow.
Agents, risk rules, recommendations, reports, and templates are deterministic.
The configured external model integration supplies Gemini embeddings for the
optional RAG pipeline.

## Conversational request flow

1. Telegram posts a signed update to the FastAPI webhook route.
2. The handler sends an authenticated request through `BackendClient` to
   `/api/v1/chat/messages` and later sends the returned reply to Telegram.
3. `ChatService` loads PostgreSQL-backed memory, detects intent, resolves
   academic entities, merges canonical context, and creates an agent plan.
4. LangGraph executes only the ordered selected agents against `AgentState`.
5. Academic agents use `AcademicToolGateway`; MCP tool functions call domain
   services and repositories rather than exposing database sessions to agents.
6. `RecommendationAgent` may request policy context through
   `PolicyContextGateway`. Without configured RAG, the explicit unavailable
   gateway preserves partial-result semantics.
7. The workflow/formatter returns the response. `ChatService` persists a
   successful or partial turn and its STUDENT, STUDENT_GROUP, COURSE, and
   TEACHER context before the handler replies.

The chat API can also be called by another authorized client; Telegram is the
principal demonstrated interface, not a requirement of `ChatService`.

## Autonomous workflow flow

1. FastAPI lifespan starts the scheduler only when enabled and registers
   Monday, Daily, and Weekly jobs with configured timezones.
2. Monday discovers active tutors and assigned students, consumes
   progress/risk/event services, renders briefings, and delivers them through
   the lifecycle-owned Telegram sender.
3. Daily runs automatic risk detection, alert generation, and authorized
   Telegram alert delivery.
4. Weekly calculates and persists aggregate previous-week reports; it does not
   send tutor briefings.
5. Execution recorders store aggregate lifecycle status, counts, timing, and
   safe error metadata in PostgreSQL.

Autonomous workflows call domain services/repositories directly. They do not
route through ChatService, LangGraph, or MCP because they are server-side
application orchestrators rather than agent tool consumers.

## Component responsibilities

| Component | Responsibility |
|---|---|
| Telegram | Tutor interface and transport for replies and proactive notifications. |
| FastAPI routes | Authenticate Telegram webhooks/internal chat calls and expose APIs. |
| `ChatService` | Coordinate intent, entity resolution, context, planning, workflow execution, and persistence. |
| Conversation memory | Persist bounded turns and canonical entities per authorized conversation scope. |
| Router/planner | Select a supported route and expand only its declared dependencies. |
| LangGraph and `AgentState` | Execute the ordered plan and carry typed state/results. |
| `TutorDataQueryAgent` | Run resolved student, group, course, result, and teacher queries. |
| Analysis agents | Produce progress, study-right, risk, and calendar results from tools. |
| `RecommendationAgent` | Map verified risk evidence to actions and optionally retrieve policy context. |
| `ReportingAgent` | Assemble prior verified results into a structured tutor report. |
| `CommunicationAgent` | Render available verified results and recommendations when selected. |
| `AcademicToolGateway` | Async validated boundary between agents/entity resolution and academic tools. |
| MCP tools/server | Tool functions adapt services; FastMCP registers them for stdio exposure. |
| Academic services | Own student, group, course, result, assignment, study-right, and event behavior. |
| Analysis services | Own deterministic progress, delay, risk, health, and analytics calculations. |
| Repositories | Perform SQL access and map rows into service inputs. |
| Supabase/PostgreSQL | Store authoritative academic, assignment, conversation, report, and log data. |
| `PolicyContextGateway` | Separate optional policy retrieval from student facts. |
| RAG/Qdrant | Embed queries and retrieve policy/document chunks from the vector index. |
| Gemini embedding API | Configurable RAG embeddings; not answer generation. |
| Scheduler | Trigger registered timezone-aware jobs during FastAPI lifespan. |
| Autonomous workflows | Reuse domain logic for briefings, risk/alerts, and reports. |
| Telegram notification delivery | Send already-rendered workflow messages to authorized destinations. |
| Workflow execution logging | Persist privacy-safe aggregate execution metadata. |

## Architectural boundaries

- Agents/entity resolution do not open database sessions or query PostgreSQL
  directly; structured agent data crosses gateway/tool/service boundaries.
- MCP tools adapt services, services own domain behavior, and repositories own
  SQL. LangGraph coordinates execution rather than replacing those layers.
- Risk, health, progress, recommendation decisions, and templates are
  deterministic. Missing evidence retains COMPLETE, PARTIAL, UNAVAILABLE, or
  UNPROCESSABLE semantics.
- RAG knowledge is optional and cannot override canonical academic facts.
- Telegram transport is outside agents/domain services. Workflows hand rendered
  messages to the configured notification sender.
- Autonomous workflows reuse services/repositories but are not conversational
  agent requests.

## Data classification

### Authoritative structured data

Supabase/PostgreSQL stores students, programmes, groups, courses, enrollments,
completions/results, teachers/tutors, assignments, study rights, meetings,
events, curriculum, weekly reports, conversation memory, and workflow history.

### Knowledge and RAG data

Policies, documentation, and guidance are loaded, chunked, embedded, and
indexed in Qdrant. Query-time RAG returns attributed supporting context. Qdrant
does not store or replace canonical student academic records.

### Conversation state

Production `SQLAlchemyConversationMemoryStore` persists bounded messages and
resolved canonical entity snapshots in PostgreSQL by conversation/owner scope.
Tests can inject an in-memory implementation. `AgentState` is per-execution
state, not the durable conversation database.

## Current limitations and configuration notes

- The default workflow uses `UnavailablePolicyContextGateway`; production RAG
  needs an explicit `RagPolicyContextGateway` composition not currently wired
  in the default `ChatService` singleton.
- The repository contains an LLM-ready context pipeline, but no
  answer-generation LLM call in the production chat workflow.
- The in-process scheduler is disabled by default. Deployment must enable it
  and ensure only the intended application process owns scheduled execution.
- Monday delivery has no durable per-recipient deduplication key; execution logs
  audit runs but do not suppress repeated manual sends.

# Agent collaboration testing

## Purpose

Issue #89 validates the existing production multi-agent architecture without
adding another workflow or changing agent responsibilities. The tested public
workflow entry point is `AcademicAgentWorkflow.run(AgentState)`. The highest
application boundary is `ChatService.process_message`, using the real workflow
and agents with only external data, policy, memory, and delivery boundaries
replaced by deterministic fakes.

## Successful scenario and route

The tutor scenario asks for a review of student STU-001's progress and study
right, risk assessment, next actions, a structured report, and a tutor-facing
response. Because current routing is explicit rather than inferred, the test
selects the supported production sequence:

```text
progress → study_rights → risk → recommendation → reporting → communication
```

The scenario uses behind-schedule progress and an expiring study right. It
asserts canonical `AgentResult` objects for every route, ordered completion,
empty pending state, consistent request/student context, six workflow steps,
and a valid partial terminal status reflecting attention-required upstream
results. Each result remains distinguishable in `agent_results`.

Recommendation consumes the risk result and supporting progress/study-right
results. Reporting aggregates verified performance, study-right, risk, and
recommendation sections. Communication alone supplies `final_response`.
Warnings and errors accumulate without removing earlier results.

## Failure and bounded scenarios

An unavailable registered collaborator (`calendar`) demonstrates orchestration
error accumulation while preserving the completed progress result. Reporting
and Communication still produce a qualified response without exposing the
internal error or fabricating a no-risk conclusion.

A six-agent route with `max_steps=3` proves bounded execution: exactly the first
three agents complete once, the remaining three stay pending, and no final
response is produced before Communication runs. Separate workflow invocations
prove that mutable warnings and result dictionaries are isolated.

## Deterministic boundaries

The specialized production agents use the injected `AcademicToolGateway`
abstraction rather than invoking MCP transport directly. The deterministic
academic gateway supplies fixed student, progress, study-right, and event data;
the test asserts the exact gateway methods, order, and student identifier used
by ProgressAnalysisAgent, StudyRightsAgent, and RiskDetectionAgent. The risk
agent retrieves its own academic inputs through that boundary, while
RecommendationAgent consumes the canonical upstream results already stored in
`AgentState.agent_results`. The policy gateway supplies fixed evidence and its
exact queries are asserted. No real MCP transport,
repository, PostgreSQL, Supabase, Qdrant, RAG provider, embedding model, LLM,
Telegram client, credential, or network call is used.

The ChatService scenario uses `InMemoryConversationMemoryStore`, which
implements Issue #88's production store contract for tests. A reconstructed
ChatService receives the prior bounded user/assistant turn through the typed
`AgentState.memory` snapshot. The next workflow still begins with empty
same-run `agent_results`; durable cross-request memory is therefore not confused
with collaboration state. Raw Telegram identifiers, mappings, database
sessions, and internal service keys do not enter the trusted workflow state.

Conversation memory differs from RAG knowledge retrieval, MCP academic tool
execution, and Telegram network delivery. Those integrations are intentionally
outside this deterministic collaboration suite.

## Commands

Focused tests:

```powershell
python -m pytest backend/tests/agents/test_agent_collaboration.py -v
```

Affected tests include agent contracts/state/reducers/workflow, all six agents,
ChatService, conversation memory, and existing end-to-end integration tests.

Complete backend suite:

```powershell
python -m pytest backend/tests -q
```

The pre-change latest-main baseline was 461 passed, 23 known legacy MCP
integration failures, and one warning. Verification after adding the Issue #89
tests produced:

- focused collaboration suite: 5 passed;
- affected agent, workflow, ChatService, memory, and integration suite: 199 passed;
- complete backend suite: 466 passed, 23 known legacy failures, and one warning.

The five new collaboration tests introduce no new failures. The earlier
394-passed Issue #88 baseline predates merged Issues #91/#92 and is therefore
not the direct baseline of this branch.

## Limitations

The tests validate deterministic collaboration and application integration,
not production deployment, actual Telegram delivery, PostgreSQL persistence,
MCP transport, RAG retrieval, or LLM behavior. Routing selection remains an
explicit caller responsibility in the current production architecture.

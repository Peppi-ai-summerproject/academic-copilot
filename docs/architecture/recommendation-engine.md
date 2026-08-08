# Recommendation Engine architecture (Issue #110)

## Purpose and boundary

The Recommendation Engine is a deterministic application/domain component
that converts structured, pre-calculated academic evidence into structured
tutor-action decisions. It is implemented in
`backend/app/services/recommendation_engine.py` and is usable without
LangGraph, MCP, RAG, a database, or an LLM.

The engine owns:

- approved mappings from academic risk dimensions to advisory action types;
- priority gates for those mappings;
- stable reason codes;
- preservation of evidence provenance and data-completeness status.

The engine does **not** calculate ECTS, expected progress, delay, study-right
status, academic risk scores, or event applicability. Those facts remain owned
by the existing analytics and risk services. It does not retrieve policy, call
MCP tools, write prompts, generate natural-language explanations, or format a
tutor response.

## Existing components and responsibilities

| Component | Responsibility in the recommendation flow |
|---|---|
| Analytics and risk services | Produce authoritative progress, delay, study-right, event, and risk evidence. |
| MCP and `AcademicToolGateway` | Access structured academic data without exposing repositories to agents. |
| `RecommendationEngine` | Map normalized evidence to deterministic recommendation decisions. |
| `RagIntegrationService` / `PolicyContextGateway` | Retrieve optional institutional guidance; never calculate student facts. |
| `RecommendationAgent` | Adapt shared agent results, invoke the engine, retrieve policy context, and return an `AgentResult`. |
| LangGraph workflow | Execute selected agents in order and preserve results in `AgentState`. |
| LLM / communication layer | Future presentation of approved structured decisions; it must not invent facts or rules. |

No second recommendation agent, risk scorer, retriever, vector store, or MCP
tool is introduced by Issue #110.

## Decision flow

```mermaid
flowchart TD
    A[Academic data] -->|existing MCP tools| B[Analytics and risk services]
    B --> C[Progress / study-right / risk AgentResults]
    C -->|adapter| D[RecommendationInput]
    D --> E[RecommendationEngine]
    E --> F[Structured decisions: type, priority, reason codes, evidence]
    F --> G[RecommendationAgent]
    G -->|narrow policy query| H[PolicyContextGateway]
    H -->|optional RAG evidence| G
    G --> I[AgentResult in shared AgentState]
    I --> J[Communication / tutor-facing response]
```

1. Existing services and agents determine academic facts.
2. `RecommendationAgent` validates that risk ran first and adapts its structured
   output into `RecommendationInput`.
3. `RecommendationEngine.evaluate` applies explicit mappings and produces
   `RecommendationDecision` objects.
4. The agent optionally retrieves relevant institutional context for each
   unique policy query. Retrieval failure does not change academic facts or
   cause the engine to invent policy.
5. The agent stores decisions, warnings, unavailable dimensions, and policy
   evidence in the normal `AgentResult` under the `recommendation` route.

## Contracts and explainability

`RecommendationInput` contains the student identifier, upstream risk level,
risk factors, `COMPLETE`/`PARTIAL` data status, unavailable dimensions, and
optional supporting evidence from prior agents. It intentionally contains no
raw repositories, tool clients, prompts, or database sessions.

Each `RecommendationDecision` contains:

- `recommendation_type` (also exposed as legacy `category` by the agent);
- `priority`, inherited from authoritative risk evidence;
- an approved advisory `action`;
- stable `reason_codes` describing the matched rule;
- structured evidence and `source_agents` provenance;
- an internal narrow policy query used only by the agent's RAG adapter.

The assessment retains `data_status`, `unavailable_dimensions`, and
`missing_information`. Missing evidence is never interpreted as a safe or
zero-risk result. RAG evidence is stored separately from student evidence, so
institutional context cannot be mistaken for a calculated student fact.

## Current integration and extension points

The existing `RecommendationAgent` remains registered in the LangGraph
workflow and now delegates deterministic mapping to the engine. Existing
progress and study-right agent results are attached as supporting provenance;
the risk result remains the required decision input.

The later Epic #109 issues can extend this boundary without moving business
rules into prompts:

- #111 can add additional approved recommendation mappings or application
  adapters around the same input/output contract.
- #112 can model intervention options associated with reason codes.
- #113 and #114 can render explanations from retained evidence and provenance.
- #115 can map structured decisions into tutor-facing templates.
- #116 can evaluate decision quality using deterministic fixtures and recorded
  evidence, without requiring a production LLM.

Any future canonical risk-score or tutor-meeting adapter should normalize its
existing result into `RecommendationInput`; it must not be recalculated inside
the engine.

# Shared Agent State for AI Academic Copilot

## Purpose

Shared Agent State is a typed, request-scoped contract that allows specialized agents to exchange context and intermediate results during a single LangGraph workflow execution.

This state is not long-term memory. It is transient and exists only for the lifetime of one user request or workflow invocation.

## State lifecycle

1. Entry layer creates an initial state object with request and academic context.
2. The supervisor and router may inspect and update routing fields.
3. Each agent reads common context, writes one or more partial results, and returns structured state updates.
4. Reducers merge partial updates into the shared state without losing previous findings.
5. The communication agent builds the final response from the accumulated state.

## Field summary

| Field | Written by | Read by | Purpose |
| --- | --- | --- | --- |
| `request_id` | Entry layer | Supervisor, agents, logger | Unique workflow identifier |
| `intent` | Entry layer | Supervisor, agents | User intent or explicit command |
| `route` | Entry layer or supervisor | Supervisor, agents | Primary workflow route |
| `student_id` | Entry layer or supervisor | Academic agents | Student academic context |
| `conversation_id` | Entry layer | Supervisor, agents | Optional chat/session context |
| `user_message` | Entry layer | Supervisor, agents | Raw user request text |
| `telegram_user_id` | Entry layer | Communication agent | Telegram user context |
| `telegram_chat_id` | Entry layer | Communication agent | Telegram chat context |
| `parameters` | Entry layer | Agents | Arbitrary workflow parameters |
| `selected_agents` | Supervisor | Router, agents | Planned agents for this workflow |
| `pending_agents` | Supervisor | Router, agents | Agents yet to run |
| `completed_agents` | Agents | Supervisor, communication | Agents that have finished |
| `current_agent` | Router | Agents, supervisor | Agent currently executing |
| `next_agent` | Router | Agents, supervisor | Next scheduled agent |
| `step_count` | Router | Supervisor, validation | Number of state update steps |
| `max_steps` | Router | Supervisor, validation | Workflow step limit |
| `agent_outputs` | Agents | Recommendation, reporting, communication | Typed intermediate agent results |
| `warnings` | Any node | Communication | Non-fatal issues |
| `errors` | Any node | Communication, supervisor | Execution failures |
| `final_response` | Communication agent | API or Telegram adapter | Final structured result |
| `response_format` | Communication agent | API or Telegram adapter | Preferred output type |
| `workflow_status` | Supervisor or router | Supervisor, communication | Overall workflow state |
| `metadata` | Any node | Supervisor, logger | Implementation-specific hints |

## State ownership

- `request_id`, `intent`, `route`, `user_message`, `conversation_id`, `telegram_user_id`, `telegram_chat_id`, `parameters`, and `student_id` are entry-layer fields.
- Routing fields such as `selected_agents`, `pending_agents`, `completed_agents`, `current_agent`, `next_agent`, `step_count`, `max_steps`, and `workflow_status` are owned by the supervisor or router.
- `agent_outputs` is written by specialized agents.
- `warnings` and `errors` may be written by any node.
- `final_response` and `response_format` are owned by the communication agent.

## Field usage examples

### Initial state example

```python
from app.agents.state import create_initial_state
from app.agents.types import AgentRoute

state = create_initial_state(
    request_id="req-123",
    intent="student progress",
    route="progress",
    user_message="Show me this student's academic progress.",
    student_id=42,
    conversation_id="conv-abc",
    telegram_user_id="tg-user-1",
    telegram_chat_id="tg-chat-1",
)
```

### Partial agent update example

```python
return {
    "agent_outputs": {
        "progress": progress_result,
    },
    "completed_agents": ["progress"],
    "warnings": ["Curriculum data was not available."],
}
```

## Reducer and merge rules

- `merge_agent_results` replaces the previous result for the same agent with the latest update.
- `append_warnings` preserves warning order and accumulates new warnings.
- `append_errors` preserves error order and accumulates new errors.
- `append_completed_agents` preserves agent order and avoids duplicate completed entries.

## Error and warning propagation

- Warnings are non-fatal and should not stop workflow execution by themselves.
- Errors should be surfaced in the final response and may cause the supervisor to stop or choose a different route.
- Partial results are preserved even when an agent returns warnings or errors.

## State versus memory

- **Shared state** is request-scoped and lives only for one workflow execution.
- **Agent memory** is cross-session and is explicitly out of scope for Issue #87.
- Shared state must not store database connections, MCP clients, LLM clients, API keys, or full raw student records.

## Privacy rules

- Keep shared state minimal and avoid embedding sensitive data unnecessarily.
- Do not log the full shared state when it contains student identifiers or user message content.
- Only pass student identifiers and minimal context between agents.

## Adding a new state field safely

1. Add the field to `backend/app/agents/types.py`.
2. Update `create_initial_state` in `backend/app/agents/state.py` if the field is part of initial context.
3. Update `validate_agent_state` to enforce any required invariants.
4. Update documentation and tests.

## Coordination points with Issue #79 and Issue #88

- Issue #87 implements shared state only; it does not decide supervisor routing or agent execution order.
- The `AgentState` contract is intentionally generic so Issue #79 can reuse it for the supervisor and agent orchestration.
- Issue #88 will decide what belongs in long-term memory. This file keeps state transient and request-scoped.

# LangGraph Academic Agent Workflow

Issue #167 introduces the orchestration boundary for the academic agents.

## Responsibilities

`AcademicAgentWorkflow` receives the canonical `AgentState`, executes the routes
in `selected_agents` in deterministic order, accumulates `AgentResult` objects,
tracks execution progress, enforces `max_steps`, and assigns the final workflow
status.

The graph contains three nodes:

1. `prepare` normalizes the execution plan and initializes pending work.
2. `execute_agent` resolves one agent from `AgentRegistry`, runs it, and records
   its result or error before looping.
3. `finalize` assigns `completed`, `partial`, or `failed` deterministically.

## Dependency boundaries

The workflow depends on `AgentRegistry` and `AcademicToolGateway`. Both can be
replaced with test doubles. It never accesses MCP tools, database sessions,
repositories, application services, RAG, Chat Service, or Telegram directly.

The initial production registry supports `progress` and `study_rights`. New
agents can be registered without changing graph topology.

## Usage

```python
from app.agents.state import create_initial_state
from app.agents.workflow import create_academic_agent_workflow

state = create_initial_state(
    user_message="Check student 42",
    student_id=42,
)
state.selected_agents = ["progress", "study_rights"]

workflow = create_academic_agent_workflow()
result = await workflow.run(state)
```

Chat Service integration, routing from natural-language intent, RAG context,
and persistent checkpointing are intentionally outside this issue.
